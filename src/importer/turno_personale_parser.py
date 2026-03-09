"""
Parser per PDF "Turno Personale" Trenord (Turni PdC rete RFI).

Questo parser gestisce documenti in formato tabellare dove ogni pagina
contiene giornate numerate con varianti per tipo giorno (LMXGV/S/D).

Struttura tipica di una pagina:
  - Header: numero turno, deposito
  - Righe con: numero giornata, tipo giorno (LMXGV/S/D), treni, orari
  - S.COMP = disponibilita (standby, senza treni assegnati)
  - Ore settimanali in fondo

Usa pdfplumber per l'estrazione testo (PDF digitali, no OCR).
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logger = logging.getLogger(__name__)


@dataclass
class PersonalShiftDay:
    """Una variante di giornata nel turno personale."""
    day_number: int
    variant_type: str = "LMXGV"   # LMXGV, S, D
    day_type: str = "LV"          # LV, SAB, DOM
    train_ids: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    dep_times: list = field(default_factory=list)
    arr_times: list = field(default_factory=list)
    is_scomp: bool = False
    scomp_duration_min: int = 0
    prestazione_min: int = 0
    condotta_min: int = 0
    presentation_time: str = ""
    end_time: str = ""
    notes: str = ""


@dataclass
class PersonalShift:
    """Un turno personale completo con tutte le giornate."""
    name: str = ""
    deposito: str = ""
    turn_number: str = ""
    days: list = field(default_factory=list)  # list of PersonalShiftDay
    weekly_hours: float = 0
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Regex patterns per il parsing del turno personale
# ---------------------------------------------------------------------------

# Pattern per numeri di treno (4-5 cifre)
RE_TRAIN_ID = re.compile(r'\b(\d{4,5})\b')

# Pattern per orari HH:MM o H:MM
RE_TIME = re.compile(r'\b(\d{1,2}:\d{2})\b')

# Pattern per S.COMP / SCOMP / DISPONIBILE
RE_SCOMP = re.compile(r'\bS\.?\s*COMP\b|\bDISPONIBILE\b|\bSCOMP\b', re.IGNORECASE)

# Pattern per tipo giorno
RE_DAY_TYPE = re.compile(r'\b(LMXGV|LV|SAB|DOM|FEST|GG|LS)\b', re.IGNORECASE)

# Pattern per numero giornata (G1, G2, ... o 1., 2., ...)
RE_DAY_NUMBER = re.compile(r'(?:G|Giorno\s*)(\d+)|\b(\d+)\s*[.)\-]')

# Pattern per stazioni (parole uppercase di 3+ lettere)
RE_STATION = re.compile(r'\b([A-Z][A-Z\s]{2,})\b')


def parse_turno_personale_pdf(pdf_path: str) -> PersonalShift:
    """
    Parsa un PDF di Turno Personale Trenord e restituisce la struttura.

    Il parsing e' basato sull'estrazione del testo pagina per pagina
    e sulla ricerca di pattern per giornate, treni, orari e S.COMP.

    Args:
        pdf_path: percorso del file PDF

    Returns:
        PersonalShift con tutte le giornate estratte
    """
    if pdfplumber is None:
        raise ImportError("pdfplumber non installato. Installare con: pip install pdfplumber")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {pdf_path}")

    logger.info(f"Parsing turno personale: {pdf_path}")

    shift = PersonalShift()
    all_text = []

    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            all_text.append(text)

            if page_num == 1:
                # Estrai informazioni dall'header della prima pagina
                _parse_header(text, shift)

            # Estrai giornate dalla pagina
            _parse_page_days(text, shift, page_num)

    shift.raw_text = "\n--- PAGE ---\n".join(all_text)

    # Post-processing: deduplica e ordina
    _postprocess(shift)

    logger.info(f"Parsing completato: {len(shift.days)} varianti giornata estratte")
    return shift


def _parse_header(text: str, shift: PersonalShift):
    """Estrai informazioni dall'header del documento."""
    lines = text.split('\n')
    for line in lines[:10]:  # Primi 10 righe
        line_upper = line.strip().upper()

        # Cerca numero turno
        m = re.search(r'TURNO\s*(?:N[.°]?\s*)?(\d+)', line_upper)
        if m:
            shift.turn_number = m.group(1)

        # Cerca deposito/impianto
        from ..constants import DEPOSITI
        for dep in DEPOSITI:
            if dep.upper() in line_upper:
                shift.deposito = dep
                break

        # Cerca nome turno
        if not shift.name and ('TURNO' in line_upper or 'PDC' in line_upper):
            shift.name = line.strip()


