# PROGRAMMA MATERIALE — input umano del pianificatore (draft v0.2)

> Specifica della tabella di parametri che il **pianificatore giro
> materiale** compila prima di lanciare l'algoritmo di costruzione
> giri (Algoritmo A di `LOGICA-COSTRUZIONE.md`).
>
> **Decisione architetturale (utente, 2026-04-26)**: COLAZIONE non
> "legge" l'assegnazione rotabile dal sistema Trenord esistente — il
> PdE Trenord 2025-2026 reale ha le 27 colonne di tipologia/categoria
> **completamente vuote** (verifica empirica). Il rotabile è **una
> scelta del pianificatore**, fatta in COLAZIONE, registrata nel
> `programma_materiale`. Il software è strumento di programmazione,
> non di replica.
>
> **Multi-tenant**: il programma materiale è **per azienda**.
>
> ---
>
> **v0.2 changelog** (post-review utente):
>
> - §2.2 Scope: passa da 4 valori enum a **lista di filtri AND**
>   estendibile (codice_linea, direttrice, categoria, stazione
>   origine/destinazione, rete, treno garantito, numero_treno, ecc.).
> - §2.4 Fasce orarie: chiarito che sono **indicative, non rigide**.
>   Il modello le tiene esatte, il builder le interpreta morbide su
>   corse borderline.
> - §2.7 Strict mode: passa da flag globale a **JSONB di flag
>   granulari** (per dimensione di violazione).
> - §5 Aggancio/sgancio: il builder **propone**, l'utente **decide
>   manualmente** la stazione. Modellato come `evento_composizione`
>   che il builder annota con `is_validato_utente=False`, e il
>   pianificatore conferma/sposta in editor giro.
> - §6.7 Multi-giornata cross-notte: gestita **da subito**, non
>   rimandata. Complica il builder ma è la versione vera.

---

## Indice

