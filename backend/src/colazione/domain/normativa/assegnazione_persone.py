"""Algoritmo greedy auto-assegnazione persone PdC → giornate dei turni.

Sub-MR 2.bis-a (Sprint 8.0): per un programma in stato
``PDC_CONFERMATO`` e una finestra calendariale ``[data_da, data_a]``,
assegna le persone disponibili alle giornate dei turni del programma
rispettando i vincoli normativi (vedi ``docs/NORMATIVA-PDC.md`` §10
+ §11).

**Vincoli HARD** (bloccano l'assegnazione):

- Sede residenza == deposito_pdc del turno (i PdC coprono i turni del
  proprio deposito; il caller pre-filtra le persone per deposito).
- Nessuna ``IndisponibilitaPersona`` approvata che copre la data.
- Nessuna assegnazione sulla stessa data per la stessa persona
  (incluse esistenti DB e quelle generate nello stesso run).
- Riposo intraturno (§11.5):
  - 11h standard tra due giornate consecutive
  - 14h dopo una giornata che finisce 00:01-01:00
  - 16h dopo una giornata notturna

**Vincoli SOFT** (warning, non bloccano):

- FR cap §10.6: 1 FR/sett, 3 FR/28gg per persona.
- Riposo settimanale §11.4: ≥62h. Euristica MVP: ≥6 giornate
  assegnate in 7gg → warning (impossibile rispettare 62h).
- §11.2: primo giorno post-riposo non mattino (preferenziale).

**Differiti** (declared, fuori scope sub-MR 2.bis-a):

- §11.3 (ultimo giorno pre-riposo ≤15:00) — richiede schedule futuro.
- Qualifiche persona vs linee turno — richiede campo
  ``linee_richieste`` su ``TurnoPdc`` (oggi non esiste).
- Prestazione max 7h/8h30 (§11.8), condotta max 5h30 (§3),
  refezione 30min (§4) — già validati dal builder PdC.

**Algoritmo**:

1. Le giornate sono ordinate per ``(data, turno_pdc_giornata_id)`` —
   stabile, deterministico, idempotente.
2. Per ogni giornata, candidati = persone del deposito ordinate per
   ``persona.id``. Si scarta chi viola un vincolo HARD.
3. Si sceglie il primo candidato sopravvissuto (first-fit).
4. Dopo l'assegnazione, si valutano i vincoli SOFT.
5. Se nessun candidato passa i HARD: ``Mancanza`` con motivo specifico.

DB-agnostic: il caller (endpoint API) carica i dati dal DB, costruisce
le ``GiornataDaAssegnare`` + ``PersonaCandidata`` + ``AssegnazioneEsistente``,
chiama ``auto_assegna()``, persiste le ``Assegnazione`` risultanti in
``AssegnazioneGiornata``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum

# =====================================================================
# Costanti normative (§ docs/NORMATIVA-PDC.md)
# =====================================================================

#: Riposo intraturno standard fra due giornate consecutive (§11.5).
RIPOSO_INTRATURNO_MIN_STANDARD_H = 11

#: Riposo intraturno dopo giornata che finisce 00:01-01:00 (§11.5).
RIPOSO_INTRATURNO_MIN_NOTTE_TARDA_H = 14

#: Riposo intraturno dopo giornata notturna 00:01-05:00 (§11.5).
RIPOSO_INTRATURNO_MIN_NOTTURNA_H = 16

#: Cap FR settimanale per persona (§10.6).
FR_CAP_SETTIMANA = 1

#: Cap FR rolling 28gg per persona (§10.6).
FR_CAP_28GG = 3

#: Soglia euristica MVP per il warning di riposo settimanale (§11.4).
#: ≥6 giornate in 7gg → 62h consecutive non sono fisicamente possibili.
SOGLIA_WARNING_RIPOSO_SETTIMANALE = 6


# =====================================================================
# Enum
# =====================================================================


class MotivoMancanza(StrEnum):
    """Motivo per cui una giornata non è stata coperta."""

    NESSUN_PDC_DEPOSITO = "nessun_pdc_deposito"
    """Nessun PdC attivo nel deposito del turno."""

    TUTTI_INDISPONIBILI = "tutti_indisponibili"
    """Tutti i PdC del deposito hanno indisponibilità approvata."""

    TUTTI_GIA_ASSEGNATI = "tutti_gia_assegnati"
    """Tutti i PdC compatibili sono già assegnati nella stessa data."""

    TUTTI_RIPOSO_INTRATURNO_VIOLATO = "tutti_riposo_intraturno_violato"
    """Tutti i PdC compatibili violerebbero il riposo intraturno (§11.5)."""

    NESSUN_PDC_CANDIDATO = "nessun_pdc_candidato"
    """Fallback: cause miste (mix di indisponibilità/assegnazioni/riposo)."""


class TipoWarningSoft(StrEnum):
    """Tipo di warning soft emesso dall'algoritmo."""

    FR_CAP_SETTIMANA_SUPERATO = "fr_cap_settimana_superato"
    """Persona supera 1 FR/settimana ISO (§10.6)."""

    FR_CAP_28GG_SUPERATO = "fr_cap_28gg_superato"
    """Persona supera 3 FR rolling 28gg (§10.6)."""

    RIPOSO_SETTIMANALE_VIOLATO = "riposo_settimanale_violato"
    """Persona ha ≥6 assegnazioni in 7gg: §11.4 ≥62h non è rispettabile."""

    PRIMO_GIORNO_POST_RIPOSO_MATTINA = "primo_giorno_post_riposo_mattina"
    """Persona inizia mattina dopo gap di ≥2 giorni: §11.2 (preferenziale)."""


