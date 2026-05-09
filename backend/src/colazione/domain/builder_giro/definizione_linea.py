"""Modello formale di una **linea ferroviaria** Trenord (Sprint 8.2 MR-D0).

Sprint 8.2 Plan-D (riscrittura linea-centrica, opzione A radicale):
SEVERO ha votato il piano 7/10 con raccomandazione obbligatoria di
introdurre questo modulo come **fondazione** del nuovo builder.
Tutti i moduli successivi (MR-D1..D8) consumano `Linea` /
`SegmentoLinea` come input strutturato.

# Perché esiste questo modulo

Il vecchio builder (`catena.py` + `multi_giornata.py`) costruiva
catene libere topologicamente: una catena poteva mescolare corse
di linee diverse purché stazioni e orari combaciassero. Questa
libertà ha prodotto:

- **76 navette intra-day perse** (problema #1 prog 17): le navette
  S01860↔S01074 round-trip sono LINEE DEDICATE Trenord, ma il greedy
  le assorbiva in catene multi-pattern, perdendole.
- **Catene mix linee** (problema #4): regola 27 prog 14 ha 4
  direttrici nel filtro; il greedy mescolava R31+RE13+R34 nello
  stesso convoglio.
- **Ciclo aperto fuori Milano** (problema #2): catene libere
  vagavano fra Pavia/Mortara/Asti senza un concetto di "linea
  termina qui".

La realtà operativa Trenord è invece **linea-centrica**: ogni linea
(R31, R34, RE13, ecc.) ha un pattern di servizio fisso, capolinee
fissi, materiale dedicato, sosta notturna in punti precisi. Un
convoglio ETR522 che fa la R31 (ALES-MORTARA-MILANO) ci sta sopra
per giorni, non salta su RE13 (ALES-VOGHERA-PAVIA-MILANO) anche
se geograficamente compatibile.

# Granularità: Linea vs SegmentoLinea

SEVERO ha smascherato che una `Linea` ha **sotto-pattern**: la R31
ha sia corse complete (ALES↔MILANO) sia corse corte (ALES↔MORTARA
o MORTARA↔MILANO). Questi sotto-pattern sono operativamente
DISTINTI: hanno orari diversi, capolinee diversi, e devono essere
schedulati come segmenti separati.

Il modello distingue:

- ``Linea``: aggregato della linea commerciale (es. R31). Identificata
  da ``codice_linea``.
- ``SegmentoLinea``: pattern di servizio omogeneo (= corse con stessi
  capolinea + stesso pattern temporale). Una `Linea` ha 1+
  `SegmentoLinea`.

# Vincoli operativi (da MR-D0.5)

`SegmentoLinea` espone i vincoli che il builder DEVE rispettare:

- `sosta_massima_diurna_min`: durata max sosta intra-giornata fra
  servizi consecutivi (default 240 min = 4h).
- `sosta_massima_notturna_min`: durata max sosta fra giornate
  consecutive (default 720 min = 12h).
- `stazioni_sosta_notturna`: insieme di codici stazione ammessi per
  riposo del convoglio fra giornate.
- `capolinee`: insieme di codici stazione "estremo" del segmento
  (es. R31 corto = {S00470 ALES, S00034 MORTARA}; R31 completo =
  {S00470 ALES, S01640 MILANO_CERTOSA}).

I dati sosta/capolinee per segmento sono caricati dal builder
da `ProgrammaRegolaAssegnazione` (sezione `linea_definizioni_json`)
o, in assenza, derivati empiricamente da
`identifica_segmenti_da_corse` (vedi MR-D1).

# Tipo di servizio

Un `SegmentoLinea` è classificato in `TipoSegmento`:

- `LINEARE`: A→B→C... pattern unidirezionale o quasi-unidirezionale
  (es. R31 completo ALES→MORTARA→MILANO).
- `NAVETTA`: A↔B round-trip ripetuto N volte/die (es. S01860↔S01074
  4-8 round-trip giornaliere).
- `MISTO`: pattern intermedio (alcune corse complete, alcune corte).

Il tipo guida le decisioni di MR-D2 (assegna_convogli) e MR-D3
(costruisci_turno).

# DB-agnostic

Questo modulo è **dominio puro**: non importa SQLAlchemy né i
modelli ORM. Accetta `_CorsaLike` come Protocol (stesso pattern di
``catena.py``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Protocol

# =====================================================================
# Protocol — duck-typing input
# =====================================================================


class _CorsaLike(Protocol):
    """Una corsa: ORM ``CorsaCommerciale`` o dataclass test.

    Stesso Protocol di ``catena.py``, esteso con ``codice_linea``
    obbligatorio (necessario per il raggruppamento in `Linea`).
    """

    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    codice_linea: str


# =====================================================================
# Tipi enumerati
# =====================================================================


class TipoSegmento(StrEnum):
    """Classificazione operativa di un segmento di linea.

    Determina la strategia di assegnazione convogli (MR-D2) e
    costruzione turno (MR-D3):

    - ``LINEARE``: pattern A→B→C unidirezionale. Convoglio percorre
      tutta la tratta in una corsa, può fare round-trip ma non
      ripetuto N volte/die.
    - ``NAVETTA``: pattern A↔B ripetuto ≥3 round-trip/die. Linea
      dedicata con convoglio che fa SOLO quelle corse per tutto il
      turno.
    - ``MISTO``: alcune corse complete + alcune corte/parziali.
      Richiede assegnazione separata di convogli alle corse
      complete vs corte.
    """

    LINEARE = "lineare"
    NAVETTA = "navetta"
    MISTO = "misto"


# =====================================================================
# Modelli formali
# =====================================================================


@dataclass(frozen=True, kw_only=True)
class VincoliSosta:
    """Vincoli di sosta per un ``SegmentoLinea``.

    SEVERO Plan-D raccomandazione obbligatoria #1 (MR-D0.5): senza
    vincoli sosta espliciti, il builder può produrre pattern come
    sosta 20h44' a Voghera (caso prog 14 giro 574). Il vincolo va
    nei DATI strutturati, non hardcoded.

    Attributi:
        sosta_max_diurna_min: durata max sosta intra-giornata fra
            servizi consecutivi dello stesso convoglio sulla stessa
            linea. Default 240 min (4h). Sopra questa soglia il
            convoglio dovrebbe rientrare deposito o cambiare linea
            (= vuoto tecnico in MR-D6).
        sosta_max_notturna_min: durata max sosta fra giornate
            consecutive (sosta notturna programmata). Default 720
            min (12h). Sopra: spezzare il giro o anomalia da
            indagare.
        sosta_min_notturna_min: durata minima della sosta notturna
            (= il convoglio non riparte 30 min dopo l'ultima corsa
            del giorno precedente, riposa almeno N ore). Default
            300 min (5h).
    """

    sosta_max_diurna_min: int = 240
    sosta_max_notturna_min: int = 720
    sosta_min_notturna_min: int = 300

    def __post_init__(self) -> None:
        if self.sosta_max_diurna_min < 0:
            raise ValueError(
                "sosta_max_diurna_min deve essere >= 0, "
                f"ricevuto {self.sosta_max_diurna_min}"
            )
        if self.sosta_max_notturna_min < self.sosta_min_notturna_min:
            raise ValueError(
                "sosta_max_notturna_min deve essere >= "
                f"sosta_min_notturna_min ({self.sosta_min_notturna_min}), "
                f"ricevuto {self.sosta_max_notturna_min}"
            )


@dataclass(frozen=True, kw_only=True)
class SegmentoLinea:
    """Pattern di servizio omogeneo all'interno di una `Linea`.

    Una `Linea` (es. R31) può avere più segmenti se il PdE espone
    pattern operativi distinti:

    - R31 completo: ALES → MORTARA → MILANO (capolinee ALES + MILANO)
    - R31 tronco: ALES → MORTARA (capolinee ALES + MORTARA)

    SEVERO Plan-D modifica obbligatoria #1: senza segmenti, MR-D2
    confonde corse complete e corte assegnando lo stesso convoglio
    a entrambe (= servizio operativamente illegale).

    Attributi:
        codice: identificatore univoco del segmento all'interno della
            linea (es. ``"R31_completo"``, ``"R31_tronco"``,
            ``"S01860_S01074"``). Stringhe deterministiche per debug.
        tipo: classificazione operativa (`LINEARE`, `NAVETTA`, `MISTO`).
        capolinee: insieme di codici stazione "estremi" del segmento
            (origine OR destinazione di tutte le corse del segmento).
            Es. R31 completo: ``{"S00470", "S01640"}``.
        stazioni_sosta_notturna: insieme di codici stazione ammessi
            come riposo del convoglio fra giornate consecutive. Per
            R31: ``{"S00470" ALES, "S01640" MI.CERTOSA}``. Per
            navette intra-Milano: il deposito sede.
        vincoli_sosta: parametri di sosta per il segmento (vedi
            ``VincoliSosta``).
        n_corse_per_die_media: media giornaliera di corse del
            segmento sull'intero perimetro. Usato da MR-D2 per
            stimare n convogli necessari.
    """

    codice: str
    tipo: TipoSegmento
    capolinee: frozenset[str]
    stazioni_sosta_notturna: frozenset[str]
    vincoli_sosta: VincoliSosta
    n_corse_per_die_media: float

    def __post_init__(self) -> None:
        if not self.codice:
            raise ValueError("SegmentoLinea.codice non può essere vuoto")
        if len(self.capolinee) < 2:
            raise ValueError(
                f"SegmentoLinea {self.codice!r}: capolinee deve "
                f"contenere almeno 2 stazioni, ricevuto "
                f"{sorted(self.capolinee)}"
            )
        if not self.stazioni_sosta_notturna:
            raise ValueError(
                f"SegmentoLinea {self.codice!r}: stazioni_sosta_notturna "
                "non può essere vuoto (un convoglio multi-giornata deve "
                "poter sostare da qualche parte)"
            )
        if self.n_corse_per_die_media < 0:
            raise ValueError(
                f"SegmentoLinea {self.codice!r}: "
                f"n_corse_per_die_media deve essere >= 0, ricevuto "
                f"{self.n_corse_per_die_media}"
            )


@dataclass(frozen=True, kw_only=True)
class Linea:
    """Linea ferroviaria commerciale Trenord (es. R31, RE13, S5).

    Aggregato di 1+ ``SegmentoLinea`` con pattern operativi
    distinti ma stesso ``codice_linea`` PdE.

    Attributi:
        codice_linea: identificatore commerciale della linea (es.
            ``"R31"``). Match diretto con ``CorsaCommerciale.codice_linea``.
        descrizione: descrizione human-readable (es. ``"Alessandria
            - Mortara - Milano"``). Solo per UI/log, non logica.
        segmenti: tuple di ``SegmentoLinea`` ordinata per codice
            (determinismo). Almeno 1.
    """

    codice_linea: str
    descrizione: str
    segmenti: tuple[SegmentoLinea, ...]

    def __post_init__(self) -> None:
        if not self.codice_linea:
            raise ValueError("Linea.codice_linea non può essere vuoto")
        if not self.segmenti:
            raise ValueError(
                f"Linea {self.codice_linea!r}: deve avere almeno 1 segmento"
            )
        codici_segmento = [s.codice for s in self.segmenti]
        if len(set(codici_segmento)) != len(codici_segmento):
            raise ValueError(
                f"Linea {self.codice_linea!r}: codici segmento duplicati: "
                f"{codici_segmento}"
            )


# =====================================================================
# Helpers di costruzione
# =====================================================================


def _coppia_capolinee(corse: Sequence[_CorsaLike]) -> frozenset[str]:
    """Estrae l'insieme dei capolinea da un gruppo di corse.

    Convenzione: una stazione è "capolinea" se appare come
    ``codice_origine`` di almeno una corsa del gruppo OR come
    ``codice_destinazione`` di almeno un'altra. La maggioranza dei
    pattern Trenord ha 2 capolinee (origine A → destinazione B +
    origine B → destinazione A). Pattern lineari A→B→C senza
    round-trip hanno solo 2 stazioni distinte (A e C).
    """
    origini = {c.codice_origine for c in corse}
    destinazioni = {c.codice_destinazione for c in corse}
    return frozenset(origini & destinazioni) | frozenset(
        # capolinee asimmetrici: stazioni che sono SOLO origine o SOLO
        # destinazione (pattern lineare unidirezionale)
        origini ^ destinazioni
    )


def _classifica_tipo(
    corse: Sequence[_CorsaLike],
    *,
    n_giorni_perimetro: int,
) -> TipoSegmento:
    """Classifica il tipo di segmento dal pattern delle corse.

    Heuristica:
    - **NAVETTA**: ≥3 round-trip/die in media (= ≥6 corse/die nello
      stesso pattern A↔B). Es. S01860↔S01074 8 corse/die = 4 round-trip.
    - **LINEARE**: pattern unidirezionale o ~simmetrico A↔B con ≤2
      round-trip/die.
    - **MISTO**: tutto il resto (es. corse complete + corse corte
      mescolate, ma con stesso codice_linea — distinguerle in
      segmenti separati è scope di ``identifica_segmenti_da_corse``).

    Args:
        corse: corse del segmento candidato.
        n_giorni_perimetro: numero giorni del periodo PdE su cui
            calcolare la media. >=1.
    """
    if n_giorni_perimetro < 1:
        raise ValueError(
            f"n_giorni_perimetro deve essere >= 1, "
            f"ricevuto {n_giorni_perimetro}"
        )
    if not corse:
        return TipoSegmento.LINEARE  # default per gruppi vuoti (defensive)

    # Conta coppie (origine, destinazione)
    coppie: Counter[tuple[str, str]] = Counter(
        (c.codice_origine, c.codice_destinazione) for c in corse
    )
    n_corse_die_media = len(corse) / n_giorni_perimetro

    # NAVETTA: 2 sole coppie (A→B e B→A) con frequenza alta
    if len(coppie) == 2 and n_corse_die_media >= 6.0:
        ((o1, d1), n1), ((o2, d2), n2) = coppie.most_common(2)
        if o1 == d2 and d1 == o2:  # round-trip simmetrico
            return TipoSegmento.NAVETTA

    # LINEARE: 1-2 coppie con frequenza moderata
    if len(coppie) <= 2 and n_corse_die_media < 6.0:
        return TipoSegmento.LINEARE

    # MISTO: pattern complesso, scope futuro raffinare
    return TipoSegmento.MISTO


def identifica_segmenti_da_corse(
    corse_per_linea: dict[str, list[_CorsaLike]],
    *,
    n_giorni_perimetro: int,
    descrizioni_linea: dict[str, str] | None = None,
    vincoli_default: VincoliSosta | None = None,
    stazioni_sosta_notturna_per_linea: (
        dict[str, frozenset[str]] | None
    ) = None,
) -> list[Linea]:
    """Costruisce ``Linea`` con relativi ``SegmentoLinea`` da un
    raggruppamento di corse per ``codice_linea``.

    Algoritmo (sub-MR-D0, raffinato in MR-D1):
    1. Per ogni ``codice_linea`` nel mapping, raccoglie le corse.
    2. Identifica le coppie (origine, destinazione) distinte.
    3. **MR-D0 baseline**: 1 segmento per linea che aggrega tutte le
       coppie. ``capolinee`` = unione di tutte origine/destinazione
       distinte.
    4. **MR-D1 raffinerà**: split in segmenti separati quando la
       linea ha pattern multi-tronco (R31 completo vs R31 corto).

    Args:
        corse_per_linea: mapping ``codice_linea → lista corse``.
        n_giorni_perimetro: numero giorni del PdE (per media die).
        descrizioni_linea: opzionale, mapping ``codice_linea →
            descrizione human-readable``. Se assente, usa
            ``codice_linea`` come descrizione.
        vincoli_default: opzionale, vincoli di sosta default per
            tutti i segmenti. Se ``None``, usa ``VincoliSosta()``.
        stazioni_sosta_notturna_per_linea: opzionale, override
            stazioni sosta per linea (es. R31 → ``{ALES, MORTARA,
            MILANO_CERTOSA}``). Se assente per una linea, fallback
            a ``capolinee`` del segmento.

    Returns:
        lista di ``Linea`` ordinata alfabeticamente per
        ``codice_linea`` (determinismo).

    Raises:
        ValueError: se input incoerente (n_giorni < 1, corse senza
            linea, ecc.).

    NB scope MR-D0: 1 segmento per linea (semplificazione). MR-D1
    raffinerà splittando le linee multi-tronco. I test devono
    coprire questa baseline.
    """
    if n_giorni_perimetro < 1:
        raise ValueError(
            f"n_giorni_perimetro deve essere >= 1, "
            f"ricevuto {n_giorni_perimetro}"
        )

    descrizioni = descrizioni_linea or {}
    vincoli = vincoli_default or VincoliSosta()
    sosta_per_linea = stazioni_sosta_notturna_per_linea or {}

    linee: list[Linea] = []
    for codice_linea in sorted(corse_per_linea.keys()):
        corse = corse_per_linea[codice_linea]
        if not corse:
            continue

        capolinee = _coppia_capolinee(corse)
        if len(capolinee) < 2:
            # Defensive: una linea con < 2 capolinee è degenerata
            # (1 sola stazione = impossibile in PdE reale). Skippa
            # con warning silente — il caller può loggare.
            continue

        sosta_notturna = sosta_per_linea.get(codice_linea, capolinee)

        tipo = _classifica_tipo(
            corse, n_giorni_perimetro=n_giorni_perimetro
        )

        n_die = len(corse) / n_giorni_perimetro

        segmento = SegmentoLinea(
            codice=f"{codice_linea}_completo",
            tipo=tipo,
            capolinee=capolinee,
            stazioni_sosta_notturna=sosta_notturna,
            vincoli_sosta=vincoli,
            n_corse_per_die_media=n_die,
        )

        linea = Linea(
            codice_linea=codice_linea,
            descrizione=descrizioni.get(codice_linea, codice_linea),
            segmenti=(segmento,),
        )
        linee.append(linea)

    return linee


# =====================================================================
# Lookup helpers (per uso nel builder)
# =====================================================================


def trova_segmento_per_corsa(
    corsa: _CorsaLike,
    linee: Sequence[Linea],
) -> SegmentoLinea | None:
    """Ritorna il `SegmentoLinea` cui appartiene una corsa.

    Convenzione MR-D0: una corsa appartiene al segmento se:
    - il ``codice_linea`` della corsa matcha quello della `Linea`, AND
    - il ``codice_origine`` E il ``codice_destinazione`` sono
      entrambi nei `capolinee` del segmento OR sono coperti dal
      pattern delle corse del segmento (scope MR-D1: oggi
      semplificato).

    Per MR-D0 baseline: 1 segmento per linea, quindi basta il match
    `codice_linea`. Returns ``None`` se nessuna linea matcha.

    MR-D1 raffinerà la logica per linee multi-segmento.
    """
    for linea in linee:
        if linea.codice_linea != corsa.codice_linea:
            continue
        # MR-D0: 1 segmento per linea, ritorna il primo
        return linea.segmenti[0]
    return None


def raggruppa_corse_per_linea(
    corse: Sequence[_CorsaLike],
) -> dict[str, list[_CorsaLike]]:
    """Raggruppa una lista di corse per `codice_linea`.

    Helper di convenienza per il caller (`builder.py`) che
    tipicamente ha tutte le corse del perimetro e deve passarle a
    `identifica_segmenti_da_corse` raggruppate.
    """
    grouped: dict[str, list[_CorsaLike]] = defaultdict(list)
    for c in corse:
        grouped[c.codice_linea].append(c)
    return dict(grouped)


__all__ = [
    "Linea",
    "SegmentoLinea",
    "TipoSegmento",
    "VincoliSosta",
    "identifica_segmenti_da_corse",
    "raggruppa_corse_per_linea",
    "trova_segmento_per_corsa",
]