1. [Visione](#1-visione)
2. [Concetti chiave](#2-concetti-chiave)
3. [Modello dati v0.2](#3-modello-dati-v02)
4. [Risoluzione di una corsa](#4-risoluzione-di-una-corsa)
5. [Composizione dinamica (aggancio/sgancio)](#5-composizione-dinamica-agganciosgancio)
6. [Edge case + strict mode granulare](#6-edge-case--strict-mode-granulare)
7. [Esempi reali Trenord](#7-esempi-reali-trenord)
8. [Versione individuale (futura)](#8-versione-individuale-futura)
9. [Riferimenti](#9-riferimenti)
10. [Stato](#10-stato)

---

## 1. Visione

### 1.1 Perché esiste

Il PdE Trenord (10579 corse) descrive **cosa** circolerà (linee,
orari, periodicità). Non descrive **con quale rotabile**. Quella è
una **decisione di programmazione** che oggi Trenord prende in un
sistema interno separato.

Il programma materiale di COLAZIONE è il **registro autorevole** di
quella decisione, lato nostro:

```
┌─────────────────────────┐
│  PdE (10579 corse)      │  ← cosa circola
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  PROGRAMMA MATERIALE    │  ← cosa fa girare il treno
│  (input umano)          │     (umano decide)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  GIRI MATERIALI         │  ← cosa effettivamente succede
│  (Algoritmo A)          │     (builder propone, umano valida)
└─────────────────────────┘
```

### 1.2 Filosofia "noi decidiamo"

COLAZIONE **non importa** un programma materiale da file Trenord. Il
pianificatore lo costruisce dentro l'app, con UI che permette di:

- Definire regole "linea S5 feriale mattina = 3× ALe711"
- Override per fasce orarie pendolari
- Validare la copertura (tutte le corse hanno una regola
  applicabile?)
- Salvare versioni (programma estivo vs invernale)
- Pubblicare un programma → sblocca la generazione giri

### 1.3 Versione "fungibile" prima, "individuale" poi

**Versione fungibile (questo documento, v0.2)**: il programma
assegna **tipi** di rotabile + **quantità**. Es. "S5 mattina = 3×
ALe711". L'algoritmo verifica che la località manutenzione abbia
almeno 3 pezzi del tipo. Non identifica *quale* dei 64 ALe711 di
Fiorenza farà il giro: è fungibile.

**Versione individuale (futura, obbligatoria)**: ogni rotabile
fisico ha identità (`ALe711#001`, `#002`, …). Il programma può
vincolare "ALe711#003 fa il giro X" per allineare con piani di
manutenzione, revisioni, fermate calendario. Si introdurrà quando
integreremo il modulo manutenzione.

### 1.4 Multi-tenant

Una `azienda` ha **molti** `programma_materiale`. Ogni programma è
indipendente. Possono coesistere più programmi attivi nello stesso
momento per diverse stagioni.

---

## 2. Concetti chiave

### 2.1 Programma materiale

Un'**unità coerente di scelte di programmazione** valida per una
finestra temporale. Ha:

- **Intestazione**: nome, azienda, stagione, valido_da/a, stato.
- **Parametri globali**: km_max_giornaliero, n_giornate_default,
  fascia_oraria_tolerance_min, strict_options_json.
- **Regole di assegnazione** (1 → N): le scelte specifiche.

### 2.2 Regola di assegnazione

Una **dichiarazione** del pianificatore: "le corse che soddisfano
**tutti questi filtri** vengono coperte da N pezzi di tipo X".

```
Regola := lista_filtri (AND) → assegnazione
```

Una regola può combinare **più filtri** che devono matchare tutti.
Es. "linea S5 + stazione origine MILANO_CADORNA + giorno_tipo
feriale + fascia 04:00-15:59 → 3× ALe711".

### 2.3 Filtri disponibili

Lista (estendibile) dei campi su cui una regola può filtrare. Ogni
filtro è una coppia `(campo, valore)` o `(campo, valori_lista)`. Tutti
i filtri di una regola si combinano in **AND**.

| Campo filtro | Tipo | Operatore | Esempio |
|---|---|---|---|
| `codice_linea` | string | eq, in | `S5` o `[S5,S6,S7]` |
| `direttrice` | string | eq, in | `MILANO-BERGAMO` |
| `categoria` | string | eq, in | `RE`, `R`, `S` |
| `numero_treno` | string | eq, in | `12345` (per eccezioni) |
| `rete` | string | eq | `RFI` o `FN` |
| `codice_origine` | string | eq, in | `S01066` (Mi.Cadorna) |
| `codice_destinazione` | string | eq, in | `S01747` (Laveno) |
| `is_treno_garantito_feriale` | bool | eq | `true` |
| `is_treno_garantito_festivo` | bool | eq | `true` |
| `fascia_oraria` | time range | between | `[04:00, 15:59]` |
| `giorno_tipo` | enum set | in | `[feriale]` |
| `valido_in_data_da/a` | date range | between | range datesettimana |

L'elenco è estendibile in futuro (es. `posti_min`, `velocità_min`,
`linea_di_origine`) senza migration: la `regola.filtri_json` è JSONB
opaco a SQL, validato solo dall'applicazione.

**Una regola con `filtri_json = []` matcha tutte le corse**
(uso: regola di fallback con priorità bassa).

### 2.4 Fascia oraria — indicativa, non rigida

Una regola con `fascia_oraria_da=16:00, fascia_oraria_a=23:59` matcha
formalmente le corse con `ora_partenza ∈ [16:00, 23:59]`.

**Ma le fasce sono indicative**: una corsa che parte alle 15:55
appartiene comunque alla fascia "pomeriggio pendolare" se il
contesto del giro lo richiede. Per gestire questa flessibilità:

- **Modello dati**: tiene le fasce esatte (rigide, comparabili,
  testabili).
- **Builder algoritmico**: in caso di **delta di composizione** su
  corse borderline (es. corsa che parte alle 15:55 dopo una corsa
  delle 16:30 sulla stessa linea), può **spostare l'evento di
  aggancio** alla stazione più sensata, anche se formalmente
  sarebbe in mezzo. **L'utente conferma o riposiziona** l'evento in
  editor giro (vedi §5).
- **Tolleranza configurabile**: parametro `fascia_oraria_tolerance_min`
  sul programma (default 30 min). Il builder considera corse entro
  questa tolleranza come "candidate" per entrambe le fasce
  adiacenti, e segnala la decisione al pianificatore per
  conferma.

### 2.5 Giorno tipo

Set di valori tra `{feriale, sabato, festivo}`. La corsa ha
periodicità già parsata in `valido_in_date_json`; per determinare il
giorno_tipo di una corsa in una data specifica:

- Lunedì-venerdì non festivo → feriale
- Sabato non festivo → sabato
- Domenica e festività italiane → festivo

(Logica già pronta in `holidays.py` per le festività, da cablare nel
builder.)

### 2.6 Priorità

Più regole possono matchare la stessa corsa. La **priorità**
numerica (0-100) decide chi vince: priorità più alta prevale.

Convenzione suggerita per i default UI (l'utente può forzare):

| Tipo regola | Priorità default |
|---|---|
| Solo `numero_treno` (corsa specifica) | 100 |
| `codice_linea` + altri filtri (fascia/giorno/stazione) | 80 |
| Solo `codice_linea` o `direttrice` | 60 |
| Solo `categoria` o `rete` | 30 |
| `filtri_json = []` (fallback globale) | 10 |

In caso di parità, vince **la regola più specifica** (più filtri
attivi nel `filtri_json`). In caso di parità anche di specificità,
errore esplicito al pianificatore: "due regole equivalenti, scegli
priorità diverse".

### 2.7 Strict mode granulare (JSONB)

Le opzioni di strict mode sono in JSONB sul programma, ognuna
indipendente. Default tutto `false` durante editing (tolerant), tutto
`true` per pubblicazione (strict).

```json
{
  "no_corse_residue": false,
  "no_overcapacity": false,
  "no_aggancio_non_validato": false,
  "no_orphan_blocks": false,
  "no_giro_non_chiuso_a_localita": false,
  "no_km_eccesso": false
}
```

Ogni flag controlla una dimensione:

| Flag | Cosa controlla | Errore se attivo |
|---|---|---|
| `no_corse_residue` | Tutte le corse devono avere ≥ 1 regola applicabile | Corsa senza regola → errore |
| `no_overcapacity` | Quantità rotabili richiesta ≤ dotazione disponibile per ogni località/istante | Overcapacity → errore |
| `no_aggancio_non_validato` | Eventi aggancio/sgancio devono avere `is_validato_utente=true` | Aggancio non confermato → errore |
| `no_orphan_blocks` | Ogni `giro_blocco` ha materiale assegnato | Blocco senza assegnazione → errore |
| `no_giro_non_chiuso_a_localita` | Ogni giro inizia e finisce in una `localita_manutenzione` | Giro che non chiude → errore |
| `no_km_eccesso` | Ogni giornata del giro ≤ `km_max_giornaliero` | Eccesso km → errore |

Default: tutti `false` durante editing (tolerant) → builder logga
warning. Pre-pubblicazione: tutti `true` (strict) → ogni violazione
blocca la pubblicazione. UI permette di toggle individuali.

### 2.8 Fungibile

Per Sprint 4 il programma assegna **tipo + quantità**, non identità.
"3× ALe711 a Fiorenza" = "qualsiasi 3 dei 64 ALe711 in dotazione a
Fiorenza". L'algoritmo verifica solo che la quantità in dotazione ≥
quantità richiesta dalla somma dei giri attivi simultaneamente.

---

## 3. Modello dati v0.2

### 3.1 Tabelle

#### `programma_materiale`

```sql
CREATE TABLE programma_materiale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

    nome TEXT NOT NULL,
    stagione VARCHAR(20),               -- 'invernale' | 'estiva' | 'agosto' | NULL
    valido_da DATE NOT NULL,
    valido_a DATE NOT NULL,
    stato VARCHAR(20) NOT NULL DEFAULT 'bozza',

    -- Parametri globali
    km_max_giornaliero INTEGER,         -- nullable; NULL = nessun vincolo
    n_giornate_default INTEGER NOT NULL DEFAULT 1,
    fascia_oraria_tolerance_min INTEGER NOT NULL DEFAULT 30,

    -- Strict mode granulare (default tutto false = tolerant)
    strict_options_json JSONB NOT NULL DEFAULT '{
        "no_corse_residue": false,
        "no_overcapacity": false,
        "no_aggancio_non_validato": false,
        "no_orphan_blocks": false,
        "no_giro_non_chiuso_a_localita": false,
        "no_km_eccesso": false
    }'::jsonb,

    -- Tracking
    created_by_user_id BIGINT REFERENCES app_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT programma_stato_check
        CHECK (stato IN ('bozza', 'attivo', 'archiviato')),
    CONSTRAINT programma_stagione_check
        CHECK (stagione IN ('invernale', 'estiva', 'agosto') OR stagione IS NULL),
    CONSTRAINT programma_validita_check CHECK (valido_a >= valido_da),
    CONSTRAINT programma_giornate_check CHECK (n_giornate_default >= 1),
    CONSTRAINT programma_tolerance_check
        CHECK (fascia_oraria_tolerance_min >= 0 AND fascia_oraria_tolerance_min <= 120)
);

CREATE INDEX idx_programma_azienda ON programma_materiale(azienda_id);
CREATE INDEX idx_programma_stato ON programma_materiale(stato);
CREATE INDEX idx_programma_validita ON programma_materiale(valido_da, valido_a);
```

#### `programma_regola_assegnazione`

```sql
CREATE TABLE programma_regola_assegnazione (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    programma_id BIGINT NOT NULL
        REFERENCES programma_materiale(id) ON DELETE CASCADE,

    -- Filtri (combinati AND, validati dall'app)
    -- Es. [
    --   {"campo": "codice_linea", "op": "eq", "valore": "S5"},
    --   {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
    --   {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
    -- ]
    filtri_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Assegnazione
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
    numero_pezzi INTEGER NOT NULL,

    -- Priorità + tracking
    priorita INTEGER NOT NULL DEFAULT 60,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT regola_pezzi_check CHECK (numero_pezzi >= 1),
    CONSTRAINT regola_priorita_check CHECK (priorita >= 0 AND priorita <= 100)
);

CREATE INDEX idx_regola_programma ON programma_regola_assegnazione(programma_id);
CREATE INDEX idx_regola_priorita ON programma_regola_assegnazione(priorita DESC);
-- GIN su filtri_json per query "che regole filtrano per linea X?"
CREATE INDEX idx_regola_filtri_gin
    ON programma_regola_assegnazione USING GIN (filtri_json);
```

### 3.2 Schema dei filtri (`filtri_json`)

Array di oggetti, ognuno con 3 chiavi obbligatorie:

```typescript
type FiltroRegola = {
    campo: string;     // uno dei campi listati in §2.3
    op: 'eq' | 'in' | 'between' | 'gte' | 'lte';
    valore: string | number | boolean | Array<...>;
};
```

Validazione applicativa (Pydantic):
- `campo` ∈ lista chiusa di campi supportati (§2.3)
- `op` compatibile col tipo del campo (es. `between` solo su time/date,
  `eq` su tutti)
- `valore` shape coerente con `op` (es. `between` richiede array di 2)

Esempi validi:
```json
[
  {"campo": "codice_linea", "op": "eq", "valore": "S5"}
]

[
  {"campo": "categoria", "op": "in", "valore": ["RE", "R"]},
  {"campo": "fascia_oraria", "op": "between", "valore": ["16:00", "21:00"]},
  {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
]

[
  {"campo": "codice_origine", "op": "eq", "valore": "S01066"},
  {"campo": "is_treno_garantito_feriale", "op": "eq", "valore": true}
]
```

### 3.3 Esempio popolamento

```sql
-- Programma invernale Trenord 2025-2026 (bozza)
INSERT INTO programma_materiale
    (azienda_id, nome, stagione, valido_da, valido_a, stato,
     km_max_giornaliero, n_giornate_default)
VALUES
    (1, 'Trenord 2025-2026 invernale', 'invernale',
     '2025-12-14', '2026-04-30', 'bozza',
     800, 5);
-- → id = 1

-- Regola 1: S5 feriale mattina → 3× ALe711
INSERT INTO programma_regola_assegnazione
    (programma_id, filtri_json, materiale_tipo_codice, numero_pezzi, priorita)
VALUES
    (1,
     '[
        {"campo": "codice_linea", "op": "eq", "valore": "S5"},
        {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
        {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
      ]'::jsonb,
     'ALe711', 3, 80);

-- Regola 2: S5 feriale pomeriggio → 6× ALe711 (aggancio implicito alle 16)
INSERT INTO programma_regola_assegnazione
    (programma_id, filtri_json, materiale_tipo_codice, numero_pezzi, priorita)
VALUES
    (1,
     '[
        {"campo": "codice_linea", "op": "eq", "valore": "S5"},
        {"campo": "fascia_oraria", "op": "between", "valore": ["16:00", "23:59"]},
        {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
      ]'::jsonb,
     'ALe711', 6, 80);
```

---

## 4. Risoluzione di una corsa

Funzione pura `risolvi_corsa(corsa, programma, data) →
AssegnazioneRisolta | None`.

### 4.1 Algoritmo

```python
def risolvi_corsa(corsa: CorsaCommerciale, programma: ProgrammaMateriale,
                  data: date) -> AssegnazioneRisolta | None:
    """Data una corsa e un programma, ritorna l'assegnazione (rotabile +
    quantità) applicabile in una specifica data, oppure None.
    """
    giorno_tipo = determina_giorno_tipo(data)  # via holidays.py

    # Step 1: filtra regole applicabili (tutti i filtri AND devono matchare)
    candidate = [r for r in programma.regole if matches_all(r.filtri_json, corsa, giorno_tipo)]
    if not candidate:
        return None

    # Step 2: ordina per (priorita DESC, specificita DESC)
    candidate.sort(
        key=lambda r: (r.priorita, len(r.filtri_json)),
        reverse=True,
    )

    # Step 3: detect parità ambigue
    top = candidate[0]
    if len(candidate) > 1:
        second = candidate[1]
        if (top.priorita == second.priorita
                and len(top.filtri_json) == len(second.filtri_json)):
            raise RegolaAmbiguaError(
                corsa_id=corsa.id, regole=[top.id, second.id]
            )

    return AssegnazioneRisolta(
        regola_id=top.id,
        materiale_tipo_codice=top.materiale_tipo_codice,
        numero_pezzi=top.numero_pezzi,
    )


def matches_all(filtri: list[FiltroRegola], corsa: Corsa, giorno_tipo: str) -> bool:
    """Tutti i filtri devono matchare la corsa (AND)."""
    for f in filtri:
        if not matches_filtro(f, corsa, giorno_tipo):
            return False
    return True


def matches_filtro(f: FiltroRegola, corsa: Corsa, giorno_tipo: str) -> bool:
    valore_corsa = estrai_valore_corsa(f["campo"], corsa, giorno_tipo)
    if f["op"] == "eq":
        return valore_corsa == f["valore"]
    if f["op"] == "in":
        return valore_corsa in f["valore"]
    if f["op"] == "between":
        lo, hi = f["valore"]
        return lo <= valore_corsa <= hi
    if f["op"] == "gte":
        return valore_corsa >= f["valore"]
    if f["op"] == "lte":
        return valore_corsa <= f["valore"]
    raise ValueError(f"Operatore non supportato: {f['op']}")


def estrai_valore_corsa(campo: str, corsa: Corsa, giorno_tipo: str):
    """Mapping campo regola → attributo della corsa."""
    if campo == "codice_linea":
        return corsa.codice_linea
    if campo == "direttrice":
        return corsa.direttrice
    if campo == "categoria":
        return corsa.categoria
    if campo == "numero_treno":
        return corsa.numero_treno
    if campo == "rete":
        return corsa.rete
    if campo == "codice_origine":
        return corsa.codice_origine
    if campo == "codice_destinazione":
        return corsa.codice_destinazione
    if campo == "is_treno_garantito_feriale":
        return corsa.is_treno_garantito_feriale
    if campo == "is_treno_garantito_festivo":
        return corsa.is_treno_garantito_festivo
    if campo == "fascia_oraria":
        return corsa.ora_partenza
    if campo == "giorno_tipo":
        return giorno_tipo
    raise ValueError(f"Campo non supportato: {campo}")
```

### 4.2 Properties

- **Determinismo**: stessa corsa + programma + data → stessa
  assegnazione, sempre.
- **Funzione pura**: niente DB, niente I/O. Testabile.
- **Performance**: O(N regole × M filtri/regola) per corsa. Per
  10579 corse × 100 regole × 5 filtri ≈ 5M operazioni, < 2s.
- **Errori controllati**: `RegolaAmbiguaError` se due regole con
  priorità + specificità identiche matchano. L'utente deve
  disambiguare.

---

## 5. Composizione dinamica (aggancio/sgancio)

### 5.1 Il fenomeno reale

(cit. utente):
> *"ALe711 gira con 3 pezzi fino alle 16, poi aggancia altri 3 pezzi
> per fascia pendolare. Il giro continua fino alla successiva fascia
> pendolare della mattina dopo, poi sgancia i 3 pezzi originari."*

### 5.2 Filosofia: builder propone, utente decide

Decisione utente esplicita: **l'aggancio/sgancio non viene scelto
automaticamente dal builder**. Il builder rileva il **delta di
composizione** dalle regole sovrapposte (es. transizione `3 → 6` alle
16:00 sulla linea S5) e **propone** una stazione candidata
(tipicamente la prima opportuna dopo l'inizio della nuova fascia).

L'utente vede l'evento in editor giro come **"da validare"** e:
- Conferma la stazione proposta → `is_validato_utente=true`
- Sposta in altra stazione del giro → conferma altrove
- Cancella se la regola sovrapposta era un errore di programma

### 5.3 Algoritmo di rilevamento delta + proposta stazione

```python
def rileva_eventi_composizione(blocchi_giro: list[BloccoCorsa]) -> list[EventoComposizione]:
    """Annota i punti dove la composizione cambia.

    Ogni evento ha:
      - tipo: 'aggancio' | 'sgancio'
      - pezzi_delta: signed int (es. +3 o -3)
      - stazione_proposta: codice stazione candidata
      - is_validato_utente: False (default; UI lo cambia in True
        quando il pianificatore conferma)
      - note_builder: spiegazione del perché questa stazione
        (per UI tooltip)
    """
    eventi = []
    composizione_prev = None
    for blocco in blocchi_giro:
        composizione_curr = blocco.assegnazione.numero_pezzi
        if composizione_prev is not None:
            delta = composizione_curr - composizione_prev
            if delta != 0:
                stazione_proposta = scegli_stazione_aggancio(
                    blocco_prev=blocchi_giro[blocchi_giro.index(blocco) - 1],
                    blocco_curr=blocco,
                )
                eventi.append(EventoComposizione(
                    tipo='aggancio' if delta > 0 else 'sgancio',
                    pezzi_delta=delta,
                    stazione_proposta=stazione_proposta,
                    is_validato_utente=False,
                    note_builder=f"Transizione fascia {blocco_prev.fascia} → {blocco.fascia}",
                ))
        composizione_prev = composizione_curr
    return eventi


def scegli_stazione_aggancio(blocco_prev, blocco_curr):
    """Heuristic: preferisci capolinea, altrimenti prima stazione disponibile."""
    if blocco_prev.codice_destinazione == blocco_curr.codice_origine:
        # Punto naturale di transizione (cambio treno in stazione)
        return blocco_curr.codice_origine
    # Fallback: stazione di partenza del blocco corrente
    return blocco_curr.codice_origine
```

### 5.4 Persistenza

Estendiamo il modello `giro_blocco` esistente con i tipi `aggancio`/
`sgancio` e un campo `is_validato_utente` + `metadata_json`:

```sql
-- Aggiorna check tipo
ALTER TABLE giro_blocco DROP CONSTRAINT giro_blocco_tipo_check;
ALTER TABLE giro_blocco ADD CONSTRAINT giro_blocco_tipo_check
    CHECK (tipo_blocco IN (
        'corsa_commerciale', 'materiale_vuoto',
        'sosta_capolinea', 'sosta_intermedia', 'sosta_deposito',
        'aggancio', 'sgancio'
    ));

-- Nuovo campo per tracking validazione utente
ALTER TABLE giro_blocco ADD COLUMN is_validato_utente BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE giro_blocco ADD COLUMN metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;
```

`metadata_json` per i blocchi `aggancio`/`sgancio`:
```json
{
  "pezzi_delta": 3,
  "note_builder": "Transizione fascia mattina → pomeriggio",
  "stazione_proposta_originale": "S01066",
  "stazione_finale": "S01700"
}
```

Default `is_validato_utente=false`. Il flag `no_aggancio_non_validato`
in `strict_options_json` (§2.7) blocca la pubblicazione finché
**tutti** gli `aggancio`/`sgancio` sono validati dall'utente.

### 5.5 Limiti del v0.2

L'aggancio/sgancio dello stesso pezzo che "girava prima da solo"
(cit. utente) è una relazione **trasversale** tra giri diversi: il
pezzo ALe711#X esce dal giro A e entra nel giro B. Nella **versione
fungibile** non tracciamo identità di pezzi, quindi l'evento è
"locale al giro" (delta count). La **versione individuale** (futura,
§8) modellerà esplicitamente la transizione del pezzo P tra giro A
e giro B.

---

## 6. Edge case + strict mode granulare

### 6.1 Sovrapposizione di regole

Più regole matchano una stessa corsa.

**Risoluzione**: ordina per `(priorita DESC, specificita DESC)`,
prendi la prima. Se top-2 hanno **identica priorità + specificità** →
`RegolaAmbiguaError`. L'utente disambigua dal UI.

### 6.2 Corsa senza regola applicabile

Comportamento dipende da `strict_options_json.no_corse_residue`:

- `false` (default editing): la corsa va in `output.corse_residue:
  list[CorsaResidua]`, warning loggato, gli altri giri sono comunque
  generati.
- `true` (pre-pubblicazione): l'algoritmo solleva
  `ProgrammaIncompletoError(corsa_id=...)`, nessun giro generato.

### 6.3 Cambio composizione su corsa di confine (fascia indicativa)

Una corsa parte alle 15:55 (fascia mattina, regola "fino alle 16 = 3
pezzi"). La corsa successiva del giro parte alle 16:30 (fascia
pomeriggio, regola "dalle 16 = 6 pezzi"). Cosa fa il builder?

**Default**: la **partenza** decide il match della singola corsa.
- Corsa 15:55 → regola mattina → 3 pezzi
- Corsa 16:30 → regola pomeriggio → 6 pezzi
- Delta `+3` rilevato tra i due blocchi → evento aggancio
  proposto
- Stazione proposta: la stazione di arrivo della corsa 15:55 (=
  partenza corsa 16:30, naturale)
- `is_validato_utente=false` → l'utente conferma o sposta

**Tolleranza configurabile**: se `fascia_oraria_tolerance_min=30`, le
corse 15:30-15:59 (entro 30' dalla soglia 16:00) sono **borderline**
e il builder genera una nota nel `metadata_json` del blocco:
"corsa borderline, valuta se appartiene alla fascia precedente o
successiva". Il pianificatore può aggiungere una regola
`numero_treno`-specifica per forzare.

### 6.4 Capacità materiale (vincolo di dotazione)

Il builder controlla che la **quantità di pezzi richiesti
simultaneamente** non ecceda la dotazione della località
manutenzione. Esempio: Fiorenza ha 64 ALe711. Se 25 giri attivi
contemporaneamente richiedono 3 pezzi ciascuno = 75 pezzi → **errore
di overcapacity**.

`strict_options_json.no_overcapacity`:
- `false` (default): warning, builder procede e segnala il conflitto.
- `true` (pre-pubblicazione): errore, blocco generazione.

### 6.5 Materiale non in dotazione

Una regola assegna `materiale_tipo='ETR526'`, ma nessuna
`localita_manutenzione` ha quel tipo → errore di config.

**Detection**: validazione del programma alla **pubblicazione**
(cambio stato bozza → attivo). Si calcola
`set(regole.materiale_tipo) - set(materiali_disponibili)`. Se non
vuoto → errore di pubblicazione, indipendente dallo strict mode.

### 6.6 Programmi sovrapposti

Le finestre temporali devono essere **non sovrapponibili** per
programmi della stessa stagione e azienda. Constraint applicativo
(non SQL) controllato alla pubblicazione.

Sovrapposizioni **legittime** sono solo tra stagioni diverse (es.
"invernale 14/12-30/04" + "estiva 01/05-30/09" non si sovrappongono).
Programmi feriale/weekend distinti **non sono questo**: un singolo
programma con regole filtrate per `giorno_tipo` è la modellazione
corretta.

### 6.7 Multi-giornata cross-notte

Decisione utente: il builder **gestisce da subito** giri che
attraversano la notte. Implicazioni:

1. **Continuità materiale fisico**: il convoglio non "torna in
   deposito a mezzanotte" obbligatoriamente. Un giro G1 può durare
   da lunedì 04:00 a martedì 03:00 senza tornare alla località
   manutenzione.

2. **Determinazione del `giorno_tipo`** per l'assegnazione: usa la
   data della **partenza** della corsa, non la data calendaristica.
   Una corsa che parte martedì 00:30 → giorno_tipo = "feriale"
   anche se è tecnicamente "il giorno dopo" rispetto al lunedì in
   cui è iniziato il giro.

3. **Chiusura giro**: il giro chiude quando:
   - Torna alla località manutenzione di partenza (chiusura
     naturale)
   - Raggiunge il `n_giornate_default` del programma (es. 5
     giornate operative)
   - Supera il `km_max_giornaliero` × `n_giornate_default` (forza
     rientro)

4. **Strict flag dedicato**:
   `strict_options_json.no_giro_non_chiuso_a_localita` → blocca
   pubblicazione se ci sono giri "appesi" senza chiusura.

### 6.8 Strict mode granulare — riepilogo

| Flag | Cosa controlla |
|---|---|
| `no_corse_residue` | Tutte le corse hanno ≥ 1 regola applicabile |
| `no_overcapacity` | Pezzi richiesti ≤ dotazione disponibile |
| `no_aggancio_non_validato` | Tutti gli eventi composizione `is_validato_utente=true` |
| `no_orphan_blocks` | Ogni `giro_blocco` ha materiale assegnato |
| `no_giro_non_chiuso_a_localita` | Ogni giro chiude in `localita_manutenzione` |
| `no_km_eccesso` | Nessuna giornata > `km_max_giornaliero` |

Editing iterativo: tutti `false`. Pre-pubblicazione: tutti `true`. UI
permette toggle individuale per debug mirato (es. "voglio vedere se
ci sono solo problemi di overcapacity").

---

## 7. Esempi reali Trenord

### 7.1 Linea S5 con cambio fascia pendolare

Pianificatore vuole: ALe711 in singola la mattina, in doppia il
pomeriggio (16-21), poi singola la sera. Sabato e festivi sempre in
singola.

```
Programma "Trenord 2025-2026 invernale", regole linea S5:

R1 — filtri: [linea=S5, fascia=04:00-15:59, giorno_tipo=[feriale]]
  → 3× ALe711, priorità 80
R2 — filtri: [linea=S5, fascia=16:00-21:00, giorno_tipo=[feriale]]
  → 6× ALe711, priorità 80   (delta +3 alle 16 → evento aggancio)
R3 — filtri: [linea=S5, fascia=21:01-23:59, giorno_tipo=[feriale]]
  → 3× ALe711, priorità 80   (delta -3 alle 21 → evento sgancio)
R4 — filtri: [linea=S5, giorno_tipo=[sabato, festivo]]
  → 3× ALe711, priorità 60
```

Una corsa S5 feriale alle 17:30 → matcha R2 → 6 pezzi.
Una corsa S5 sabato alle 17:30 → matcha solo R4 → 3 pezzi.

Il builder genera 2 eventi sui giri attraversati: aggancio +3 alle
16:00 (stazione da validare), sgancio -3 alle 21:00 (idem).

### 7.2 Linea TILO Svizzera (rotabile dedicato)

```
R — filtri: [direttrice="MILANO-CHIASSO-LUGANO"]
  → 4× ETR524, priorità 60
```

Tutte le corse della direttrice sono coperte. Il programma valida
che ETR524 sia in dotazione di POOL_TILO_SVIZZERA.

### 7.3 Treno speciale singolo

```
R — filtri: [numero_treno="12345"]
  → 1× ALe711, priorità 100
```

Sempre vincente per quella corsa, indipendente da regole linea più
generali.

### 7.4 Default per categoria (fallback)

```
R — filtri: [categoria="RE"]
  → 4× ALe711, priorità 30
```

Cattura tutto il regio express che non abbia regole più specifiche.
Buona difesa contro `no_corse_residue=true`.

### 7.5 Rotabile per stazione (terminale dedicato)

Esempio: tutte le corse che partono da MILANO CADORNA (rete FN)
usano un parco specifico:

```
R — filtri: [codice_origine="S01066", rete="FN"]
  → 3× ALe711, priorità 70
```

### 7.6 Treno garantito (servizio essenziale)

I treni garantiti feriali hanno priorità di rotabile robusto:

```
R — filtri: [is_treno_garantito_feriale=true, codice_linea="S5"]
  → 3× ALe711, priorità 90   (override delle regole standard S5)
```

---

## 8. Versione individuale (futura)

### 8.1 Quando si attiva

Quando il modulo manutenzione richiederà di **tracciare quale pezzo
fisico** copre quale giro, per:
- Allineare giri con fermate calendario
- Pianificare revisioni (ogni N km/giorni il pezzo X va fermo)
- Audit operativo ("il pezzo P il giorno D dove è andato?")

### 8.2 Modello dati anticipato

Nuova tabella `rotabile_individuale`:

```sql
CREATE TABLE rotabile_individuale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matricola VARCHAR(50) NOT NULL UNIQUE,
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice),
    localita_manutenzione_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id),
    stato VARCHAR(20) DEFAULT 'attivo',
    km_progressivi BIGINT DEFAULT 0,
    ultima_revisione DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

E tabella di link `giro_pezzo_assegnazione` per tracciare quale pezzo
copre quale giro in quale data.

### 8.3 Migrazione fungibile → individuale

Le regole esistenti restano (`numero_pezzi`). Si aggiunge un campo
`assegnazione_individuale_json` su `giro_blocco` opzionale:

```json
[
  {"matricola": "ALe711-001"},
  {"matricola": "ALe711-002"},
  {"matricola": "ALe711-003"}
]
```

Se `NULL`: semantica fungibile. Se popolato: assegnazione esplicita.
Coesistenza nello stesso DB.

### 8.4 Aggancio/sgancio con identità

Con la versione individuale, l'evento di aggancio/sgancio identifica
**quale pezzo** entra/esce. La transizione "pezzo che girava prima
da solo, ora aggancia" diventa esplicita:

```json
{
  "tipo": "aggancio",
  "pezzi_in_ingresso": [
    {"matricola": "ALe711-007", "giro_origine_id": 42},
    {"matricola": "ALe711-008", "giro_origine_id": 42},
    {"matricola": "ALe711-009", "giro_origine_id": 42}
  ],
  "stazione": "S01066",
  "ora": "16:00:00",
  "is_validato_utente": true
}
```

---

## 9. Riferimenti

- `docs/LOGICA-COSTRUZIONE.md` §3 — Algoritmo A che usa il programma materiale
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale a piramide
- `docs/SCHEMA-DATI-NATIVO.md` §3 (anagrafica) e §5 (giri)
- `docs/IMPORT-PDE.md` — fonte input PdE (corsa_commerciale)
- `data/depositi_manutenzione_trenord_seed.json` — dotazione Trenord (1884 pezzi, 69 tipi)
- `TN-UPDATE.md` entry Sprint 4.0 — diario decisioni

---

## 10. Stato

- [x] **v0.1 — disegno fungibile** (commit 8b52dfc)
- [x] **v0.2 — refinement post-feedback utente** (questo doc)
  - Filtri come array AND estendibile (§2.3)
  - Fasce orarie indicative + tolerance (§2.4, §6.3)
  - Strict mode granulare via JSONB (§2.7, §6.8)
  - Aggancio/sgancio con `is_validato_utente` (§5)
  - Multi-giornata cross-notte (§6.7)
- [ ] Sub-sprint 4.1 — migration 0005 + modello SQLAlchemy
- [ ] Sub-sprint 4.2 — funzione pura `risolvi_corsa`
- [ ] Sub-sprint 4.3 — API CRUD
- [ ] Sub-sprint 4.4 — builder algoritmico (multi-giornata cross-notte)
- [ ] Sub-sprint 4.5 — CLI + smoke test su PdE Trenord reale
- [ ] (futuro) v1.0 — versione individuale (rotabile per matricola)

---

**Fine draft v0.2**. Da validare con utente prima di procedere a 4.1.