# =====================================================================
# Dataclass di input
# =====================================================================


@dataclass(frozen=True)
class IndisponibilitaPeriodo:
    """Una indisponibilità approvata (qualsiasi tipo)."""

    data_inizio: date
    data_fine: date


@dataclass(frozen=True)
class GiornataDaAssegnare:
    """Una giornata-data candidata all'assegnazione.

    Costruita dal caller a partire da ``TurnoPdcGiornata`` espandendo
    le date che matchano la ``variante_calendario`` nella finestra
    ``[data_da, data_a]``.
    """

    turno_pdc_giornata_id: int
    """PK target di ``AssegnazioneGiornata.turno_pdc_giornata_id``."""

    turno_pdc_id: int
    """PK del turno padre (per logging/diagnostica nelle mancanze)."""

    data: date
    """Data calendariale dell'assegnazione."""

    deposito_pdc_id: int
    """ID del deposito PdC del turno (filtro HARD: persona must match)."""

    inizio_prestazione: time
    """Ora di inizio servizio della giornata."""

    fine_prestazione: time
    """Ora di fine servizio. Se ``≤ inizio_prestazione`` → notturna che
    attraversa la mezzanotte (fine cade nel giorno successivo)."""

    is_notturno: bool
    """True se la giornata è classificata notturna (§11.5: 16h riposo
    successivo)."""

    is_fr: bool
    """True se la giornata termina fuori dalla sede residenza del PdC
    (§10.1). Caller computes ``stazione_fine != stazione_collegata_deposito``.
    Quando ``False`` (default conservativo per giornate ambigue), i FR
    cap §10.6 non si applicano."""


@dataclass(frozen=True)
class PersonaCandidata:
    """Una persona PdC candidata all'assegnazione.

    Pre-filtrata dal caller a:
    - ``profilo == 'PdC'``
    - ``is_matricola_attiva == True``
    - ``azienda_id`` corretta
    - ``sede_residenza_id`` valorizzato
    """

    id: int
    sede_residenza_id: int
    indisponibilita: tuple[IndisponibilitaPeriodo, ...]


@dataclass(frozen=True)
class AssegnazioneEsistente:
    """Una assegnazione già nel DB (non sovrascrivibile)."""

    persona_id: int
    data: date
    turno_pdc_giornata_id: int


# =====================================================================
# Dataclass di output
# =====================================================================


@dataclass(frozen=True)
class Assegnazione:
    """Una nuova assegnazione generata (da inserire in ``assegnazione_giornata``)."""

    persona_id: int
    turno_pdc_giornata_id: int
    data: date


