"""Analisi pattern di servizio per linea (Sprint 8.2 MR-D1).

Sprint 8.2 Plan-D, raffina la baseline MR-D0
(``identifica_segmenti_da_corse``) splittando le linee multi-tronco
in più ``SegmentoLinea`` distinti.

# Perché serve

MR-D0 produce 1 segmento per linea. Funziona per linee con un solo
pattern di servizio (es. navetta S01860↔S01074 round-trip), ma è
insufficiente per linee con sotto-pattern operativi distinti:

- **R31 multi-tronco**: corse complete ALES → MORTARA → MILANO + corse
  corte ALES → MORTARA. Sono pattern operativi DIVERSI: il convoglio
  che fa solo ALES↔MORTARA ha un turno più corto, sosta in MORTARA
  invece che in MILANO, e probabilmente è materiale dedicato.

- **Linee con servizio scolastico vs ordinario**: stesse stazioni ma
  fasce orarie diverse → MR-D0.5 lo classifica per calendario, ma
  qui aggiungiamo la dimensione "tronco" geografica.

Senza split in segmenti, MR-D2 (assegna_convogli) confonderebbe
corse complete e corte assegnando lo stesso convoglio a entrambe
(= servizio operativamente illegale).

# Algoritmo

Per ogni linea con corse:

1. **Conta coppie (origine, destinazione)** distinte presenti.
2. **Identifica capolinee** = stazioni che appaiono come origine OR
   destinazione di tutte le coppie principali (= stazioni con grado
   massimo nel grafo della linea).
3. **Classifica ogni coppia**:
   - **principale**: tocca entrambi i capolinee globali (es. R31
     ALES↔MILANO).
   - **tronco**: tocca un capolinea + una stazione intermedia (es.
     R31 ALES↔MORTARA).
4. **Crea segmenti**:
   - 1 segmento "principale" per le coppie principali (se ce ne sono).
   - 1 segmento per ogni gruppo coppie tronco con stesso capolinea
     condiviso.
5. **Se la linea ha un solo pattern** (es. navetta): output identico
   a MR-D0 baseline (1 segmento). Backward compat.

# Naming dei segmenti

- segmento principale: ``{codice_linea}_completo`` (es. ``R31_completo``)
- segmento tronco con capolinea X: ``{codice_linea}_tronco_{X}`` dove
  X è il capolinea condiviso (es. ``R31_tronco_S00470`` per il
  tronco ALES-MORTARA che condivide ALES col completo).

# Cosa NON fa MR-D1

- Non raffinata classificazione `TipoSegmento` oltre la baseline di
  ``_classifica_tipo`` di MR-D0 (NAVETTA / LINEARE / MISTO).
- Non gestisce calendari diversi per segmento (è scope MR-D0.5).
- Non sceglie sosta notturna (default = capolinee del segmento, può
  essere overridden con ``stazioni_sosta_notturna_per_segmento``).

DB-agnostic come MR-D0.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from colazione.domain.builder_giro.definizione_linea import (
    Linea,
    SegmentoLinea,
    VincoliSosta,
    _classifica_tipo,
    _CorsaLike,
)

# =====================================================================
# Helpers
# =====================================================================


def _normalizza_coppia(o: str, d: str) -> tuple[str, str]:
    """Coppia ordinata alfabeticamente (per simmetria A↔B).

    Una corsa A→B e una corsa B→A sono lo stesso pattern di
    servizio: hanno gli stessi capolinea, stessa rotta. Normalizziamo
    ordinando alfabeticamente.
    """
    return (o, d) if o <= d else (d, o)


def _identifica_capolinee_globali(
    coppie_normalizzate: Sequence[tuple[str, str]],
) -> tuple[str, str] | None:
    """Identifica i 2 capolinee "globali" della linea.

    Un capolinea è una stazione con frequenza di apparizione più
    alta nelle coppie. Se le 2 stazioni più frequenti compaiono in
    una coppia comune, sono i capolinee globali (linea con pattern
    principale chiaro).

    Tie-break deterministico: a parità di frequenza, ordina
    alfabeticamente (= determina il "principale" per ordine
    alfabetico stazione).

    Ritorna ``None`` se la linea non ha un pattern principale
    identificabile (es. tutte coppie disgiunte, o meno di 2
    stazioni distinte).
    """
    if not coppie_normalizzate:
        return None
    freq: Counter[str] = Counter()
    for a, b in coppie_normalizzate:
        freq[a] += 1
        freq[b] += 1
    # Ordina per (-freq desc, codice asc) per determinismo cross-run
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    top_2 = [staz for staz, _ in ranked[:2]]
    if len(top_2) < 2:
        return None
    cap_a, cap_b = sorted(top_2)
    # Verifica: la coppia (cap_a, cap_b) appare?
    if (cap_a, cap_b) in set(coppie_normalizzate):
        return cap_a, cap_b
    return None


def _classifica_coppia(
    coppia: tuple[str, str],
    capolinee_globali: tuple[str, str] | None,
) -> tuple[str, str | None]:
    """Classifica una coppia rispetto ai capolinee globali.

    Returns:
        Tuple ``(categoria, capolinea_condiviso)``:
        - ``("principale", None)``: la coppia coincide con i capolinee
          globali.
        - ``("tronco", X)``: la coppia tocca esattamente un capolinea
          globale (X = quel capolinea) + una intermedia.
        - ``("isolata", None)``: la coppia non tocca nessun capolinea
          globale (raro: pattern sub-tronco senza connessione).
    """
    if capolinee_globali is None:
        return "isolata", None
    a, b = coppia
    cap_a, cap_b = capolinee_globali
    if (a, b) == (cap_a, cap_b):
        return "principale", None
    if a == cap_a or b == cap_a:
        return "tronco", cap_a
    if a == cap_b or b == cap_b:
        return "tronco", cap_b
    return "isolata", None


# =====================================================================
# Algoritmo principale
# =====================================================================


def analizza_linea_e_splitta_segmenti(
    codice_linea: str,
    corse: Sequence[_CorsaLike],
    *,
    n_giorni_perimetro: int,
    descrizione: str | None = None,
    vincoli_default: VincoliSosta | None = None,
    stazioni_sosta_notturna_per_segmento: (
        dict[str, frozenset[str]] | None
    ) = None,
) -> Linea | None:
    """Analizza una linea e produce ``Linea`` con 1+ ``SegmentoLinea``.

    Differenze da ``identifica_segmenti_da_corse`` di MR-D0:
    - splitta in 2+ segmenti se la linea ha pattern multi-tronco
    - usa solo capolinee globali (non simmetria + asimmetria mista)

    Args:
        codice_linea: codice della linea (es. ``"R31"``).
        corse: corse della linea.
        n_giorni_perimetro: giorni del periodo PdE (per media).
        descrizione: descrizione human-readable (default = codice_linea).
        vincoli_default: vincoli di sosta default per i segmenti.
        stazioni_sosta_notturna_per_segmento: override mapping
            ``codice_segmento → frozenset[stazione]``. Se assente,
            sosta notturna = capolinee del segmento.

    Returns:
        ``Linea`` con 1+ segmenti, oppure ``None`` se la linea è
        degenerata (no corse, o capolinee non identificabili).

    Esempi:
    - R31 con sole coppie ALES↔MILANO → 1 segmento
      ``R31_completo`` con capolinee ``{ALES, MILANO}``.
    - R31 con coppie ALES↔MILANO + ALES↔MORTARA → 2 segmenti:
      - ``R31_completo`` con capolinee ``{ALES, MILANO}``
      - ``R31_tronco_S00470`` (= tronco condividendo ALES) con
        capolinee ``{ALES, MORTARA}``
    """
    if not corse:
        return None
    if n_giorni_perimetro < 1:
        raise ValueError(
            f"n_giorni_perimetro deve essere >= 1, "
            f"ricevuto {n_giorni_perimetro}"
        )

    vincoli = vincoli_default or VincoliSosta()
    sosta_override = stazioni_sosta_notturna_per_segmento or {}
    descr = descrizione or codice_linea

    # Step 1: estrai coppie normalizzate
    coppie_per_corsa = [
        _normalizza_coppia(c.codice_origine, c.codice_destinazione)
        for c in corse
    ]
    # Determinismo: sort esplicito (set è non-deterministico cross-run)
    coppie_uniche = sorted(set(coppie_per_corsa))

    # Step 2: capolinee globali
    capolinee_glob = _identifica_capolinee_globali(coppie_uniche)

    # Caso degenerato: nessun capolinea identificabile (1 sola
    # stazione, o coppie completamente disgiunte). Fallback baseline
    # MR-D0 (1 segmento con tutte le stazioni come capolinee).
    if capolinee_glob is None:
        capolinee_all: set[str] = set()
        for a, b in coppie_uniche:
            capolinee_all.add(a)
            capolinee_all.add(b)
        if len(capolinee_all) < 2:
            return None
        codice_seg = f"{codice_linea}_completo"
        sosta = sosta_override.get(
            codice_seg, frozenset(capolinee_all)
        )
        seg = SegmentoLinea(
            codice=codice_seg,
            tipo=_classifica_tipo(
                corse, n_giorni_perimetro=n_giorni_perimetro
            ),
            capolinee=frozenset(capolinee_all),
            stazioni_sosta_notturna=sosta,
            vincoli_sosta=vincoli,
            n_corse_per_die_media=len(corse) / n_giorni_perimetro,
        )
        return Linea(
            codice_linea=codice_linea,
            descrizione=descr,
            segmenti=(seg,),
        )

    # Step 3: classifica ogni coppia
    cap_a, cap_b = capolinee_glob
    coppie_principali: list[tuple[str, str]] = []
    coppie_tronco_per_capolinea: dict[str, list[tuple[str, str]]] = (
        defaultdict(list)
    )
    coppie_isolate: list[tuple[str, str]] = []
    for coppia in coppie_uniche:
        cat, cap_cond = _classifica_coppia(coppia, capolinee_glob)
        if cat == "principale":
            coppie_principali.append(coppia)
        elif cat == "tronco" and cap_cond is not None:
            coppie_tronco_per_capolinea[cap_cond].append(coppia)
        else:
            # Pattern senza connessione coi capolinee globali: linea
            # operativa secondaria (raro, ma esistente per linee con
            # branche disgiunte). Crea segmento isolato dedicato.
            coppie_isolate.append(coppia)

    # Step 4: raggruppa corse per segmento
    corse_per_coppia: dict[tuple[str, str], list[_CorsaLike]] = defaultdict(list)
    for c, coppia in zip(corse, coppie_per_corsa, strict=True):
        corse_per_coppia[coppia].append(c)

    segmenti: list[SegmentoLinea] = []

    # Segmento principale (se esistono coppie principali)
    if coppie_principali:
        corse_principali = [
            c
            for coppia in coppie_principali
            for c in corse_per_coppia[coppia]
        ]
        codice_seg = f"{codice_linea}_completo"
        sosta = sosta_override.get(
            codice_seg, frozenset({cap_a, cap_b})
        )
        segmenti.append(
            SegmentoLinea(
                codice=codice_seg,
                tipo=_classifica_tipo(
                    corse_principali,
                    n_giorni_perimetro=n_giorni_perimetro,
                ),
                capolinee=frozenset({cap_a, cap_b}),
                stazioni_sosta_notturna=sosta,
                vincoli_sosta=vincoli,
                n_corse_per_die_media=(
                    len(corse_principali) / n_giorni_perimetro
                ),
            )
        )

    # Segmenti tronco: 1 per capolinea condiviso (= cap_a o cap_b)
    for cap_cond in sorted(coppie_tronco_per_capolinea.keys()):
        coppie_tronco = coppie_tronco_per_capolinea[cap_cond]
        corse_tronco = [
            c
            for coppia in coppie_tronco
            for c in corse_per_coppia[coppia]
        ]
        # Stazioni del segmento tronco = unione di tutte le stazioni
        # delle coppie tronco
        capolinee_tronco: set[str] = {cap_cond}
        for coppia in coppie_tronco:
            capolinee_tronco.add(coppia[0])
            capolinee_tronco.add(coppia[1])
        codice_seg = f"{codice_linea}_tronco_{cap_cond}"
        sosta = sosta_override.get(
            codice_seg, frozenset(capolinee_tronco)
        )
        segmenti.append(
            SegmentoLinea(
                codice=codice_seg,
                tipo=_classifica_tipo(
                    corse_tronco,
                    n_giorni_perimetro=n_giorni_perimetro,
                ),
                capolinee=frozenset(capolinee_tronco),
                stazioni_sosta_notturna=sosta,
                vincoli_sosta=vincoli,
                n_corse_per_die_media=(
                    len(corse_tronco) / n_giorni_perimetro
                ),
            )
        )

    # Segmenti isolati: 1 per ogni coppia disgiunta dai capolinee
    # globali. Ordinamento alfabetico per determinismo.
    for coppia_isolata in sorted(coppie_isolate):
        a_iso, b_iso = sorted(coppia_isolata)
        codice_seg = f"{codice_linea}_isolato_{a_iso}_{b_iso}"
        capolinee_iso = frozenset({a_iso, b_iso})
        sosta = sosta_override.get(codice_seg, capolinee_iso)
        corse_iso = corse_per_coppia[coppia_isolata]
        segmenti.append(
            SegmentoLinea(
                codice=codice_seg,
                tipo=_classifica_tipo(
                    corse_iso, n_giorni_perimetro=n_giorni_perimetro
                ),
                capolinee=capolinee_iso,
                stazioni_sosta_notturna=sosta,
                vincoli_sosta=vincoli,
                n_corse_per_die_media=(
                    len(corse_iso) / n_giorni_perimetro
                ),
            )
        )

    # Defensive: se nessun segmento è stato creato (caso impossibile
    # raggiunto ora che coppie_isolate è gestito, ma defensive
    # programming), fallback a baseline 1 segmento
    if not segmenti:
        capolinee_all = set()
        for a, b in coppie_uniche:
            capolinee_all.add(a)
            capolinee_all.add(b)
        codice_seg = f"{codice_linea}_completo"
        sosta = sosta_override.get(
            codice_seg, frozenset(capolinee_all)
        )
        segmenti.append(
            SegmentoLinea(
                codice=codice_seg,
                tipo=_classifica_tipo(
                    corse, n_giorni_perimetro=n_giorni_perimetro
                ),
                capolinee=frozenset(capolinee_all),
                stazioni_sosta_notturna=sosta,
                vincoli_sosta=vincoli,
                n_corse_per_die_media=len(corse) / n_giorni_perimetro,
            )
        )

    return Linea(
        codice_linea=codice_linea,
        descrizione=descr,
        segmenti=tuple(segmenti),
    )


def analizza_linee_da_corse(
    corse_per_linea: dict[str, list[_CorsaLike]],
    *,
    n_giorni_perimetro: int,
    descrizioni_linea: dict[str, str] | None = None,
    vincoli_default: VincoliSosta | None = None,
    stazioni_sosta_notturna_per_segmento: (
        dict[str, frozenset[str]] | None
    ) = None,
) -> list[Linea]:
    """Versione raffinata di ``identifica_segmenti_da_corse`` di MR-D0.

    Per ogni linea, applica
    ``analizza_linea_e_splitta_segmenti`` per produrre 1+
    ``SegmentoLinea`` distinti.

    Output ordinato alfabeticamente per ``codice_linea``
    (determinismo).
    """
    if n_giorni_perimetro < 1:
        raise ValueError(
            f"n_giorni_perimetro deve essere >= 1, "
            f"ricevuto {n_giorni_perimetro}"
        )

    descrizioni = descrizioni_linea or {}
    out: list[Linea] = []
    for codice_linea in sorted(corse_per_linea.keys()):
        corse = corse_per_linea[codice_linea]
        if not corse:
            continue
        linea = analizza_linea_e_splitta_segmenti(
            codice_linea,
            corse,
            n_giorni_perimetro=n_giorni_perimetro,
            descrizione=descrizioni.get(codice_linea),
            vincoli_default=vincoli_default,
            stazioni_sosta_notturna_per_segmento=(
                stazioni_sosta_notturna_per_segmento
            ),
        )
        if linea is not None:
            out.append(linea)
    return out


__all__ = [
    "analizza_linea_e_splitta_segmenti",
    "analizza_linee_da_corse",
]