def _parse_page_days(text: str, shift: PersonalShift, page_num: int):
    """Estrai giornate e varianti da una pagina."""
    lines = text.split('\n')

    current_day_num = None
    current_variant = None

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        line_upper = line_stripped.upper()

        # Cerca numero giornata
        day_match = RE_DAY_NUMBER.search(line_stripped)
        if day_match:
            new_day = int(day_match.group(1) or day_match.group(2))
            if 1 <= new_day <= 20:  # range ragionevole
                current_day_num = new_day

        # Cerca tipo giorno
        day_type_match = RE_DAY_TYPE.search(line_upper)
        variant_type = None
        day_type = None
        if day_type_match:
            dt = day_type_match.group(1).upper()
            if dt in ('LMXGV', 'LV'):
                variant_type = 'LMXGV'
                day_type = 'LV'
            elif dt == 'SAB':
                variant_type = 'S'
                day_type = 'SAB'
            elif dt in ('DOM', 'FEST'):
                variant_type = 'D'
                day_type = 'DOM'
            elif dt == 'GG':
                variant_type = 'LMXGV'
                day_type = 'LV'
            elif dt == 'LS':
                variant_type = 'LMXGV'
                day_type = 'LV'

        # Cerca S.COMP
        is_scomp = bool(RE_SCOMP.search(line_upper))

        # Cerca treni
        train_ids = RE_TRAIN_ID.findall(line_stripped)

        # Cerca orari
        times = RE_TIME.findall(line_stripped)

        # Se abbiamo abbastanza informazioni, crea/aggiorna variante
        if current_day_num and (train_ids or is_scomp or (variant_type and times)):
            if not variant_type:
                variant_type = 'LMXGV'
                day_type = 'LV'

            psd = PersonalShiftDay(
                day_number=current_day_num,
                variant_type=variant_type,
                day_type=day_type,
                train_ids=train_ids,
                is_scomp=is_scomp,
            )

            # Assegna orari
            if times:
                if len(times) >= 2:
                    psd.presentation_time = times[0]
                    psd.end_time = times[-1]
                    # Calcola prestazione approssimativa
                    try:
                        start_m = _time_to_min(times[0])
                        end_m = _time_to_min(times[-1])
                        if end_m < start_m:
                            end_m += 24 * 60
                        psd.prestazione_min = end_m - start_m
                    except Exception:
                        pass
                elif len(times) == 1:
                    psd.presentation_time = times[0]

            # Assegna orari dep/arr per ogni treno
            if len(times) >= 2 * len(train_ids):
                for i, tid in enumerate(train_ids):
                    if 2 * i + 1 < len(times):
                        psd.dep_times.append(times[2 * i])
                        psd.arr_times.append(times[2 * i + 1])

            if is_scomp:
                psd.scomp_duration_min = psd.prestazione_min or 360

            shift.days.append(psd)


def _postprocess(shift: PersonalShift):
    """Post-processing: deduplica, ordina, calcola metriche."""
    if not shift.days:
        return

    # Ordina per day_number e variant_type
    shift.days.sort(key=lambda d: (d.day_number, d.variant_type))

    # Deduplica (tieni la versione con piu' informazioni)
    seen = {}
    unique = []
    for d in shift.days:
        key = (d.day_number, d.variant_type)
        if key in seen:
            # Tieni quella con piu' treni
            existing = seen[key]
            if len(d.train_ids) > len(existing.train_ids):
                unique[unique.index(existing)] = d
                seen[key] = d
        else:
            seen[key] = d
            unique.append(d)
    shift.days = unique

    # Calcola ore settimanali pesate
    total = 0
    freq_total = 0
    freq_map = {"LMXGV": 5, "S": 1, "D": 1}
    for d in shift.days:
        freq = freq_map.get(d.variant_type, 1)
        pres = d.scomp_duration_min if d.is_scomp else d.prestazione_min
        total += pres * freq
        freq_total += freq

    if freq_total > 0:
        shift.weekly_hours = total / 60


def _time_to_min(t: str) -> int:
    """Converte HH:MM in minuti."""
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def personal_shift_to_dict(shift: PersonalShift) -> dict:
    """Converte un PersonalShift in un dizionario per l'API."""
    days_map = defaultdict(list)
    for d in shift.days:
        days_map[d.day_number].append({
            "variant_type": d.variant_type,
            "day_type": d.day_type,
            "train_ids": d.train_ids,
            "is_scomp": d.is_scomp,
            "scomp_duration_min": d.scomp_duration_min,
            "prestazione_min": d.prestazione_min,
            "condotta_min": d.condotta_min,
            "presentation_time": d.presentation_time,
            "end_time": d.end_time,
            "dep_times": d.dep_times,
            "arr_times": d.arr_times,
            "notes": d.notes,
        })

    return {
        "name": shift.name,
        "deposito": shift.deposito,
        "turn_number": shift.turn_number,
        "weekly_hours": shift.weekly_hours,
        "days": [
            {
                "day_number": dn,
                "variants": variants,
            }
            for dn, variants in sorted(days_map.items())
        ],
    }