@dataclass(frozen=True)
class Mancanza:
    """Una giornata non coperta + motivo specifico."""

    turno_pdc_giornata_id: int
    turno_pdc_id: int
    data: date
    motivo: MotivoMancanza


@dataclass(frozen=True)
class WarningSoft:
    """Un warning soft (assegnazione effettuata ma con possibile violazione
    di vincolo non rigido)."""

    persona_id: int
    data: date
    tipo: TipoWarningSoft
    descrizione: str


@dataclass(frozen=True)
class RisultatoAutoAssegna:
    """Risultato completo dell'algoritmo."""

    assegnazioni: tuple[Assegnazione, ...]
    """Nuove assegnazioni da persistere."""

    mancanze: tuple[Mancanza, ...]
    """Giornate non coperte (richiedono override manuale o nuove persone)."""

    warning_soft: tuple[WarningSoft, ...]
    """Warning emessi: l'assegnazione è stata fatta ma viola un soft."""

    n_giornate_totali: int
    """Numero totale di giornate-data processate."""

    n_giornate_coperte: int
    """Numero di giornate coperte (esistenti pre-run + nuove)."""

    @property
    def delta_copertura_pct(self) -> float:
        """Percentuale di copertura, 0..100. Se zero giornate da
        assegnare → 100% (vuoto = perfetto, nessun gap)."""
        if self.n_giornate_totali == 0:
            return 100.0
        return round(100.0 * self.n_giornate_coperte / self.n_giornate_totali, 1)


# =====================================================================
# Helpers (puri)
# =====================================================================


def _datetime_inizio(g: GiornataDaAssegnare) -> datetime:
    """``datetime`` di inizio prestazione."""
    return datetime.combine(g.data, g.inizio_prestazione)


def _datetime_fine(g: GiornataDaAssegnare) -> datetime:
    """``datetime`` di fine prestazione, gestendo notturne post-mezzanotte."""
    fine_dt = datetime.combine(g.data, g.fine_prestazione)
    if g.fine_prestazione <= g.inizio_prestazione:
        fine_dt += timedelta(days=1)
    return fine_dt


def _riposo_richiesto_h(prev: GiornataDaAssegnare) -> int:
    """Ore di riposo intraturno richieste DOPO la giornata ``prev`` (§11.5)."""
    if prev.is_notturno:
        return RIPOSO_INTRATURNO_MIN_NOTTURNA_H
    fine_t = _datetime_fine(prev).time()
    if time(0, 1) <= fine_t <= time(1, 0):
        return RIPOSO_INTRATURNO_MIN_NOTTE_TARDA_H
    return RIPOSO_INTRATURNO_MIN_STANDARD_H


def _indisponibile_in_data(p: PersonaCandidata, target: date) -> bool:
    """True se la persona ha indisponibilità approvata che copre ``target``."""
    return any(
        per.data_inizio <= target <= per.data_fine
        for per in p.indisponibilita
    )


# =====================================================================
# Stato interno (mutabile, isolato all'invocazione)
# =====================================================================


@dataclass
class _StatoAssegna:
    """Stato muta interno all'algoritmo greedy. Non esposto al caller."""

    assegnate_per_persona_data: dict[tuple[int, date], bool] = field(default_factory=dict)
    """``(persona_id, data) → True``: include esistenti DB + nuove."""

    storia_per_persona: dict[int, list[GiornataDaAssegnare]] = field(default_factory=dict)
    """``persona_id → [giornata, ...]``: cronologia delle giornate
    appena assegnate dall'algoritmo (per riposo intraturno + soft)."""

    fr_per_persona: dict[int, list[date]] = field(default_factory=dict)
    """``persona_id → [data_FR, ...]``: solo FR generate dall'algoritmo,
    per cap settimanali/mensili."""


def _registra_assegnazione(
    stato: _StatoAssegna,
    persona_id: int,
    g: GiornataDaAssegnare,
) -> None:
    """Aggiorna lo stato dopo una scelta del greedy."""
    stato.assegnate_per_persona_data[(persona_id, g.data)] = True
    stato.storia_per_persona.setdefault(persona_id, []).append(g)
    if g.is_fr:
        stato.fr_per_persona.setdefault(persona_id, []).append(g.data)


