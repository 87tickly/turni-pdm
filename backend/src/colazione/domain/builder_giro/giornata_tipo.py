"""Identificazione delle giornate-tipo del ciclo del convoglio (MR-1110
Step 2).

Decisione utente 2026-05-06 (entry TN-UPDATE 190 + 193): nuovo modulo
che sostituisce concettualmente la "concatenazione di giornate
consecutive di calendario" del builder v1 con la "identificazione di
fasi del ciclo del convoglio", coerentemente con il modello PDF
Trenord (turno 1110 di riferimento — 1 giornata-tipo G6 con 6 varianti
calendariali ricche).

Una **giornata-tipo** del turno è una *fase del ciclo* attraversata da
un convoglio. È identificata univocamente dalla **chiave 5-uple**
(D1 chiusa 2026-05-06):

    (materiale_tipo_codice, localita_codice, staz_inizio, staz_fine,
     codice_servizio_dominante)

dove:

- ``materiale_tipo_codice`` / ``localita_codice``: derivati dalla
  composizione assegnata alla catena (vedi ``composizione.py``).
  Il caller li passa esplicitamente in ``CatenaIstanza``.
- ``staz_inizio``: codice stazione della prima corsa della catena
  (= origine prima corsa, ignorando vuoti tecnici testa).
- ``staz_fine``: codice stazione dell'ultima corsa della catena
  (= destinazione ultima corsa, ignorando vuoti tecnici coda).
- ``codice_servizio_dominante``: il ``codice_linea`` più frequente fra
  le corse della catena (tie-break lessicografico). ``None`` se
  nessuna corsa ha ``codice_linea`` popolato.

**D1 fallback morbido**: catene con ``codice_servizio_dominante=None``
(= nessuna corsa con ``codice_linea`` valorizzato) **non frammentano**
in giornate-tipo "orfane senza servizio identificabile". Vengono
fuse con la giornata-tipo gemella (= stessi primi 4 campi della
chiave) che ha ``codice_servizio_dominante`` valorizzato. Se nessun
gemello esiste, la giornata-tipo "None" resta isolata.

**Filtro di significatività** (D3 default ``min_istanze=2``): le
giornate-tipo con meno di ``params.min_istanze`` istanze (= ridotta
copertura calendariale) sono scartate dall'output principale e
restituite separatamente come ``istanze_orfane``. Il caller le gestisce
come "corse residue" del programma (= servizi che il builder non è
riuscito a inquadrare in un ciclo riutilizzabile).

Il modulo è **DB-agnostic**: opera su ``CatenaPosizionata`` + ``data``
+ ``materiale_tipo_codice`` via duck-typing. Le corse della catena
devono esporre l'attributo opzionale ``codice_linea`` (``getattr``
fallback a ``None``); ``CorsaCommerciale`` ORM lo espone, le fixture
test possono ometterlo.

Output: due liste — ``GiornataTipo`` significative ordinate
deterministicamente per chiave, e ``CatenaIstanza`` orfane (giornate
sotto soglia significatività).

Vedi ``docs/MR-1110-DESIGN.md`` §2.1 (definizione giornata-tipo),
§4.2 (algoritmo Step 2), §8.2 (decisioni D1/D3 chiuse).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from colazione.domain.builder_giro.posizionamento import CatenaPosizionata

# =====================================================================
# Parametri + Output
# =====================================================================


@dataclass(frozen=True)
class ParamGiornataTipo:
    """Parametri per ``identifica_giornate_tipo``.

    Attributi:
        min_istanze: soglia di significatività (D3, default 2).
            Giornate-tipo con meno istanze finiscono nelle
            ``istanze_orfane`` invece di essere emesse come output
            principale.
    """

    min_istanze: int = 2


_DEFAULT_PARAM = ParamGiornataTipo()


@dataclass(frozen=True)
class CatenaIstanza:
    """Una catena posizionata applicata a una specifica data,
    arricchita col tipo materiale assegnato.

    L'unità di base che le giornate-tipo aggregano. Costruita dal
    caller a partire dall'output di ``costruisci_catene`` +
    ``posiziona_su_localita`` + assegnazione composizione di
    ``composizione.py``.

    Attributi:
        data: data calendaristica di applicazione di questa istanza.
        catena_posizionata: la catena vera e propria (corse + vuoti
            tecnici testa/coda).
        materiale_tipo_codice: codice del tipo materiale assegnato
            (es. ``ETR421``, ``ETR204``). Estratto dalla composizione
            del primo blocco della catena (mirror di
            ``aggregazione_a2._materiale_codice_giro`` ma noto
            esplicitamente al caller).
    """

    data: date
    catena_posizionata: CatenaPosizionata
    materiale_tipo_codice: str


@dataclass(frozen=True)
class GiornataTipo:
    """Una giornata-tipo del ciclo del convoglio (output Step 2).

    Identificata dalla chiave 5-uple D1. Contiene tutte le istanze
    (catena × data) raggruppate per quella chiave. Lo Step 3
    successivo (varianti calendariali — non in questo modulo) le
    raggruppa per sequenza-treni concrete in M ``VarianteCalendariale``.

    Attributi:
        materiale_tipo_codice: tipo materiale (parte 1 della chiave).
        localita_codice: sede manutenzione (parte 2 della chiave).
        staz_inizio: stazione di inizio fase (parte 3 della chiave).
        staz_fine: stazione di fine fase (parte 4 della chiave).
        codice_servizio_dominante: codice servizio commerciale
            dominante della catena, ``None`` se non determinabile
            (parte 5 della chiave). Vedi
            ``_codice_servizio_dominante`` per il calcolo.
        istanze: tuple ordinata per data delle istanze appartenenti
            alla giornata-tipo. Min ``params.min_istanze`` per
            costruzione (giornate sotto-soglia sono in
            ``istanze_orfane``).
    """

    materiale_tipo_codice: str
    localita_codice: str
    staz_inizio: str
    staz_fine: str
    codice_servizio_dominante: str | None
    istanze: tuple[CatenaIstanza, ...]


# Alias di tipo per leggibilità interna.
_Chiave5 = tuple[str, str, str, str, str | None]
_Prefix4 = tuple[str, str, str, str]


# =====================================================================
# Helpers privati
# =====================================================================


def _staz_inizio(cat_pos: CatenaPosizionata) -> str:
    """Stazione di inizio della fase della catena.

    = origine della prima corsa commerciale, **ignorando** il vuoto
    tecnico di testa (che è un posizionamento sede→stazione, non
    parte della "fase" del ciclo).
    """
    # ``Catena.corse`` è ``tuple[Any, ...]`` (duck-typing dell'ORM
    # ``CorsaCommerciale``): annotazione esplicita per mypy strict.
    codice: str = cat_pos.catena.corse[0].codice_origine
    return codice


def _staz_fine(cat_pos: CatenaPosizionata) -> str:
    """Stazione di fine della fase della catena.

    = destinazione dell'ultima corsa commerciale, **ignorando** il
    vuoto tecnico di coda (rientro stazione→sede).
    """
    codice: str = cat_pos.catena.corse[-1].codice_destinazione
    return codice


def _codice_servizio_dominante(cat_pos: CatenaPosizionata) -> str | None:
    """Codice servizio commerciale dominante della catena.

    Algoritmo (D1 chiusa 2026-05-06):

    1. Estrai ``codice_linea`` da ogni corsa della catena (via
       ``getattr`` con fallback ``None``).
    2. Filtra i ``None``.
    3. Se nessun codice valido → ``None`` (giornata-tipo "orfana di
       servizio", gestita dal fallback morbido in
       ``_fondi_orfani_servizio``).
    4. Conta le occorrenze di ogni codice.
    5. Sceglie il codice con frequenza massima. Se più codici hanno
       la stessa frequenza, **tie-break lessicografico ascendente**
       (deterministico).

    Esempi:

    - Catena con 1 corsa S5 → ``"S5"``.
    - Catena con 3 corse [S5, S5, S7] → ``"S5"`` (S5 più frequente).
    - Catena con 2 corse [S5, S7] → ``"S5"`` (tie-break
      lessicografico).
    - Catena con 2 corse [None, None] → ``None``.
    - Catena con 2 corse [S5, None] → ``"S5"`` (None ignorato).
    """
    codici_validi: list[str] = []
    for c in cat_pos.catena.corse:
        cl = getattr(c, "codice_linea", None)
        if cl is not None:
            codici_validi.append(cl)

    if not codici_validi:
        return None

    counter: Counter[str] = Counter(codici_validi)
    massima_freq = max(counter.values())
    candidati = sorted(c for c, n in counter.items() if n == massima_freq)
    return candidati[0]


def _fondi_orfani_servizio(
    per_chiave: dict[_Chiave5, list[CatenaIstanza]],
) -> dict[_Chiave5, list[CatenaIstanza]]:
    """Fallback morbido D1: fonde gruppi con servizio ``None`` in
    gruppi gemelli (= stessi primi 4 campi) con servizio valorizzato.

    Algoritmo:

    1. Separa le chiavi con ``codice_servizio_dominante=None``
       (orfane) da quelle con servizio valorizzato (normali).
    2. Indicizza le chiavi normali per prefix 4-uple (i primi 4 campi
       della chiave).
    3. Per ogni orfana:
       - Se esistono gemelli (stessi 4 prefix) con servizio
         valorizzato, fondi le istanze nell'**unico** gruppo gemello
         lessicograficamente minimo per ``codice_servizio_dominante``
         (deterministico).
       - Altrimenti, lascia l'orfana invariata (resta come gruppo
         con servizio ``None``).

    Conseguenza: niente frammentazione di giornate-tipo dovuta a
    catene con servizio non identificabile. La gemella "principale"
    (= servizio dominante) assorbe l'orfana.
    """
    chiavi_orfane: list[_Chiave5] = [k for k in per_chiave if k[4] is None]
    chiavi_normali: list[_Chiave5] = [k for k in per_chiave if k[4] is not None]

    # Indice per prefix 4-uple. Le liste sono ordinate per chiave[4]
    # ascendente, così target di fusione = lista[0] è il
    # lessicograficamente minimo.
    per_prefix: dict[_Prefix4, list[_Chiave5]] = {}
    for k in chiavi_normali:
        prefix: _Prefix4 = (k[0], k[1], k[2], k[3])
        per_prefix.setdefault(prefix, []).append(k)
    for lista in per_prefix.values():
        # Tipato come list[_Chiave5] dove k[4] qui è sempre str (non
        # None): cast esplicito per mypy strict.
        lista.sort(key=lambda k: k[4] or "")

    risultato: dict[_Chiave5, list[CatenaIstanza]] = {}
    # Copia (shallow) le chiavi normali. Le orfane ci aggiungono
    # eventualmente sopra.
    for k in chiavi_normali:
        risultato[k] = list(per_chiave[k])

    for k_orfana in chiavi_orfane:
        prefix_o: _Prefix4 = (k_orfana[0], k_orfana[1], k_orfana[2], k_orfana[3])
        gemelli = per_prefix.get(prefix_o, [])
        if gemelli:
            target = gemelli[0]
            risultato[target].extend(per_chiave[k_orfana])
        else:
            # Niente gemelli: l'orfana resta isolata.
            risultato[k_orfana] = list(per_chiave[k_orfana])

    return risultato


# =====================================================================
# API pubblica
# =====================================================================


def identifica_giornate_tipo(
    istanze: list[CatenaIstanza],
    params: ParamGiornataTipo = _DEFAULT_PARAM,
) -> tuple[list[GiornataTipo], list[CatenaIstanza]]:
    """Identifica le giornate-tipo del ciclo dalle catene-istanza.

    Implementa lo Step 2 del nuovo builder MR-1110 (vedi
    ``docs/MR-1110-DESIGN.md`` §4.2).

    Pipeline:

    1. Per ogni ``CatenaIstanza``, calcola la chiave 5-uple D1
       ``(materiale, sede, staz_inizio, staz_fine, servizio_dominante)``.
    2. Raggruppa le istanze per chiave.
    3. Applica il fallback morbido D1: fondi gruppi con
       ``servizio_dominante=None`` in gemelli con servizio
       valorizzato (vedi ``_fondi_orfani_servizio``).
    4. Filtra per significatività (D3): gruppi con
       ``len(istanze) < params.min_istanze`` finiscono nelle
       ``istanze_orfane``.
    5. Ordina output deterministicamente per chiave.

    Args:
        istanze: lista di ``CatenaIstanza`` (catena posizionata + data
            + materiale assegnato). Tipicamente prodotta dal caller
            componendo l'output di ``costruisci_catene`` +
            ``posiziona_su_localita`` + assegnazione di
            ``composizione.py``.
        params: parametri di soglia (default ``ParamGiornataTipo()``
            con ``min_istanze=2``).

    Returns:
        Tupla ``(giornate_tipo, istanze_orfane)``:

        - ``giornate_tipo``: lista di ``GiornataTipo``
          significative (≥ ``min_istanze`` istanze ciascuna), ordinata
          per chiave 5-uple ascendente.
        - ``istanze_orfane``: lista di ``CatenaIstanza`` scartate
          dal filtro di significatività. Restituite al caller per la
          gestione "corse residue" del programma materiale.

    Esempi:
        Lista vuota → output vuoto:

        >>> identifica_giornate_tipo([])
        ([], [])

        Una sola istanza con ``min_istanze=2`` → 0 giornate-tipo
        significative + 1 orfana:

        >>> # vedi test_giornata_tipo.py per esempi completi.
    """
    if not istanze:
        return ([], [])

    # Step 1-2: raggruppa per chiave 5-uple.
    per_chiave: dict[_Chiave5, list[CatenaIstanza]] = {}
    for ist in istanze:
        chiave: _Chiave5 = (
            ist.materiale_tipo_codice,
            ist.catena_posizionata.localita_codice,
            _staz_inizio(ist.catena_posizionata),
            _staz_fine(ist.catena_posizionata),
            _codice_servizio_dominante(ist.catena_posizionata),
        )
        per_chiave.setdefault(chiave, []).append(ist)

    # Step 3: fallback morbido D1.
    per_chiave = _fondi_orfani_servizio(per_chiave)

    # Step 4: filtro significatività + costruzione output.
    giornate_tipo: list[GiornataTipo] = []
    istanze_orfane: list[CatenaIstanza] = []

    for chiave, ist_chiave in per_chiave.items():
        if len(ist_chiave) < params.min_istanze:
            istanze_orfane.extend(ist_chiave)
            continue
        materiale, sede, staz_in, staz_out, servizio = chiave
        istanze_ordinate = tuple(sorted(ist_chiave, key=lambda i: i.data))
        giornate_tipo.append(
            GiornataTipo(
                materiale_tipo_codice=materiale,
                localita_codice=sede,
                staz_inizio=staz_in,
                staz_fine=staz_out,
                codice_servizio_dominante=servizio,
                istanze=istanze_ordinate,
            )
        )

    # Step 5: ordinamento deterministico per chiave (None ordina
    # come "" per consistenza tra Python versions, ma in pratica
    # tutte le tuple sono confrontabili dopo la fusione).
    giornate_tipo.sort(
        key=lambda gt: (
            gt.materiale_tipo_codice,
            gt.localita_codice,
            gt.staz_inizio,
            gt.staz_fine,
            gt.codice_servizio_dominante or "",
        )
    )

    # Anche istanze_orfane ordinate per data (utile al consumer per
    # diagnostica).
    istanze_orfane.sort(key=lambda i: i.data)

    return (giornate_tipo, istanze_orfane)
