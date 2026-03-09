"""
Parser per il PDF "Turni PdC rete RFI" di Trenord.

Estrae da ogni pagina:
  - Deposito (IMPIANTO)
  - Codice turno (es. ALOR_C)
  - Per ogni PROG: giornata, tipo giorno, orari, treni assegnati

NOTA: nel PDF i numeri treno e le stazioni nel grafico timeline
sono scritti al contrario (testo ruotato). Es. "82001" = treno 10028.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber


@dataclass
class PdcProg:
    """Una singola giornata (PROG) nel turno PdC."""
    prog_number: int
    day_type: str                    # LMXGV, S, D, SD, LMXGVSD
    start_time: str                  # HH:MM
    end_time: str                    # HH:MM
    lavoro_min: int = 0              # Durata lavoro in minuti
    condotta_min: int = 0            # Durata condotta in minuti
    km: int = 0
    notturno: bool = False
    riposo_min: int = 0              # Riposo in minuti
    train_ids: list[str] = field(default_factory=list)
    note: str = ""
    is_rest: bool = False            # S.COMP / Disponibile
    raw_text: str = ""


@dataclass
class PdcTurno:
    """Un turno completo di un deposito."""
    depot: str
    turno_code: str
    turno_id: str = ""
    valid_from: str = ""
    valid_to: str = ""
    progs: list[PdcProg] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)


# ---------- Pattern costanti ----------
DAY_TYPES = {"LMXGVSD", "LMXGV", "SD", "S", "D", "LMX", "GV", "LMXG", "VSD",
             "LM", "XG", "VS", "L", "M", "X", "G", "V"}

# Stazioni abbreviate reversed -> nome reale (parziale, le piu' comuni)
STATION_ABBREV_REV = {
    "AL": "ALESSANDRIA",
    "LA": "ALESSANDRIA",  # reversed
    "orIM": "MILANO ROGOREDO",
    "ecIM": "MILANO CENTRALE",
    "gpIM": "MILANO P.GARIBALDI",
    "abIM": "MILANO LAMBRATE",
    "lcIM": "MILANO CADORNA",
    "VP": "PAVIA",
    "HGOV": "VOGHERA",
    "NORA": "ARONA",
    "OMOD": "DOMODOSSOLA",
}


def _reverse_str(s: str) -> str:
    """Inverti una stringa carattere per carattere."""
    return s[::-1]


def _parse_hhmm_to_min(s: str) -> int:
    """Converte HH:MM in minuti."""
    parts = s.strip().split(":")
    if len(parts) == 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return 0


def _extract_train_ids_from_block(text: str) -> list[str]:
    """Estrae numeri treno da un blocco di testo del turno PdC.

    Strategia:
    1. Cerca note esplicite: "TR 10028", "Tr.10205"
    2. Cerca numeri a 5 cifre e invertili
    3. Filtra: il numero invertito deve essere un treno plausibile (10000-99999)
    """
    train_ids = set()

    # 1. Note esplicite (testo non invertito)
    for m in re.finditer(r'(?:TR|Tr\.?)\s*(\d{4,6})', text):
        train_ids.add(m.group(1))

    # 2. Numeri a 5 cifre invertiti
    # Escludiamo numeri che sono chiaramente orari o codici
    # (i numeri invertiti di treno iniziano tipicamente con 1,2,3,4,5,6,7,8,9)
    for m in re.finditer(r'\b(\d{5})\b', text):
        num = m.group(1)
        reversed_num = _reverse_str(num)

        # Escludi il codice turno (es. 65046 -> 64056, non e' un treno)
        # e numeri che sono chiaramente non-treni
        rev_int = int(reversed_num)

        # Treni Trenord: tipicamente 10000-99999
        # Ma i numeri tipo 00000-09999 non sono treni
        if 2000 <= rev_int <= 99999:
            # Controlla che il numero originale non sia il risultato
            # di un reverse di un numero gia' presente nelle note
            if num not in train_ids:
                train_ids.add(reversed_num)

    # 3. Numeri a 4 cifre che potrebbero essere treni (es. "736(" -> 637?)
    # Cerchiamo pattern tipo "NNN(" che sembra un numero treno con parentesi
    for m in re.finditer(r'\b(\d{3,4})\(', text):
        num = m.group(1)
        reversed_num = _reverse_str(num)
        rev_int = int(reversed_num)
        if 100 <= rev_int <= 99999:
            train_ids.add(reversed_num)

    # Rimuovi duplicati e numeri che compaiono sia diretti che invertiti
    # (es. "10028" in nota e "82001" nel grafico -> tieni solo "10028")
    final = set()
    for tid in train_ids:
        rev = _reverse_str(tid)
        # Se il numero e il suo reverse sono entrambi presenti, tieni l'originale
        if rev in train_ids and int(tid) < int(rev):
            continue
        final.add(tid)

    return sorted(final)


def _split_into_prog_blocks(cell_text: str) -> list[dict]:
    """Divide il testo della cella grande in blocchi PROG."""
    # Pattern: numero PROG + [HH:MM] [HH:MM]
    # Es: "3 [06:04] [14:34]"
    prog_pattern = re.compile(
        r'(\d+)\s*\[(\d{1,2}:\d{2})\]\s*\[(\d{1,2}:\d{2})\]'
    )

    # Pattern per Lav/Cct/Km: "08:30 03:33 171 no 14:45"
    metrics_pattern = re.compile(
        r'(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+(\d+)\s+(s[iì]|no)\s+(\d{1,2}:\d{2})'
    )

    # Pattern per tipo giorno
    day_type_pattern = re.compile(
        r'\b(LMXGVSD|LMXGV|LMXG|LMX|GV|SD|VSD|S|D)\b'
    )

    # Trova tutte le occorrenze di PROG
    prog_matches = list(prog_pattern.finditer(cell_text))

    blocks = []
    for idx, pm in enumerate(prog_matches):
        prog_num = int(pm.group(1))
        start_time = pm.group(2)
        end_time = pm.group(3)

        # Determina il range di testo per questo blocco
        block_start = pm.start()
        # Cerca indietro per il tipo giorno
        # Il tipo giorno e' tipicamente qualche riga sopra il PROG
        lookback_start = prog_matches[idx - 1].end() if idx > 0 else 0
        preceding_text = cell_text[lookback_start:block_start]

        # Fine del blocco: inizio del prossimo blocco o fine testo
        block_end = prog_matches[idx + 1].start() if idx + 1 < len(prog_matches) else len(cell_text)

        # Testo dopo il PROG match
        after_text = cell_text[pm.end():block_end]
        full_block = preceding_text + cell_text[block_start:block_end]

        # Tipo giorno
        day_matches = day_type_pattern.findall(preceding_text)
        day_type = day_matches[-1] if day_matches else "?"

        # Metriche
        mm = metrics_pattern.search(after_text)
        lavoro_min = 0
        condotta_min = 0
        km = 0
        notturno = False
        riposo_min = 0
        if mm:
            lavoro_min = _parse_hhmm_to_min(mm.group(1))
            condotta_min = _parse_hhmm_to_min(mm.group(2))
            km = int(mm.group(3))
            notturno = mm.group(4).lower().startswith("s")
            riposo_min = _parse_hhmm_to_min(mm.group(5))

        # Check se e' un giorno di riposo (S.COMP, Disponibile)
        # Solo nel testo DOPO il PROG match (non preceding), per evitare bleed
        is_rest_text = ("PMOC.S" in after_text or "LAPMOC" in after_text
                        or "Disponibile" in after_text
                        or "NORAPMOC" in after_text)
        # Se ha condotta e km, NON e' riposo anche se il testo lo suggerisce
        if condotta_min > 0 and km > 0:
            is_rest = False
        else:
            is_rest = is_rest_text or (condotta_min == 0 and km == 0)

        # Note (testo non invertito, es. "TR 10028 tempi maggiorati...")
        note_match = re.search(r'((?:TR|Tr\.?)\s*\d+[^\n]*)', full_block)
        note = note_match.group(1) if note_match else ""

        # Treni — estrai sempre, anche se is_rest (per completezza DB)
        train_ids = _extract_train_ids_from_block(full_block)

        blocks.append({
            "prog_number": prog_num,
            "day_type": day_type,
            "start_time": start_time,
            "end_time": end_time,
            "lavoro_min": lavoro_min,
            "condotta_min": condotta_min,
            "km": km,
            "notturno": notturno,
            "riposo_min": riposo_min,
            "is_rest": is_rest,
            "train_ids": train_ids,
            "note": note,
            "raw_text": full_block[:300],
        })

    return blocks


def parse_pdc_pdf(pdf_path: str) -> list[PdcTurno]:
    """Parse il PDF Turni PdC e restituisce lista di turni."""
    turni = []

    with pdfplumber.open(pdf_path) as pdf:
        current_turno: Optional[PdcTurno] = None

        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            # Cerca header
            header_match = re.search(
                r'IMPIANTO:\s*(\S+)\s+TURNO:\s*\[(\w+)\]\s*\[(\d+)\]'
                r'.*?DAL:\s*(\d{2}/\d{2}/\d{4})\s+AL:\s*(\d{2}/\d{2}/\d{4})',
                text
            )

            if header_match:
                depot = header_match.group(1)
                turno_code = header_match.group(2)
                turno_id = header_match.group(3)
                valid_from = header_match.group(4)
                valid_to = header_match.group(5)

                # Nuovo turno o continuazione?
                if (current_turno is None
                    or current_turno.depot != depot
                    or current_turno.turno_code != turno_code):
                    # Salva il turno precedente
                    if current_turno and current_turno.progs:
                        turni.append(current_turno)

                    current_turno = PdcTurno(
                        depot=depot,
                        turno_code=turno_code,
                        turno_id=turno_id,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        source_pages=[page_idx + 1],
                    )
                else:
                    # Stessa pagina turno, aggiungi pagina
                    current_turno.source_pages.append(page_idx + 1)

            if not current_turno:
                continue

            # Estrai PROG blocks dal testo della pagina
            blocks = _split_into_prog_blocks(text)

            for b in blocks:
                # Evita duplicati (lo stesso PROG+day_type)
                existing = [p for p in current_turno.progs
                           if p.prog_number == b["prog_number"]
                           and p.day_type == b["day_type"]]
                if existing:
                    # Aggiorna treni se ne abbiamo trovati di piu'
                    if len(b["train_ids"]) > len(existing[0].train_ids):
                        existing[0].train_ids = b["train_ids"]
                    continue

                current_turno.progs.append(PdcProg(
                    prog_number=b["prog_number"],
                    day_type=b["day_type"],
                    start_time=b["start_time"],
                    end_time=b["end_time"],
                    lavoro_min=b["lavoro_min"],
                    condotta_min=b["condotta_min"],
                    km=b["km"],
                    notturno=b["notturno"],
                    riposo_min=b["riposo_min"],
                    train_ids=b["train_ids"],
                    note=b["note"],
                    is_rest=b["is_rest"],
                    raw_text=b["raw_text"],
                ))

        # Salva l'ultimo turno
        if current_turno and current_turno.progs:
            turni.append(current_turno)

    return turni


def pdc_turni_to_flat_records(turni: list[PdcTurno]) -> list[dict]:
    """Converte la lista di turni in record piatti per il DB."""
    records = []
    for turno in turni:
        for prog in turno.progs:
            records.append({
                "depot": turno.depot,
                "turno_code": turno.turno_code,
                "turno_id": turno.turno_id,
                "valid_from": turno.valid_from,
                "valid_to": turno.valid_to,
                "prog_number": prog.prog_number,
                "day_type": prog.day_type,
                "start_time": prog.start_time,
                "end_time": prog.end_time,
                "lavoro_min": prog.lavoro_min,
                "condotta_min": prog.condotta_min,
                "km": prog.km,
                "notturno": prog.notturno,
                "riposo_min": prog.riposo_min,
                "train_ids": prog.train_ids,
                "is_rest": prog.is_rest,
                "note": prog.note,
            })
    return records


if __name__ == "__main__":
    import sys
    import json

    path = sys.argv[1] if len(sys.argv) > 1 else "test.pdf"
    turni = parse_pdc_pdf(path)

    print(f"Turni trovati: {len(turni)}")
    for t in turni:
        print(f"\n{'='*60}")
        print(f"Deposito: {t.depot} | Turno: {t.turno_code} [{t.turno_id}]")
        print(f"Valido: {t.valid_from} - {t.valid_to}")
        print(f"PROG: {len(t.progs)} giornate")
        for p in t.progs:
            trains_str = ", ".join(p.train_ids) if p.train_ids else "(nessun treno)"
            rest_str = " [RIPOSO]" if p.is_rest else ""
            print(f"  PROG {p.prog_number} [{p.day_type}] {p.start_time}-{p.end_time}"
                  f" | Lav:{p.lavoro_min}m Cct:{p.condotta_min}m Km:{p.km}"
                  f" | Treni: {trains_str}{rest_str}")