# =====================================================================
# Vincoli SOFT
# =====================================================================


def _check_warning_soft(
    persona_id: int,
    g: GiornataDaAssegnare,
    stato: _StatoAssegna,
) -> list[WarningSoft]:
    """Valuta i vincoli SOFT dopo che ``g`` è stata assegnata a ``persona_id``."""
    out: list[WarningSoft] = []

    # §10.6 — FR cap settimana ISO + 28gg
    if g.is_fr:
        fr_dates = stato.fr_per_persona.get(persona_id, [])
        target_iso = g.data.isocalendar()[:2]  # (year, week)
        same_week = [d for d in fr_dates if d.isocalendar()[:2] == target_iso]
        if len(same_week) > FR_CAP_SETTIMANA:
            out.append(
                WarningSoft(
                    persona_id=persona_id,
                    data=g.data,
                    tipo=TipoWarningSoft.FR_CAP_SETTIMANA_SUPERATO,
                    descrizione=(
                        f"{len(same_week)} FR nella settimana ISO "
                        f"{target_iso[0]}-W{target_iso[1]:02d}: "
                        f"cap §10.6 = {FR_CAP_SETTIMANA}/sett"
                    ),
                )
            )
        finestra_28 = [d for d in fr_dates if (g.data - d).days < 28]
        if len(finestra_28) > FR_CAP_28GG:
            out.append(
                WarningSoft(
                    persona_id=persona_id,
                    data=g.data,
                    tipo=TipoWarningSoft.FR_CAP_28GG_SUPERATO,
                    descrizione=(
                        f"{len(finestra_28)} FR negli ultimi 28gg: "
                        f"cap §10.6 = {FR_CAP_28GG}/28gg"
                    ),
                )
            )

    # §11.4 — riposo settimanale euristica MVP
    storia = stato.storia_per_persona.get(persona_id, [])
    finestra_inizio = g.data - timedelta(days=6)
    in_finestra = sum(
        1 for gg in storia if finestra_inizio <= gg.data <= g.data
    )
    if in_finestra >= SOGLIA_WARNING_RIPOSO_SETTIMANALE:
        out.append(
            WarningSoft(
                persona_id=persona_id,
                data=g.data,
                tipo=TipoWarningSoft.RIPOSO_SETTIMANALE_VIOLATO,
                descrizione=(
                    f"{in_finestra} assegnazioni in 7gg "
                    f"({finestra_inizio.isoformat()}..{g.data.isoformat()}): "
                    f"riposo settimanale §11.4 ≥{RIPOSO_INTRATURNO_MIN_NOTTURNA_H}"
                    "h non rispettabile"
                ),
            )
        )

    # §11.2 — primo giorno post-riposo non mattino (preferenziale)
    # Storia include la giornata appena registrata: la "precedente" è
    # storia[-2]. Se gap tra le due ≥ 2 giorni solari → era un riposo.
    if len(storia) >= 2:
        prev = storia[-2]
        gap_giorni = (g.data - prev.data).days
        if gap_giorni >= 2 and g.inizio_prestazione < time(6, 0):
            out.append(
                WarningSoft(
                    persona_id=persona_id,
                    data=g.data,
                    tipo=TipoWarningSoft.PRIMO_GIORNO_POST_RIPOSO_MATTINA,
                    descrizione=(
                        f"Inizio {g.inizio_prestazione.strftime('%H:%M')} "
                        f"dopo gap di {gap_giorni}gg: §11.2 (preferenziale)"
                    ),
                )
            )

    return out


# =====================================================================
# Entry point
# =====================================================================


