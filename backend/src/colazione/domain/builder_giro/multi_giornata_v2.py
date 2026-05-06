"""Orchestratore builder v2 — pipeline MR-1110 end-to-end (sotto-MR 5).

Decisione utente 2026-05-06: questo modulo compone i 3 step della
nuova pipeline (vedi `docs/MR-1110-DESIGN.md` §4.1):

1. **Step 2** (``giornata_tipo.identifica_giornate_tipo``):
   raggruppa le ``CatenaIstanza`` per chiave 5-uple D1
   ``(materiale, sede, staz_inizio, staz_fine,
   codice_servizio_dominante)`` con fallback morbido per servizio
   ``None`` e filtro significatività ``min_istanze``.

2. **Step 3** (``varianti_calendariali.genera_varianti_per_lista``):
   per ogni ``GiornataTipo``, raggruppa le sue istanze per
   sequenza-treni identica in M ``VarianteCalendariale`` con
   etichetta parlante stile PDF Trenord.

3. **Step 4** (``concatenazione_ciclica.concatena_in_turni``):
   concatena le giornate-tipo ciclicamente in turni
   ``G1 → G2 → … → GN → G1`` con vincolo rigido D6 e gestione
   D2 (ciclo rotto → multi-turno via SCC).

L'output è una lista di ``TurnoConVarianti``: un turno con N
giornate-tipo arricchite ciascuna con M varianti calendariali. È
l'equivalente concettuale di ``aggregazione_a2.GiroAggregato`` v1
ma costruito con il modello "fasi del ciclo" anziché "giornate
consecutive di calendario".

**Coesistenza v1/v2** (D7 chiusa): questo modulo è completamente
parallelo a ``multi_giornata.py`` v1. Un programma materiale userà
v1 o v2 secondo il valore di ``ProgrammaMateriale.builder_version``
(implementazione lato persister/orchestratore di alto livello, non
in questo modulo).

Il modulo è **DB-agnostic**: niente sessioni SQLAlchemy, niente
HTTP, solo dataclass in/out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from colazione.domain.builder_giro.concatenazione_ciclica import (
    Turno,
    concatena_in_turni,
)
from colazione.domain.builder_giro.giornata_tipo import (
    CatenaIstanza,
    GiornataTipo,
    ParamGiornataTipo,
    identifica_giornate_tipo,
)
from colazione.domain.builder_giro.varianti_calendariali import (
    GiornataTipoConVarianti,
    genera_varianti_per_lista,
)

# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True)
class TurnoConVarianti:
    """Turno materiale arricchito con varianti calendariali per
    ogni giornata-tipo (output finale builder v2).

    Attributi:
        materiale_tipo_codice: tipo materiale (parte 1 chiave gruppo).
        localita_codice: sede manutenzione (parte 2 chiave gruppo).
        giornate_tipo: tuple ordinata ciclicamente di
            ``GiornataTipoConVarianti``. Ogni elemento ha la propria
            lista di varianti calendariali.

    Invariante (verificato a costruzione, vedi
    ``concatenazione_ciclica.concatena_in_turni``):

    - Per ogni K: ``giornate_tipo[K].staz_fine ==
      giornate_tipo[(K+1) % N].staz_inizio``.
    """

    materiale_tipo_codice: str
    localita_codice: str
    giornate_tipo: tuple[GiornataTipoConVarianti, ...]

    @property
    def n_giornate(self) -> int:
        return len(self.giornate_tipo)


@dataclass(frozen=True)
class ParamBuilderV2:
    """Parametri orchestratore v2.

    Attributi:
        min_istanze: soglia significatività giornate-tipo (D3,
            default 2).
    """

    min_istanze: int = 2


_DEFAULT_PARAM = ParamBuilderV2()


# =====================================================================
# Helpers privati
# =====================================================================


def _chiave_giornata(g: GiornataTipo) -> tuple[str, str, str, str, str | None]:
    """Estrae la chiave 5-uple D1 da una GiornataTipo per lookup."""
    return (
        g.materiale_tipo_codice,
        g.localita_codice,
        g.staz_inizio,
        g.staz_fine,
        g.codice_servizio_dominante,
    )


def _arricchisci_turno(
    turno: Turno,
    indice_arricchite: dict[
        tuple[str, str, str, str, str | None], GiornataTipoConVarianti
    ],
) -> TurnoConVarianti:
    """Sostituisce le ``GiornataTipo`` del Turno con le loro varianti
    calendariali generate dallo Step 3.

    Lookup tramite chiave 5-uple D1: ogni giornata-tipo del turno
    deve essere presente nell'indice (invariante del builder).
    """
    arricchite: list[GiornataTipoConVarianti] = []
    for gt in turno.giornate_tipo:
        chiave = _chiave_giornata(gt)
        gtv = indice_arricchite[chiave]
        arricchite.append(gtv)
    return TurnoConVarianti(
        materiale_tipo_codice=turno.materiale_tipo_codice,
        localita_codice=turno.localita_codice,
        giornate_tipo=tuple(arricchite),
    )


# =====================================================================
# API pubblica
# =====================================================================


def costruisci_turni_v2(
    istanze: list[CatenaIstanza],
    festivita: frozenset[date],
    periodo: tuple[date, date],
    params: ParamBuilderV2 = _DEFAULT_PARAM,
) -> tuple[list[TurnoConVarianti], list[CatenaIstanza]]:
    """Pipeline end-to-end builder v2 MR-1110.

    Args:
        istanze: lista di ``CatenaIstanza`` (catena posizionata + data
            + materiale assegnato). Tipicamente prodotta dal caller
            componendo l'output di ``costruisci_catene`` +
            ``posiziona_su_localita`` + assegnazione composizione.
        festivita: festività rilevanti per il periodo (nazionali +
            locali azienda + domeniche se rilevanti per FpF).
        periodo: ``(inizio, fine)`` validità programma materiale (D5).
        params: parametri (min_istanze).

    Returns:
        Tupla ``(turni, orfane)``:

        - ``turni``: lista di ``TurnoConVarianti`` ordinati
          deterministicamente. Ogni turno ha N giornate-tipo
          concatenate ciclicamente, ciascuna con M varianti
          calendariali.
        - ``orfane``: lista di ``CatenaIstanza`` non inquadrabili
          (sotto soglia significatività D3 oppure giornate-tipo
          impossibili da concatenare D2). Il caller le gestisce come
          "corse residue" del programma.

    Esempi:
        Input vuoto → output vuoto:

        >>> from datetime import date
        >>> costruisci_turni_v2(
        ...     [],
        ...     frozenset(),
        ...     (date(2026, 1, 1), date(2026, 12, 31)),
        ... )
        ([], [])
    """
    if not istanze:
        return ([], [])

    # Step 2: identifica giornate-tipo + filtra orfane.
    giornate_tipo, orfane_step2 = identifica_giornate_tipo(
        istanze,
        params=ParamGiornataTipo(min_istanze=params.min_istanze),
    )

    # Step 3: genera varianti calendariali per ogni giornata-tipo.
    giornate_arricchite = genera_varianti_per_lista(
        giornate_tipo, festivita, periodo
    )
    indice_arricchite = {
        _chiave_giornata(gtv.giornata): gtv for gtv in giornate_arricchite
    }

    # Step 4: concatena giornate-tipo (pure, senza varianti) in turni.
    turni_pure, orfane_step4 = concatena_in_turni(giornate_tipo)

    # Arricchisci i turni con le varianti generate allo Step 3.
    turni: list[TurnoConVarianti] = [
        _arricchisci_turno(t, indice_arricchite) for t in turni_pure
    ]

    # Le orfane Step 4 sono ``GiornataTipo`` (impossibili da
    # concatenare). Recupera le loro istanze originali per restituirle
    # al caller come "corse residue".
    orfane_combined: list[CatenaIstanza] = list(orfane_step2)
    for gt_orfana in orfane_step4:
        orfane_combined.extend(gt_orfana.istanze)

    # Ordina deterministicamente per data
    orfane_combined.sort(key=lambda i: i.data)

    return (turni, orfane_combined)
