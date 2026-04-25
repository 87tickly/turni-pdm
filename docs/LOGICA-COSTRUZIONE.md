# LOGICA DI COSTRUZIONE — algoritmi nativi (draft v0.1)

> Specifica algoritmica del cuore generativo del programma. Tre
> algoritmi:
> 1. **PdE → Giro Materiale**: dato l'orario commerciale + dotazione
>    materiale, costruisce le rotazioni dei convogli fisici
> 2. **Giro Materiale → Turno PdC**: dato il giro materiale + depositi
>    PdC + normativa, costruisce i turni del personale
> 3. **Revisione provvisoria con cascading**: dato un evento esterno
>    (RFI/sciopero), modifica giro materiale e propaga su turno PdC
>
> **Fonte regole normative**: `docs/NORMATIVA-PDC.md` (1292 righe).
> Questo documento **applica** quelle regole, non le ridefinisce.
>
> **Riferimenti storici**: `docs/ALGORITMO-BUILDER.md` e
> `docs/ARCHITETTURA-BUILDER-V4.md` contengono versioni precedenti
> della stessa logica scritte per il vecchio progetto. Resta utile
> consultarli per dettagli normativi (preriscaldo, tempi vettura,
> stazioni CV §9.2 ammesse).

---

## Indice

1. [Principi guida](#1-principi-guida)
2. [Input e output dei tre algoritmi](#2-input-e-output)
3. [Algoritmo A — PdE → Giro Materiale](#3-algoritmo-a--pde--giro-materiale)
4. [Algoritmo B — Giro Materiale → Turno PdC](#4-algoritmo-b--giro-materiale--turno-pdc)
5. [Algoritmo C — Revisione provvisoria + cascading](#5-algoritmo-c--revisione-provvisoria--cascading)
6. [Validazione e scoring](#6-validazione-e-scoring)
7. [Mapping su moduli Python](#7-mapping-su-moduli-python)
8. [Edge case noti](#8-edge-case-noti)

---

## 1. Principi guida

### 1.1 Costruzione, non lettura

I tre algoritmi sono **generatori**, non parser. Producono dati nuovi
a partire da regole + input strutturati. Niente parsing PDF, niente
scraping. L'unico input è il PdE (Numbers/Excel) — già strutturato.

### 1.2 Determinismo + ottimizzazione

Per gli stessi input + gli stessi parametri, lo stesso output. Se
serve **ottimizzazione** (es. migliore copertura tra più soluzioni
candidate), si fa con `random_seed` esposto come parametro: i 25
tentativi del builder PdC partono da seed deterministico.

### 1.3 Validabilità a ogni passo

Ogni output passa per un **validatore** che applica i vincoli rigidi
della normativa. Se l'output non è valido, non si "ammorbidisce" il
validatore — si scarta o si reitera. La normativa non si negozia.

### 1.4 Tracciabilità

Ogni `giro_materiale` e ogni `turno_pdc` generato porta in metadata
**come è stato generato**: parametri input, versione algoritmo,
timestamp, seed. Permette di rigenerare deterministicamente per debug.

### 1.5 Algoritmi puri (DB-agnostic)

Gli algoritmi vivono in `backend/src/colazione/domain/`, ricevono
dataclass/dict, ritornano dataclass/dict. **Non** parlano direttamente
con SQLAlchemy. Le funzioni di conversione DB ↔ dominio sono separate.
Questo permette test unitari veloci e portabilità.

---

## 2. Input e output

### Algoritmo A — PdE → Giro Materiale

**Input**:
```python
@dataclass
class InputAlgoritmoA:
    corse: list[CorsaCommerciale]               # tutte le corse del PdE per una azienda
    localita_manutenzione: list[LocalitaMan]    # i 7 depositi Trenord (o altri per altre aziende)
    dotazione: list[DotazioneRotabile]          # tipi pezzo + quantità per località
    giorno_tipo: GiornoTipo                     # 'feriale' | 'sabato' | 'festivo'
    azienda_id: int
    parametri: ParamGiroBuilder = ...           # tempo manovra min, ecc.
```

**Output**:
```python
@dataclass
class OutputAlgoritmoA:
    giri: list[GiroMateriale]   # ciascuno con N giornate × M varianti × blocchi
    corse_residue: list[Corsa]  # corse non coperte (errore se non vuoto)
    materiali_vuoti_generati: list[CorsaMaterialeVuoto]  # i numeri tipo U316, 28183...
    metadata: GenerazioneMetadata
```

### Algoritmo B — Giro Materiale → Turno PdC

**Input**:
```python
@dataclass
class InputAlgoritmoB:
    giri: list[GiroMateriale]                   # quelli pubblicati
    depositi_pdc: list[Depot]                   # i 25 depositi personale Trenord
    abilitazioni: list[DepotEnabledLine]        # quale deposito copre quali linee
    normativa: NormativaConfig                  # config azienda (8h30, 5h30, ecc.)
    giorno_tipo: GiornoTipo
    azienda_id: int
    parametri: ParamPdCBuilder = ...
```

**Output**:
```python
@dataclass
class OutputAlgoritmoB:
    turni_pdc: list[TurnoPdC]                   # ciascuno con N giornate × blocchi
    materiale_residuo: list[GiroBlocco]         # corse del giro non coperte (errore)
    metadata: GenerazioneMetadata
```

### Algoritmo C — Revisione provvisoria + cascading

**Input**:
```python
@dataclass
class InputAlgoritmoC:
    causa: CausaRevisione                       # 'interruzione_rfi' | 'sciopero' | ...
    finestra_da: date
    finestra_a: date
    giri_impattati: list[GiroMateriale]         # giri di base coinvolti
    delta_corse: list[DeltaCorsa]               # corse soppresse / sostituite / aggiunte
    comunicazione_esterna_rif: str              # 'PIR-2026-345'
    descrizione_evento: str
```

**Output**:
```python
@dataclass
class OutputAlgoritmoC:
    revisione_giro: RevisioneProvvisoria        # entità nuova
    blocchi_modificati: list[RevisioneBloccoModif]
    revisioni_pdc_cascading: list[RevisioneProvvisoriaPdC]
    notifiche: list[NotificaCascading]
```

---

## 3. Algoritmo A — PdE → Giro Materiale

### 3.1 Visione d'insieme

Dato un elenco di corse commerciali per un giorno-tipo (feriale, ad
es.), costruisce una lista di **giri materiali** dove ogni giro
copre una sequenza ordinata di corse, rispettando:

1. **Continuità geografica**: l'arrivo di una corsa = la partenza
   della successiva, oppure tra le due c'è una `corsa_materiale_vuoto`
   generata per posizionare il convoglio
2. **Tempo manovra minimo**: tra due corse consecutive c'è un gap
   minimo (default 5 min in stazione capolinea, 15 in stazione
   intermedia, 20 in deposito)
3. **Compatibilità materiale**: tutte le corse del giro richiedono
   lo **stesso tipo di composizione** (es. tutte "Coradia 526" o
   tutte "Vivalto"). Switch di composizione fra giorni diversi del
   ciclo è ammesso, **dentro la stessa giornata** no
4. **Ciclo chiuso a località manutenzione**: il giro inizia e finisce
   nella stessa località manutenzione. Se non torna naturalmente, si
   genera un `corsa_materiale_vuoto` di rientro
5. **Capacità materiale**: la quantità di pezzi del tipo richiesto
   nella località manutenzione deve essere ≥ N giornate del giro

### 3.2 Pseudo-codice

```python
def costruisci_giri_materiali(input: InputAlgoritmoA) -> OutputAlgoritmoA:
    # Step 1: Raggruppa corse per tipo materiale richiesto
    corse_per_tipo = group_by(input.corse, key=lambda c: c.tipologia_treno_richiesta)

    giri_costruiti = []

    for tipo_materiale, corse_di_questo_tipo in corse_per_tipo.items():
        # Step 2: Identifica località manutenzione candidate
        loc_candidate = [
            loc for loc in input.localita_manutenzione
            if has_dotazione(loc, tipo_materiale, input.dotazione)
        ]

        # Step 3: Per ogni località, costruisci giri partendo da lì
        for loc in loc_candidate:
            corse_assegnate_a_loc = filter_corse_by_localita(
                corse_di_questo_tipo, loc
            )
            giri_da_loc = costruisci_giri_da_localita(
                corse_assegnate_a_loc, loc, tipo_materiale, input.parametri
            )
            giri_costruiti.extend(giri_da_loc)

    # Step 4: Verifica copertura
    corse_residue = corse_non_coperte(input.corse, giri_costruiti)
    if corse_residue:
        # Soluzione non completa: alcune corse non hanno trovato un giro
        log_warning(f"{len(corse_residue)} corse non coperte")

    return OutputAlgoritmoA(
        giri=giri_costruiti,
        corse_residue=corse_residue,
        materiali_vuoti_generati=collect_vuoti(giri_costruiti),
        metadata=...
    )


def costruisci_giri_da_localita(corse, localita, tipo_materiale, params):
    """
    Ordina corse per orario di partenza.
    Greedy: prima corsa libera → costruisci catena → ripeti.
    """
    corse_ordinate = sorted(corse, key=lambda c: c.ora_partenza)
    pool = list(corse_ordinate)
    giri = []

    while pool:
        prima_corsa = pool.pop(0)
        giro = nuovo_giro(localita, tipo_materiale)

        # Posizionamento iniziale: dalla località manutenzione alla
        # stazione di partenza della prima corsa
        if prima_corsa.codice_origine != localita.stazione_collegata_codice:
            vuoto = genera_materiale_vuoto(
                da=localita.stazione_collegata_codice,
                a=prima_corsa.codice_origine,
                arrivo_max=prima_corsa.ora_partenza - params.gap_min,
                origine='generato_da_giro_materiale',
            )
            giro.aggiungi_blocco(vuoto)

        giro.aggiungi_blocco(prima_corsa)
        cursore = prima_corsa.ora_arrivo
        ultima_stazione = prima_corsa.codice_destinazione

        # Loop catena
        while True:
            prossima = trova_prossima_corsa(
                pool, da_stazione=ultima_stazione, dopo_orario=cursore + params.gap_min
            )
            if prossima is None:
                break
            pool.remove(prossima)
            giro.aggiungi_blocco(prossima)
            cursore = prossima.ora_arrivo
            ultima_stazione = prossima.codice_destinazione

        # Rientro a località
        if ultima_stazione != localita.stazione_collegata_codice:
            vuoto_rientro = genera_materiale_vuoto(
                da=ultima_stazione,
                a=localita.stazione_collegata_codice,
                partenza_min=cursore + params.gap_min,
                origine='generato_da_giro_materiale',
            )
            giro.aggiungi_blocco(vuoto_rientro)

        giri.append(giro)

    return giri
```

### 3.3 Vincoli da rispettare

1. **Tempo manovra minimo**: parametro `gap_min`. Default per Trenord
   da definire (proposta: 5' capolinea, 15' intermedia, 20' deposito).
2. **No sovrapposizione**: una stessa corsa non può apparire in due
   giri diversi.
3. **Ciclo chiuso**: ogni giro inizia e finisce nella stessa
   `localita_manutenzione`.
4. **Composizione coerente**: tutti i blocchi di una giornata del giro
   condividono lo stesso `tipo_materiale`.
5. **Capacità località**: la quantità totale di pezzi del tipo nella
   località manutenzione deve essere ≥ alla quantità necessaria per N
   giornate (configurabile).

### 3.4 Multi-giornata e varianti calendario

L'algoritmo descritto sopra costruisce **una giornata-tipo** del
giro. Per costruire un ciclo completo (es. 2 giornate per Turno 1100,
10 giornate per Turno 1101):

1. Si esegue per ogni `giorno_tipo` (feriale, sabato, festivo)
2. Si raggruppano i giri risultanti per "compatibilità ciclica"
   (sequenza che si chiude → ciclo)
3. Si numerano le giornate (G1, G2, …) e si associano `giro_giornata`
4. Per ogni giornata, si crea `giro_variante` con `validita_dates_apply`
   e `validita_dates_skip` derivati da PdE periodicità

### 3.5 Output di esempio

Per input PdE Trenord (10580 corse) ci si aspetta in output ~50-150
giri materiali (ordine di grandezza Trenord reale: 54 turni nel PDF
01-04-2026).

---

## 4. Algoritmo B — Giro Materiale → Turno PdC

### 4.1 Visione d'insieme

Per ogni giornata di ogni giro materiale pubblicato, costruisce **i
turni PdC** che coprono quella giornata, rispettando la normativa
Trenord (vedi `NORMATIVA-PDC.md`).

**Architettura "centrata sulla condotta"** (riferimento:
`ARCHITETTURA-BUILDER-V4.md` storico):

- **NON** parti dal deposito PdC e concateni treni in condotta
- **SI** parti dai treni-condotta produttivi (1-2 treni totali 2-3h)
  e costruisci intorno il posizionamento (vettura) + rientro

Questa filosofia produce turni realistici tipo ALOR_C G2 (vedi
`CLAUDE.md` glossario), che il vecchio approccio "DFS dal deposito"
non riusciva a costruire.

### 4.2 Pseudo-codice top-level

```python
def costruisci_turni_pdc(input: InputAlgoritmoB) -> OutputAlgoritmoB:
    pool_blocchi = pool_giri_blocchi(input.giri, input.giorno_tipo)
    turni_costruiti = []

    while pool_blocchi non_vuota:
        # Step A: scegli un seed produttivo (1-2 treni, condotta 2-3h)
        seed = scegli_seed(pool_blocchi, input.parametri)
        if seed is None:
            break  # nessun seed produttivo possibile, esci

        # Step B-D: costruisci il turno intorno al seed
        turno = costruisci_turno_intorno_a_seed(
            seed, pool_blocchi, input.depositi_pdc, input.normativa
        )

        if turno.valido:
            pool_blocchi.rimuovi(turno.blocchi_consumati)
            turni_costruiti.append(turno)
        else:
            log_warning(f"Seed {seed} non costruibile: {turno.violazioni}")
            pool_blocchi.marca_problematico(seed)

    return OutputAlgoritmoB(
        turni_pdc=turni_costruiti,
        materiale_residuo=pool_blocchi.residui(),
        metadata=...
    )
```

### 4.3 Step A — Scelta del seed produttivo

**Definizione seed**: 1-2 corse commerciali con condotta totale 2h-3h
(target Trenord realistico, vedi `CLAUDE.md` "STRUTTURA VERA di un turno
PdC").

```python
def scegli_seed(pool, params):
    seeds_candidati = []

    for blocco in pool:
        if blocco.tipo == 'corsa_commerciale':
            durata = blocco.fine - blocco.inizio
            if 60 <= durata <= 180:  # 1-3h
                seeds_candidati.append([blocco])
            # Combina con eventuale 2° blocco
            for blocco2 in pool:
                if blocco2.inizio > blocco.fine and blocco2.codice_origine == blocco.codice_destinazione:
                    durata_totale = (blocco.fine - blocco.inizio) + (blocco2.fine - blocco2.inizio)
                    if 120 <= durata_totale <= 180:
                        seeds_candidati.append([blocco, blocco2])

    # Score: preferisci seed con condotta target ~2h30, prima del
    # mezzogiorno, deposito vicino disponibile
    return max(seeds_candidati, key=score_seed) if seeds_candidati else None
```

### 4.4 Step B — Posizionamento iniziale (deposito → seed.inizio)

Dal **deposito PdC** alla stazione di inizio del seed, in vettura
(treno passeggero passivo).

```python
def posizionamento(deposito, stazione_target, ora_target, normativa):
    # Cerca treni passivi che arrivano in stazione_target prima di
    # ora_target - tempo_minimo_cambio
    candidati = trova_corse_passeggero(
        partenza=deposito.stazione,
        arrivo=stazione_target,
        arrivo_max=ora_target - normativa.tempo_pre_seed_min  # default 5'
    )
    return scegli_migliore_per_orario(candidati)
```

**Priorità mezzi (vedi NORMATIVA §7.2)**:
1. Vettura su treno commerciale
2. MM (metropolitana) — solo se necessario
3. Taxi — ultima spiaggia o casi specifici (es. MI.PG ↔ FIOz §8.5.1)

### 4.5 Step C — Gap interni (REFEZ, vetture di connessione)

Tra le corse del seed (e fra seed e blocchi successivi), gap
intermedi. Tabella decisionale (vedi NORMATIVA §6):

| Gap | Trattamento |
|-----|-------------|
| < 65' | CV (richiede incontro 2 PdC) oppure PK (più flessibile) |
| 65'-300' | ACC (40' + 40') oppure PK |
| > 300' | ACC (default) oppure PK (opt-in) |

Inoltre, se il gap cade in **finestra refezione** (11:30-15:30 o
18:30-22:30) **e** la prestazione del turno > 360', si **inserisce
REFEZ** 30' (NORMATIVA §4.1).

### 4.6 Step D — Rientro al deposito

Dopo l'ultimo blocco condotta del seed, rientro al deposito:

1. **Già diretto**: l'ultimo treno del seed termina al deposito PdC →
   nessun rientro aggiuntivo
2. **Vettura passiva**: cerca un treno passeggeri verso il deposito
3. **Condotta di rientro**: se PdC abilitato, può guidare il treno di
   rientro (più produttivo)
4. **FR** (fuori residenza, NORMATIVA §10): se nessun rientro
   possibile senza sforare 8h30/cap, e la stazione di fine seed è in
   `pdc_fr_approved`, il PdC dorme fuori

### 4.7 Step E — Validazione finale

Vincoli rigidi (turno **scartato** se violati):

1. `prestazione ≤ cap_prest` (510' standard, 420' notte 01:00-04:59)
2. `condotta ≤ 330'` (5h30)
3. Se `prestazione > 360'`: REFEZ 30' obbligatoria in finestra
4. Accessori coerenti (ACCp/ACCa solo su condotta, non su vetture)
5. Gap gestiti (ogni gap ha un evento coerente col range)
6. CV in stazioni ammesse (NORMATIVA §9.2)
7. FR entro limiti mensili (1/settimana, 3/28gg)

Se tutti passano → turno valido. Si calcola **score** (vedi §6.2)
per ranking.

### 4.8 Validazione di ciclo (settimanale)

Una volta costruite tutte le giornate del turno (G1...G5 + 2 riposi):

1. Riposo intraturno ≥ 11h/14h/16h a seconda del tipo (NORMATIVA §11.5)
2. Riposo settimanale ≥ 62h con 2 giorni solari (NORMATIVA §11.4)
3. Distribuzione equa giornate "pesanti" (preferenze §11.7)

Se un ciclo non passa la validazione settimanale, si rigenera con
parametri diversi (random_seed alternativo).

---

## 5. Algoritmo C — Revisione provvisoria + cascading

### 5.1 Visione

Quando arriva un evento esterno che modifica l'esercizio (RFI comunica
interruzione, sciopero pianificato, manutenzione straordinaria),
applica la modifica:

1. Crea `revisione_provvisoria` per la finestra temporale
2. Modifica i `giro_blocco` impattati (modifica/cancella/aggiungi)
3. **Cascading**: per ogni giro modificato, identifica i `turno_pdc`
   che lo coprivano e crea `revisione_provvisoria_pdc` con la stessa
   finestra
4. **Re-builda** automaticamente i turni PdC nella finestra usando
   l'Algoritmo B sui giri-rev
5. **Notifica**: gestione personale per riassegnazione, personale PdC
   per cambio turno

### 5.2 Pseudo-codice

```python
def applica_revisione_provvisoria(input: InputAlgoritmoC) -> OutputAlgoritmoC:
    # Step 1: crea entità revisione
    rev = RevisioneProvvisoria(
        causa=input.causa,
        finestra_da=input.finestra_da,
        finestra_a=input.finestra_a,
        comunicazione_esterna_rif=input.comunicazione_esterna_rif,
        descrizione_evento=input.descrizione_evento,
    )

    # Step 2: applica delta_corse → modifiche ai giri impattati
    blocchi_modificati = []
    giri_modificati_set = set()

    for delta in input.delta_corse:
        # delta.operazione: 'sopprimi' | 'sostituisci_con_bus' | 'devia' | 'aggiungi'
        for giro in input.giri_impattati:
            blocchi = giro.blocchi_che_coprono(delta.corsa_id)
            for b in blocchi:
                mod = applica_delta_a_blocco(b, delta, rev)
                blocchi_modificati.append(mod)
                giri_modificati_set.add(giro.id)

    # Step 3: cascading sui turni PdC
    revisioni_pdc = []
    for giro_id in giri_modificati_set:
        turni_pdc_collegati = find_turni_che_coprono_giro(giro_id)
        for turno in turni_pdc_collegati:
            rev_pdc = RevisioneProvvisoriaPdC(
                revisione_giro_id=rev.id,
                turno_pdc_id=turno.id,
                finestra_da=input.finestra_da,
                finestra_a=input.finestra_a,
            )
            revisioni_pdc.append(rev_pdc)

    # Step 4: re-build turni PdC nella finestra (Algoritmo B su giri-rev)
    # → produce blocchi PdC modificati per ciascuna revisione_provvisoria_pdc

    # Step 5: notifiche
    notifiche = genera_notifiche_cascading(rev, revisioni_pdc)

    return OutputAlgoritmoC(
        revisione_giro=rev,
        blocchi_modificati=blocchi_modificati,
        revisioni_pdc_cascading=revisioni_pdc,
        notifiche=notifiche,
    )
```

### 5.3 Risoluzione query "cosa succede il giorno D?"

Quando il frontend chiede "qual è il turno PdC ALOR_C il 22/04/2026?":

```python
def risolvi_turno_pdc(turno_id, data: date) -> TurnoPdCRisolto:
    base = get_turno_pdc(turno_id)
    rev = find_revisione_pdc_attiva(turno_id, data)

    if rev:
        # Applica override blocchi modificati
        return applica_override(base, rev)
    else:
        return base


def find_revisione_pdc_attiva(turno_id, data):
    return query("""
        SELECT * FROM revisione_provvisoria_pdc
        WHERE turno_pdc_id = :turno_id
          AND :data BETWEEN finestra_da AND finestra_a
        ORDER BY data_pubblicazione DESC
        LIMIT 1
    """, turno_id=turno_id, data=data)
```

Stessa logica per giro materiale (Algoritmo C lato giro).

---

## 6. Validazione e scoring

### 6.1 Validatore unificato

Modulo `domain/normativa/validator.py`:

```python
class ValidatorePdC:
    def __init__(self, normativa: NormativaConfig):
        self.normativa = normativa

    def valida(self, turno: TurnoPdC) -> ValidazioneRisultato:
        violazioni = []
        violazioni += self._check_prestazione(turno)
        violazioni += self._check_condotta(turno)
        violazioni += self._check_refezione(turno)
        violazioni += self._check_accessori(turno)
        violazioni += self._check_gap_handling(turno)
        violazioni += self._check_cv_stazione_ammessa(turno)
        violazioni += self._check_fr_limiti(turno)
        return ValidazioneRisultato(
            valido=not violazioni,
            violazioni=violazioni
        )
```

### 6.2 Scoring (per ranking soluzioni)

Quando l'algoritmo B produce N soluzioni candidate, sceglie la
migliore in base a punteggio:

```python
def score_turno(turno: TurnoPdC) -> float:
    score = 0
    score += 100 - n_pdc(turno)            # meno PdC è meglio
    score -= prestazione_sotto_sfruttata(turno)  # PdC corti = spreco
    score -= n_violazioni_preferenziali(turno)   # NORMATIVA §11.7 mai-mattina-post-riposo
    return score
```

---

## 7. Mapping su moduli Python

Layout `backend/src/colazione/domain/`:

```
domain/
├── builder_giro/
│   ├── __init__.py
│   ├── seed_localita.py            # 3.2 step 2
│   ├── catena_corse.py             # 3.2 step 3 (greedy chain)
│   ├── materiale_vuoto_generator.py  # 3.2 ramo "rientro"
│   └── builder.py                   # 3.2 entry point
│
├── builder_pdc/
│   ├── __init__.py
│   ├── seed_enumerator.py          # 4.3
│   ├── posizionamento.py           # 4.4
│   ├── gap_handler.py              # 4.5
│   ├── rientro.py                  # 4.6
│   ├── builder_giornata.py         # combina A-D
│   ├── builder_ciclo.py            # 4.8 ciclo settimanale
│   └── builder.py                   # entry point Algoritmo B
│
├── normativa/
│   ├── __init__.py
│   ├── config.py                    # NormativaConfig per azienda
│   ├── validator.py                # 6.1
│   ├── score.py                    # 6.2
│   └── trenord.py                  # config Trenord (8h30, 5h30, ecc.)
│
└── revisioni/
    ├── __init__.py
    ├── builder.py                   # 5.2 Algoritmo C
    ├── cascading.py                # 5.2 step 3-4
    └── resolver.py                  # 5.3 query risolutore
```

Tutti i moduli sono **DB-agnostic**: ricevono dataclass, ritornano
dataclass. Le funzioni di lettura/scrittura DB stanno in `api/` (route
FastAPI) e usano SQLAlchemy.

Test in `tests/domain/builder_giro/`, `tests/domain/builder_pdc/`,
ecc. Test puri, no DB, fixtures con dati seed.

---

## 8. Edge case noti

Alcuni casi che il vecchio progetto aveva trovato e che il nuovo deve
gestire (vedi `ALGORITMO-BUILDER.md` §7 storico):

1. **Materiale che pernotta fuori deposito** (es. P1 → Sondrio).
   L'ultimo blocco è un `materiale_vuoto` che termina in stazione non
   deposito. Il giro torna alla località manutenzione **il giorno
   dopo** col primo treno del mattino.

2. **Materiale che parte senza U-numero** (es. da Sondrio al mattino
   dopo pernotto). Nessun `materiale_vuoto` di testa, primo blocco è
   già una corsa commerciale.

3. **CV a Tirano** (NORMATIVA §9.2 capolinea inversione): il 2° PdC
   prende il materiale per il ritorno. Ammesso ma richiede PdC
   disponibile con deposito in linea (Sondrio, Lecco, Milano).

4. **Prestazione cap 7h** su presa servizio notturna: forza PdC corti.
   Se la catena condotta naturale eccede, spezzare con CV anche se
   sub-ottimale.

5. **MI.PG → FIOz = TAXI** (NORMATIVA §8.5.1) senza API. Tempo fisso
   parametrizzato (default proposto: 20').

6. **Composizione mista (es. doppia + treno corto)**: la stessa giornata
   del giro non può cambiare composizione — se serve, due giri diversi.
   Cambio composizione fra giornate del ciclo è ammesso.

7. **POOL_TILO_SVIZZERA**: i giri ETR524 (turni 1190-1199 nei dati
   Trenord reali) gestiti come `localita_manutenzione` con flag
   `is_pool_esterno=true`. L'algoritmo li tratta come gli altri ma
   non genera materiali vuoti di rientro alla manutenzione (la
   manutenzione è altrove, non gestita da Trenord).

---

## 9. Versioning algoritmi

Ogni esecuzione di Algoritmo A/B/C registra:
- Versione algoritmo (semver in modulo)
- Hash dei parametri (`ParamGiroBuilder`, `NormativaConfig`)
- Timestamp esecuzione
- Random seed (se usato)

In `metadata` di `OutputAlgoritmoX`. Quando un giro/turno è generato,
queste info finiscono in colonna `generation_metadata_json` su
`giro_materiale` o `turno_pdc`.

Permette di:
- Rigenerare deterministicamente per debug ("prova con seed=42")
- Capire perché un giro è stato fatto in un modo (con quali parametri)
- Bumpare la versione quando l'algoritmo cambia in modo non
  retrocompatibile

---

## 10. Riferimenti

- `docs/NORMATIVA-PDC.md` — fonte verità regole (15 capitoli)
- `docs/MODELLO-DATI.md` v0.5 — entità referenziate
- `docs/STACK-TECNICO.md` — tooling Python (uv, ruff, pytest)
- `docs/SCHEMA-DATI-NATIVO.md` (FASE C doc 5, prossimo) — DDL SQL
- `docs/ALGORITMO-BUILDER.md` — algoritmo storico (riferimento storico,
  mapping a moduli vecchi)
- `docs/ARCHITETTURA-BUILDER-V4.md` — idea "centrata sulla condotta"
  (storico, riferimento concettuale)
- `data/depositi_manutenzione_trenord_seed.json` — anagrafica reale
  per fixture di test

---

**Fine draft v0.1**. Da revisionare con l'utente, in particolare:
- Step 3.4 multi-giornata: la logica di "ciclo chiuso" è ancora
  schematica, va dettagliata quando si arriva all'implementazione
- Step 4.3 scoring seed: i pesi sono placeholder, da tarare con dati
  reali
- Step 5: cascading è descritto a maglie larghe; il dettaglio
  re-build (step 4) richiede esempi concreti
