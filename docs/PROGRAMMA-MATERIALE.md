# PROGRAMMA MATERIALE — input umano del pianificatore (draft v0.1)

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
> **Multi-tenant**: il programma materiale è **per azienda**. Trenord
> avrà il suo, SAD/TILO/Trenitalia il proprio. Ogni azienda decide
> autonomamente con quale flotta coprire le proprie corse PdE.

---

## Indice

1. [Visione](#1-visione)
2. [Concetti chiave](#2-concetti-chiave)
3. [Modello dati v0.1](#3-modello-dati-v01)
4. [Risoluzione di una corsa](#4-risoluzione-di-una-corsa)
5. [Composizione dinamica (aggancio/sgancio)](#5-composizione-dinamica-agganciosgancio)
6. [Edge case + strict mode](#6-edge-case--strict-mode)
7. [Esempi reali Trenord](#7-esempi-reali-trenord)
8. [Versione individuale (futura)](#8-versione-individuale-futura)
9. [Riferimenti](#9-riferimenti)

---

## 1. Visione

### 1.1 Perché esiste

Il PdE Trenord (10579 corse) descrive **cosa** circolerà (linee,
orari, periodicità). Non descrive **con quale rotabile**. Quella è una
**decisione di programmazione** che oggi Trenord prende in un sistema
informatico interno separato.

Il programma materiale di COLAZIONE è il **registro autorevole** di
quella decisione, lato nostro:

```
┌─────────────────────────┐
│  PdE (10579 corse)      │  ← cosa circola
│  - linea, orario        │
│  - origine/destinazione │
│  - periodicità          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  PROGRAMMA MATERIALE    │  ← cosa fa girare il treno (umano decide)
│  - regole linea→tipo    │
│  - n. pezzi per regola  │
│  - fasce orarie         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  GIRI MATERIALI         │  ← cosa effettivamente succede
│  (Algoritmo A)          │
└─────────────────────────┘
```

### 1.2 Filosofia "noi decidiamo"

COLAZIONE **non importa** un programma materiale da file Trenord. Il
pianificatore lo costruisce dentro l'app, con UI che permette di:

- Definire regole "linea S5 feriale mattina = 3× ALe711"
- Override per fasce orarie pendolari
- Validare la copertura (tutte le corse hanno una regola applicabile?)
- Salvare versioni (programma estivo vs invernale)
- Pubblicare un programma → sblocca la generazione giri

### 1.3 Versione "fungibile" prima, "individuale" poi

**Versione fungibile (questo documento, v0.1)**: il programma assegna
**tipi** di rotabile + **quantità**. Es. "S5 mattina = 3× ALe711".
L'algoritmo verifica che la località manutenzione abbia almeno 3
pezzi del tipo. Non identifica *quale* dei 64 ALe711 di Fiorenza farà
il giro: è fungibile.

**Versione individuale (futura, obbligatoria)**: ogni rotabile fisico
ha identità (`ALe711#001`, `#002`, …). Il programma può vincolare
"ALe711#003 fa il giro X" per allineare con piani di manutenzione,
revisioni, fermate calendario. Si introdurrà quando integreremo il
modulo manutenzione.

### 1.4 Multi-tenant

Una `azienda` ha **molti** `programma_materiale`. Ogni programma è
indipendente: Trenord può avere "Programma 2025-2026 invernale",
"…estivo", "…agosto"; SAD avrà i propri.

---

## 2. Concetti chiave

### 2.1 Programma materiale

Un'**unità coerente di scelte di programmazione** valida per una
finestra temporale. Ha:

- **Intestazione**: nome, azienda, stagione, valido_da/a, stato.
- **Parametri globali**: km_max_giornaliero, n_giornate_default,
  strict_mode.
- **Regole di assegnazione** (1 → N): le scelte specifiche.

Possono coesistere più programmi attivi nello stesso momento per
diverse stagioni (invernale + agosto si sovrappongono se le date
coincidono nel calendario di esercizio del PdE 14/12 → 12/12).

### 2.2 Regola di assegnazione

Una **dichiarazione** del pianificatore: "le corse che soddisfano
questo scope + filtro vengono coperte da N pezzi di tipo X".

```
Regola := scope + filtro → assegnazione
```

- **Scope**: cosa identifica la corsa
  - `direttrice` (es. "MILANO-BERGAMO")
  - `codice_linea` (es. "S5")
  - `categoria_linea` (es. "RE")
  - `corsa_specifica` (singolo `numero_treno` per casi eccezionali)
- **Filtro**: opzionale, restringe quando la regola si applica
  - `fascia_oraria_da`–`fascia_oraria_a` (basato su `ora_partenza`
    della corsa)
  - `giorno_tipo` (set di valori: feriale, sabato, festivo)
- **Assegnazione**: il rotabile + quantità
  - `materiale_tipo_codice` (FK a `materiale_tipo`)
  - `numero_pezzi` (intero, ≥ 1)

### 2.3 Priorità

Più regole possono matchare la stessa corsa (es. una regola "S5
feriale" + una regola "S5 feriale 16:00-23:59" più specifica). La
**priorità** numerica decide chi vince: priorità più alta prevale.

Convenzione suggerita per i default UI:

| Scope | Priorità default |
|---|---|
| `corsa_specifica` | 100 |
| `codice_linea` + `fascia_oraria` | 80 |
| `codice_linea` solo | 60 |
| `direttrice` | 40 |
| `categoria_linea` | 20 |

L'utente può forzare manualmente. In caso di parità, vince la regola
più specifica (più filtri attivi).

### 2.4 Fascia oraria

Periodo del giorno definito da `(fascia_oraria_da, fascia_oraria_a)`,
estremi inclusi. Si confronta con `corsa_commerciale.ora_partenza`.

**Convenzione**: se una corsa parte alle 16:00:00 esatte e una regola
ha `fascia_oraria_da=16:00`, **matcha** la regola di pomeriggio (non
quella mattutina che finisce alle 15:59:59).

Le regole con `fascia_oraria` `NULL`/`NULL` valgono **24h**.

### 2.5 Giorno tipo

Set di valori tra `{feriale, sabato, festivo}`. La corsa ha la sua
periodicità testuale già parsata in `valido_in_date_json`; per
determinare il giorno_tipo di una corsa in una data specifica:

- Lunedì-venerdì non festivo → feriale
- Sabato non festivo → sabato
- Domenica e festività italiane → festivo

(Logica già pronta in `holidays.py` per le festività, da cablare.)

### 2.6 Fungibile

Per Sprint 4 il programma assegna **tipo + quantità**, non identità.
"3× ALe711 a Fiorenza" = "qualsiasi 3 dei 64 ALe711 in dotazione a
Fiorenza". L'algoritmo verifica solo che la quantità in dotazione ≥
quantità richiesta dalla somma dei giri attivi nello stesso istante.

### 2.7 Strict mode

Flag booleano sul programma. Default `False` (tolerant):

- `strict_mode=False`: corse senza regola applicabile → warning,
  finiscono in `corse_residue` dell'output algoritmo, non bloccano.
- `strict_mode=True`: corse senza regola applicabile → errore,
  l'algoritmo non genera nessun giro finché il programma è incompleto.

Si suggerisce `strict_mode=True` prima di pubblicare un programma in
produzione, `strict_mode=False` durante l'editing iterativo.

---

## 3. Modello dati v0.1

### 3.1 Tabelle

#### `programma_materiale`

```sql
CREATE TABLE programma_materiale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

    nome TEXT NOT NULL,
    stagione VARCHAR(20),               -- 'invernale' | 'estiva' | 'agosto' | NULL (multi)
    valido_da DATE NOT NULL,
    valido_a DATE NOT NULL,
    stato VARCHAR(20) NOT NULL DEFAULT 'bozza',  -- 'bozza' | 'attivo' | 'archiviato'

    -- Parametri globali
    km_max_giornaliero INTEGER,         -- nullable; NULL = nessun vincolo
    n_giornate_default INTEGER NOT NULL DEFAULT 1,
    strict_mode BOOLEAN NOT NULL DEFAULT FALSE,

    -- Tracking
    created_by_user_id BIGINT REFERENCES app_user(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT programma_stato_check
        CHECK (stato IN ('bozza', 'attivo', 'archiviato')),
    CONSTRAINT programma_stagione_check
        CHECK (stagione IN ('invernale', 'estiva', 'agosto') OR stagione IS NULL),
    CONSTRAINT programma_validita_check
        CHECK (valido_a >= valido_da),
    CONSTRAINT programma_giornate_check
        CHECK (n_giornate_default >= 1)
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

    -- Scope
    scope_tipo VARCHAR(30) NOT NULL,    -- 'direttrice' | 'codice_linea' | 'categoria_linea' | 'corsa_specifica'
    scope_valore TEXT NOT NULL,         -- es. 'S5', 'MILANO-BERGAMO', 'RE', '12345'

    -- Filtri opzionali
    fascia_oraria_da TIME,              -- nullable
    fascia_oraria_a TIME,               -- nullable; entrambi NULL = 24h
    giorno_tipo_filter_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- '[]' = nessun filtro (tutti i giorni-tipo)
        -- '["feriale"]' = solo feriale, ecc.

    -- Assegnazione
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
    numero_pezzi INTEGER NOT NULL,

    priorita INTEGER NOT NULL DEFAULT 60,
    note TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT regola_scope_tipo_check
        CHECK (scope_tipo IN (
            'direttrice', 'codice_linea', 'categoria_linea', 'corsa_specifica'
        )),
    CONSTRAINT regola_pezzi_check
        CHECK (numero_pezzi >= 1),
    CONSTRAINT regola_fascia_check
        CHECK (
            (fascia_oraria_da IS NULL AND fascia_oraria_a IS NULL)
            OR (fascia_oraria_da IS NOT NULL AND fascia_oraria_a IS NOT NULL)
        )
);

CREATE INDEX idx_regola_programma ON programma_regola_assegnazione(programma_id);
CREATE INDEX idx_regola_scope ON programma_regola_assegnazione(scope_tipo, scope_valore);
CREATE INDEX idx_regola_priorita ON programma_regola_assegnazione(priorita DESC);
```

### 3.2 Esempio popolamento (mini)

```sql
-- Programma invernale Trenord 2025-2026 (bozza)
INSERT INTO programma_materiale (azienda_id, nome, stagione, valido_da, valido_a, stato)
VALUES (1, 'Trenord 2025-2026 invernale', 'invernale', '2025-12-14', '2026-04-30', 'bozza');
-- → id = 1

-- Regola 1: linea S5 in feriale mattina = 3× ALe711
INSERT INTO programma_regola_assegnazione
  (programma_id, scope_tipo, scope_valore,
   fascia_oraria_da, fascia_oraria_a, giorno_tipo_filter_json,
   materiale_tipo_codice, numero_pezzi, priorita)
VALUES
  (1, 'codice_linea', 'S5',
   '04:00:00', '15:59:59', '["feriale"]'::jsonb,
   'ALe711', 3, 80);

-- Regola 2: linea S5 feriale pomeriggio = 6× ALe711 (aggancio implicito alle 16)
INSERT INTO programma_regola_assegnazione
  (programma_id, scope_tipo, scope_valore,
   fascia_oraria_da, fascia_oraria_a, giorno_tipo_filter_json,
   materiale_tipo_codice, numero_pezzi, priorita)
VALUES
  (1, 'codice_linea', 'S5',
   '16:00:00', '23:59:59', '["feriale"]'::jsonb,
   'ALe711', 6, 80);

-- Regola 3: linea S5 weekend = 3× ALe711 sempre
INSERT INTO programma_regola_assegnazione
  (programma_id, scope_tipo, scope_valore,
   giorno_tipo_filter_json,
   materiale_tipo_codice, numero_pezzi, priorita)
VALUES
  (1, 'codice_linea', 'S5',
   '["sabato", "festivo"]'::jsonb,
   'ALe711', 3, 60);
```

### 3.3 Decisioni di design

**Perché JSONB per `giorno_tipo_filter`?** Per supportare set
arbitrari (`["feriale"]`, `["sabato","festivo"]`, `["feriale","sabato","festivo"]` =
nessun filtro). Una colonna ENUM funzionerebbe solo per scelte
singole.

**Perché non normalizzare gli scope in tabelle separate?** Sarebbe più
"pulito" SQL ma complica enormemente l'UI di editing. Una stringa con
`scope_tipo` come discriminante è pragmatica.

**Perché `numero_pezzi` come intero secco?** La versione fungibile
non distingue identità: 3× ALe711 = 3 quantità. La versione
individuale userà tabella di link separata.

**Perché `priorita` numerica e non ordinale di tabella?** Permette al
pianificatore di forzare manualmente l'ordine (es. priorità 95 per
un'eccezione che deve battere persino le `corsa_specifica` default
100).

---

## 4. Risoluzione di una corsa

Funzione pura `risolvi_corsa(corsa, programma) → AssegnazioneRisolta | None`.

### 4.1 Algoritmo

```python
def risolvi_corsa(corsa: CorsaCommerciale, programma: ProgrammaMateriale,
                  data: date) -> AssegnazioneRisolta | None:
    """
    Data una corsa e un programma, ritorna l'assegnazione (rotabile +
    quantità) applicabile in una specifica data, oppure None se
    nessuna regola matcha.
    """
    giorno_tipo = determina_giorno_tipo(data)  # 'feriale' | 'sabato' | 'festivo'

    # Step 1: filtra regole applicabili
    candidate = [
        r for r in programma.regole
        if matches_scope(r, corsa)
        and matches_fascia(r, corsa.ora_partenza)
        and matches_giorno_tipo(r, giorno_tipo)
    ]

    if not candidate:
        return None

    # Step 2: scegli a priorità più alta
    # In caso di parità, vince la più specifica (più filtri attivi)
    candidate.sort(
        key=lambda r: (r.priorita, _specificita(r)),
        reverse=True,
    )
    return AssegnazioneRisolta(
        regola_id=candidate[0].id,
        materiale_tipo_codice=candidate[0].materiale_tipo_codice,
        numero_pezzi=candidate[0].numero_pezzi,
    )


def matches_scope(regola, corsa):
    if regola.scope_tipo == 'codice_linea':
        return corsa.codice_linea == regola.scope_valore
    if regola.scope_tipo == 'direttrice':
        return corsa.direttrice == regola.scope_valore
    if regola.scope_tipo == 'categoria_linea':
        return corsa.categoria == regola.scope_valore
    if regola.scope_tipo == 'corsa_specifica':
        return corsa.numero_treno == regola.scope_valore
    return False


def matches_fascia(regola, ora_partenza):
    if regola.fascia_oraria_da is None and regola.fascia_oraria_a is None:
        return True
    return regola.fascia_oraria_da <= ora_partenza <= regola.fascia_oraria_a


def matches_giorno_tipo(regola, giorno_tipo):
    if not regola.giorno_tipo_filter:
        return True
    return giorno_tipo in regola.giorno_tipo_filter


def _specificita(regola) -> int:
    """Numero di filtri attivi sulla regola (per tie-breaking priorità)."""
    n = 0
    if regola.fascia_oraria_da is not None:
        n += 1
    if regola.giorno_tipo_filter:
        n += 1
    return n
```

### 4.2 Properties algoritmiche

- **Determinismo**: stessa corsa + stesso programma + stessa data →
  stessa assegnazione, sempre.
- **Funzione pura**: nessun side effect, nessuna I/O, testabile in
  isolamento.
- **Performance**: O(N regole) per corsa. Per 10579 corse × 100
  regole = 1M operazioni, < 1 secondo.

### 4.3 Output

```python
@dataclass
class AssegnazioneRisolta:
    regola_id: int                  # ID della regola che ha vinto
    materiale_tipo_codice: str      # FK a materiale_tipo
    numero_pezzi: int               # quantità da impegnare
```

`None` se nessuna regola matcha. Il chiamante (builder) decide cosa
fare in base a `programma.strict_mode`.

---

## 5. Composizione dinamica (aggancio/sgancio)

### 5.1 Il fenomeno reale

Il pianificatore vuole modellare situazioni come (cit. utente):

> *"ALe711 gira con 3 pezzi fino alle 16, poi aggancia altri 3 pezzi
> per fascia pendolare. Il giro continua fino alla successiva fascia
> pendolare della mattina dopo, poi sgancia i 3 pezzi originari."*

### 5.2 Modellazione tramite regole sovrapposte

Nel modello v0.1, l'aggancio/sgancio **emerge naturalmente** dalla
sovrapposizione di regole con fasce orarie diverse:

```
Regola A: S5 feriale 04:00-15:59 → 3× ALe711   (priorità 80)
Regola B: S5 feriale 16:00-23:59 → 6× ALe711   (priorità 80)
```

Quando l'algoritmo costruisce un giro che attraversa le 16:00 sulla
linea S5:

1. Risolve la corsa delle 15:30 → 3 pezzi
2. Risolve la corsa delle 16:30 → 6 pezzi
3. Detecta il **delta `+3`** alla transizione di fascia
4. Genera un evento di **aggancio** (`giro_blocco.tipo_blocco='aggancio'`)
   nella stazione opportuna della corsa di transizione

### 5.3 Algoritmo di rilevamento delta

```python
def rileva_eventi_composizione(blocchi_giro: list[BloccoCorsa]) -> list[EventoComposizione]:
    """
    Analizza la sequenza di blocchi del giro e annota i punti dove la
    composizione cambia (aggancio/sgancio).
    """
    eventi = []
    composizione_prev = None
    for blocco in blocchi_giro:
        composizione_curr = blocco.assegnazione.numero_pezzi
        if composizione_prev is not None:
            delta = composizione_curr - composizione_prev
            if delta > 0:
                eventi.append(EventoComposizione(
                    tipo='aggancio',
                    pezzi_delta=delta,
                    stazione=blocco.codice_origine,
                    timestamp=blocco.ora_partenza,
                ))
            elif delta < 0:
                eventi.append(EventoComposizione(
                    tipo='sgancio',
                    pezzi_delta=delta,
                    stazione=blocco.codice_origine,
                    timestamp=blocco.ora_partenza,
                ))
        composizione_prev = composizione_curr
    return eventi
```

### 5.4 Persistenza

Estensione minima del modello esistente: `giro_blocco` ha già un
campo `tipo_blocco`. Aggiungiamo i valori `'aggancio'` e `'sgancio'`
all'enum, con metadata in JSONB.

```sql
-- Update enum check constraint
ALTER TABLE giro_blocco
  DROP CONSTRAINT giro_blocco_tipo_check;
ALTER TABLE giro_blocco
  ADD CONSTRAINT giro_blocco_tipo_check
  CHECK (tipo_blocco IN (
    'corsa_commerciale', 'materiale_vuoto',
    'sosta_capolinea', 'sosta_intermedia', 'sosta_deposito',
    'aggancio', 'sgancio'
  ));
```

### 5.5 Limiti del v0.1

L'aggancio/sgancio dello stesso pezzo che "girava prima da solo" (cit.
utente) è una relazione **trasversale** tra giri diversi: il pezzo
ALe711#X esce dal giro A e entra nel giro B. Nella **versione
fungibile** non tracciamo identità di pezzi, quindi non possiamo
modellare esplicitamente questa transizione: emerge solo come "il
giro B ha numero_pezzi maggiore di prima, e le risorse libere a quella
stazione lo permettono".

La **versione individuale** (futura, §8) introdurrà entità
`rotabile_individuale` con `id`/`matricola` e tabelle di link
`giro_pezzo_assegnazione` per tracciare ogni pezzo singolarmente.
Allora l'aggancio diventa "pezzo P si stacca dal giro A alle 15:59 e
si attacca al giro B alle 16:00".

---

## 6. Edge case + strict mode

### 6.1 Sovrapposizione di regole

Più regole matchano una stessa corsa.

**Risoluzione**: ordina per `(priorita DESC, specificita DESC)` e prendi
la prima. Esempio:

| Regola | Scope | Fascia | Priorità | Specificità |
|---|---|---|---|---|
| R1 | S5 | 04:00-15:59 feriale | 80 | 2 |
| R2 | S5 | nessun filtro | 60 | 0 |
| R3 | corsa 12345 | nessun filtro | 100 | 0 |

Una corsa S5 feriale alle 10:00, numero treno 99999:
- R1 matcha (80, spec 2)
- R2 matcha (60, spec 0)
- R3 non matcha (numero diverso)
- Vince R1 ✓

Una corsa S5 numero 12345 alle 10:00 feriale:
- R1, R2, R3 tutte matchano
- Vince R3 (priorità 100)

### 6.2 Corsa senza regola applicabile

`programma.strict_mode == True`:
- L'algoritmo solleva `ProgrammaIncompletoError(corsa_id=...)`
- Nessun giro generato finché il programma non è completo

`programma.strict_mode == False` (default):
- La corsa va in `output.corse_residue: list[CorsaResidua]`
- Warning loggato
- Gli altri giri sono comunque generati

### 6.3 Cambio composizione su corsa di confine

Una corsa parte alle 15:55 (regola "fino alle 16 = 3 pezzi") e arriva
alle 16:25 (regola "dalle 16 = 6 pezzi"). Cosa succede?

**Convenzione**: la **partenza** della corsa decide. La corsa parte
alle 15:55 → match regola mattutina (3 pezzi). L'aggancio dei
restanti 3 pezzi avviene **dopo** l'arrivo, sulla corsa successiva
del giro.

Questa è una semplificazione ragionevole — l'aggancio realistico
avviene in stazione, non in viaggio. Le **corse di confine vanno
verificate manualmente** dal pianificatore se le fasce orarie creano
sovrapposizioni problematiche.

### 6.4 Capacità materiale (vincolo di dotazione)

Indipendente dal programma, la verifica di dotazione è
**responsabilità del builder**: dato il programma + giorni_target +
flotta in `localita_manutenzione_dotazione`, il builder controlla che
la quantità di pezzi richiesti **simultaneamente** non ecceda la
dotazione della località manutenzione.

Esempio: località Fiorenza ha 64 ALe711. Se il programma genera 25
giri attivi alla stessa ora che richiedono 3 pezzi ciascuno = 75 pezzi.
**Errore di sovra-allocazione** → builder fallisce o avvisa, a seconda
di `strict_mode`.

### 6.5 Materiale non in dotazione

Una regola assegna `materiale_tipo='ETR526'`, ma nessuna
`localita_manutenzione` ha quel tipo in dotazione (errore di config).

**Detection**: validazione del programma alla pubblicazione (cambio
stato bozza → attivo). Si calcola `set(regole.materiale_tipo) -
set(materiali_disponibili)`. Se non vuoto → errore di pubblicazione.

### 6.6 Programmi sovrapposti

Più programmi attivi nella stessa data per la stessa azienda. Quale
vince?

**Convenzione**: le finestre temporali devono essere **non
sovrapponibili** per programmi della stessa stagione e azienda. Un
constraint applicativo (non SQL, perché complesso da esprimere)
controlla questa proprietà alla pubblicazione.

Sovrapposizioni **legittime** sono solo tra stagioni diverse (es.
"invernale 14/12-30/04" + "estiva 01/05-30/09" non si sovrappongono).
Programmi feriale/weekend distinti **non sono questo**: un singolo
programma con regole filtrate per `giorno_tipo` è la modellazione
corretta.

---

## 7. Esempi reali Trenord

### 7.1 Linea S5 con cambio fascia pendolare

Pianificatore vuole: ALe711 in singola la mattina, in doppia il
pomeriggio (16-21), poi singola la sera. Sabato e festivi sempre in
singola.

```
Programma "Trenord 2025-2026 invernale", regole linea S5:

Regola 1 — codice_linea='S5', fascia 04:00-15:59, giorni [feriale]
  → 3× ALe711, priorità 80

Regola 2 — codice_linea='S5', fascia 16:00-21:00, giorni [feriale]
  → 6× ALe711, priorità 80

Regola 3 — codice_linea='S5', fascia 21:01-23:59, giorni [feriale]
  → 3× ALe711, priorità 80

Regola 4 — codice_linea='S5', no fascia, giorni [sabato, festivo]
  → 3× ALe711, priorità 60
```

Una corsa S5 feriale alle 17:30 → matcha Regola 2 → 6 pezzi.
Una corsa S5 sabato alle 17:30 → solo Regola 4 matcha → 3 pezzi.

### 7.2 Linea TILO Svizzera (rotabile dedicato)

```
Regola — direttrice='MILANO-CHIASSO-LUGANO', no fascia, no filtro giorni
  → 4× ETR524, priorità 60
```

Tutte le corse della direttrice sono coperte. Il programma valida che
ETR524 sia in dotazione di POOL_TILO_SVIZZERA.

### 7.3 Treno speciale singolo

Una corsa con caratteristiche uniche (es. notturno, treno turistico):

```
Regola — corsa_specifica='12345', no fascia, no filtro giorni
  → 1× ALe711, priorità 100
```

Sempre vincente per quella corsa, indipendente da regole linea più
generali.

### 7.4 Default per linea senza specifiche

```
Regola — categoria_linea='RE', no fascia, no filtro giorni
  → 4× ALe711, priorità 20
```

Cattura tutto il regio express che non abbia regole più specifiche.
Buona difesa contro `strict_mode` falsificato.

---

## 8. Versione individuale (futura)

### 8.1 Quando si attiva

Quando il modulo manutenzione richiederà di **tracciare quale pezzo
fisico** copre quale giro, per:
- Allineare giri con fermate calendario
- Pianificare revisioni (ogni N km/giorni il pezzo X va fermo)
- Audit operativo ("il pezzo P che giorno è andato dove?")

### 8.2 Modello dati anticipato

Nuova tabella `rotabile_individuale`:

```sql
CREATE TABLE rotabile_individuale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matricola VARCHAR(50) NOT NULL UNIQUE,    -- es. 'ALe711-001'
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice),
    localita_manutenzione_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id),
    stato VARCHAR(20) DEFAULT 'attivo',       -- 'attivo' | 'in_revisione' | 'fermo'
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

Se `NULL`: mantiene la semantica fungibile (qualsiasi 3 pezzi
disponibili). Se popolato: assegnazione esplicita ai pezzi
identificati.

Questo permette **migrazione graduale**: programmi legacy fungibili,
nuovi programmi individuali, coesistenza nello stesso DB.

---

## 9. Riferimenti

- `docs/LOGICA-COSTRUZIONE.md` §3 — Algoritmo A che usa il programma materiale
- `docs/MODELLO-DATI.md` v0.5 — modello concettuale a piramide
- `docs/SCHEMA-DATI-NATIVO.md` §3 (anagrafica) e §5 (giri)
- `docs/IMPORT-PDE.md` — fonte input PdE (corse_commerciale)
- `data/depositi_manutenzione_trenord_seed.json` — dotazione Trenord (1884 pezzi, 69 tipi)
- `TN-UPDATE.md` entry Sprint 4.0 — diario decisioni

---

## 10. Stato

- [x] **v0.1 — disegno fungibile** (questo documento, da validare con utente)
- [ ] v0.2 — refinement post-feedback utente
- [ ] Sub-sprint 4.1 — migration 0005 + modello SQLAlchemy
- [ ] Sub-sprint 4.2 — funzione pura `risolvi_corsa`
- [ ] Sub-sprint 4.3 — API CRUD
- [ ] Sub-sprint 4.4 — builder algoritmico che usa il programma
- [ ] Sub-sprint 4.5 — CLI + smoke test su PdE Trenord reale
- [ ] (futuro) v1.0 — versione individuale (rotabile per matricola)

---

**Fine draft v0.1**. Aspetto feedback utente prima di procedere a 4.1.