def auto_assegna(
    *,
    giornate: Sequence[GiornataDaAssegnare],
    persone: Sequence[PersonaCandidata],
    assegnazioni_esistenti: Sequence[AssegnazioneEsistente],
) -> RisultatoAutoAssegna:
    """Greedy first-fit per l'auto-assegnazione persone → giornate.

    Vedi docstring del modulo per la descrizione completa.
    """
    # Indice persone per deposito + sort per id (deterministic)
    persone_per_deposito: dict[int, list[PersonaCandidata]] = {}
    for p in persone:
        persone_per_deposito.setdefault(p.sede_residenza_id, []).append(p)
    for bucket in persone_per_deposito.values():
        bucket.sort(key=lambda x: x.id)

    # Stato iniziale popolato dalle assegnazioni esistenti.
    # Le giornate già coperte (turno_pdc_giornata_id, data) vanno
    # contate in n_giornate_coperte ma NON ri-assegnate.
    stato = _StatoAssegna(
        assegnate_per_persona_data={
            (a.persona_id, a.data): True for a in assegnazioni_esistenti
        },
    )
    gia_coperte: set[tuple[int, date]] = {
        (a.turno_pdc_giornata_id, a.data) for a in assegnazioni_esistenti
    }

    assegnazioni_nuove: list[Assegnazione] = []
    mancanze: list[Mancanza] = []
    warning_soft: list[WarningSoft] = []
    n_pre_coperte = 0

    # Ordinamento deterministico
    giornate_ord = sorted(
        giornate, key=lambda g: (g.data, g.turno_pdc_giornata_id)
    )

    for g in giornate_ord:
        if (g.turno_pdc_giornata_id, g.data) in gia_coperte:
            n_pre_coperte += 1
            continue

        candidati = persone_per_deposito.get(g.deposito_pdc_id, [])
        if not candidati:
            mancanze.append(
                Mancanza(
                    turno_pdc_giornata_id=g.turno_pdc_giornata_id,
                    turno_pdc_id=g.turno_pdc_id,
                    data=g.data,
                    motivo=MotivoMancanza.NESSUN_PDC_DEPOSITO,
                )
            )
            continue

        scelto: PersonaCandidata | None = None
        n_indisp = 0
        n_assegnate = 0
        n_riposo = 0

        for persona in candidati:
            if _indisponibile_in_data(persona, g.data):
                n_indisp += 1
                continue
            if stato.assegnate_per_persona_data.get((persona.id, g.data)):
                n_assegnate += 1
                continue
            storia = stato.storia_per_persona.get(persona.id)
            if storia:
                ultima = storia[-1]
                gap_h = (
                    _datetime_inizio(g) - _datetime_fine(ultima)
                ).total_seconds() / 3600
                if gap_h < _riposo_richiesto_h(ultima):
                    n_riposo += 1
                    continue
            scelto = persona
            break

        if scelto is None:
            n_tot = len(candidati)
            if n_riposo == n_tot and n_riposo > 0:
                motivo = MotivoMancanza.TUTTI_RIPOSO_INTRATURNO_VIOLATO
            elif n_assegnate == n_tot:
                motivo = MotivoMancanza.TUTTI_GIA_ASSEGNATI
            elif n_indisp == n_tot:
                motivo = MotivoMancanza.TUTTI_INDISPONIBILI
            else:
                motivo = MotivoMancanza.NESSUN_PDC_CANDIDATO
            mancanze.append(
                Mancanza(
                    turno_pdc_giornata_id=g.turno_pdc_giornata_id,
                    turno_pdc_id=g.turno_pdc_id,
                    data=g.data,
                    motivo=motivo,
                )
            )
            continue

        assegnazioni_nuove.append(
            Assegnazione(
                persona_id=scelto.id,
                turno_pdc_giornata_id=g.turno_pdc_giornata_id,
                data=g.data,
            )
        )
        _registra_assegnazione(stato, scelto.id, g)
        warning_soft.extend(_check_warning_soft(scelto.id, g, stato))

    n_totali = len(giornate_ord)
    n_coperte = n_pre_coperte + len(assegnazioni_nuove)

    return RisultatoAutoAssegna(
        assegnazioni=tuple(assegnazioni_nuove),
        mancanze=tuple(mancanze),
        warning_soft=tuple(warning_soft),
        n_giornate_totali=n_totali,
        n_giornate_coperte=n_coperte,
    )
