# MIGRAZIONE DATI — dal DB attuale al modello v0.5 (draft v0.1)

> **Stato**: bozza in revisione. **Niente codice ancora.**
> Scopo: pianificare tabella per tabella la migrazione del DB attuale
> (centrato su `train_segment`) verso il modello v0.5 di
> `docs/MODELLO-DATI.md` (centrato su una piramide a 4 livelli).
>
> Riferimento normativo: `docs/MODELLO-DATI.md` v0.5 + `docs/METODO-DI-LAVORO.md`
> (regola 6: preservare, non distruggere; regola 5: verifica prima del
> commit).

---

## 0. Manifesto della migrazione

**Pattern strangler. Nessun "big bang".**

Il codice esistente (parser PDF Gantt, TurnValidator, cv_registry,
auto_builder, frontend Gantt) è il valore principale del progetto e
**non si tocca finché le tabelle nuove non sono validate in parallelo**.

**Tre regole non negoziabili:**

1. **Mai DROP, mai TRUNCATE prima della validazione**. Le tabelle
   nuove **affiancano** le vecchie. Quando il sistema legge dalle
   nuove con successo per N giorni → si valuta la deprecazione delle
   vecchie. Mai prima.
2. **Migrazioni idempotenti**. Ogni step deve poter essere rieseguito
   senza effetti collaterali (`CREATE TABLE IF NOT EXISTS`,
   `ALTER TABLE ADD COLUMN IF NOT EXISTS`, `INSERT OR IGNORE`).
   Il pattern `_run_migration()` di `db.py` esistente è il riferimento.
3. **Backfill in tre fasi**: (1) crea schema vuoto, (2) popola con
   dati derivati da tabelle esistenti, (3) confronta nuove vs vecchie
   con query di consistenza prima di promuovere come fonte primaria.

**Conseguenza pratica**: la migrazione **non rompe niente**. Se a metà
qualcosa va storto, la app continua a funzionare sulle tabelle vecchie.
Le nuove sono "in shadow" finché non validate.

---

## 1. Mappa di sopravvivenza — vecchio → nuovo

Sintesi dello stato di ogni tabella DB attuale.

| Tabella attuale | Destino | Note |
|-----------------|---------|------|
| `material_turn` | **rinomina logica** → `giro_materiale` | Tabella esistente arricchita con FK a `localita_manutenzione`. ALTER ADD COLUMN, no nuova tabella. |
| `train_segment` | **scompone** in `corsa_commerciale` (LIV 1) + `giro_blocco` (LIV 2) | Backfill da segmenti esistenti via numero treno. |
| `day_variant` | **rinomina logica** → `giro_variante` | Esiste già, va arricchita con `giro_giornata_id` FK |
| `non_train_event` | **assorbita** in `giro_blocco` con `tipo_blocco='evento'` | Eventi REFEZ/S.COMP diventano blocchi di tipo evento |
| `pdc_turn` | **rinomina logica** → `turno_pdc` | ALTER ADD COLUMN per nuovi campi (`azienda_id`, `ciclo_giorni`) |
| `pdc_turn_day` | **rinomina logica** → `turno_pdc_giornata` | Resta con stessa struttura |
| `pdc_block` | **rinomina logica** → `turno_pdc_blocco` | ALTER ADD COLUMN: `corsa_commerciale_id`, `corsa_materiale_vuoto_id`, `giro_blocco_id` (link triangolare) |
| `pdc_train_periodicity` | **deprecata gradualmente** | La periodicità vivrà in `corsa_commerciale.valido_in_date`. Per ora resta in shadow. |
| `saved_shift` | **invariata** | Tabella UI editor turni, fuori scope migrazione modello |
| `weekly_shift` | **invariata** | idem |
| `shift_day_variant` | **invariata** | idem |
| `users` | **invariata** | |
| `depot` | **arricchita** | ALTER ADD COLUMN: `tipi_personale_ammessi`, già esiste `company` (= `azienda`) |
| `depot_enabled_line` | **invariata** | |
| `depot_enabled_material` | **invariata** | |
| `train_allocation` | **invariata in v1** | Resta come tabella di pool/allocazione, da ripensare in v2 |
| `pdc_fr_approved` | **invariata** | |
| `cv_ledger` | **invariata** | Resta come registro CV |
| `train_route_cache` | **invariata** | Cache ARTURO Live, intoccabile |
| `pdc_import` | **invariata** | Log import |

**Tabelle completamente nuove** (non esistono oggi):
- LIV 1: `corsa_commerciale`, `corsa_composizione`, `corsa_materiale_vuoto`
- LIV 2: `giro_giornata`, `giro_blocco`, `versione_base_giro`,
  `giro_finestra_validita`, `revisione_provvisoria`,
  `revisione_provvisoria_blocco`, `revisione_provvisoria_pdc`
- LIV 3: nessuna tabella nuova in v1, solo ALTER su esistenti
- LIV 4: `persona`, `assegnazione_giornata`, `indisponibilita_persona`
- Supporto: `azienda`, `stazione`, `materiale_tipo`,
  `localita_manutenzione`, `localita_manutenzione_dotazione`

**Totale**: ~17 tabelle nuove + ~5 ALTER su esistenti.

---

## 2. DAG dipendenze — ordine esecuzione

Le tabelle vanno create in ordine di dipendenza FK. Diagramma a strati:

```
STRATO 0 — anagrafiche pure (zero FK)
   azienda
   stazione
   materiale_tipo

STRATO 1 — anagrafiche derivate (FK a strato 0)
   localita_manutenzione                  (→ azienda, stazione)
   depot_extension                         (ALTER: + tipi_personale_ammessi)

STRATO 2 — corse commerciali (LIV 1)
   corsa_commerciale                       (→ azienda, stazione)
   corsa_composizione                      (→ corsa_commerciale)
   corsa_materiale_vuoto                   (→ azienda, stazione)

STRATO 3 — giro materiale (LIV 2)
   giro_materiale                          (→ azienda, localita_manutenzione,
                                              materiale_tipo)
   versione_base_giro                      (→ giro_materiale)
   giro_finestra_validita                  (→ versione_base_giro)
   giro_giornata                           (→ giro_materiale)
   giro_variante                           (→ giro_giornata)
   giro_blocco                             (→ giro_variante,
                                              corsa_commerciale,
                                              corsa_materiale_vuoto)

STRATO 4 — revisioni provvisorie (LIV 2 estensione)
   revisione_provvisoria                   (→ giro_materiale)
   revisione_provvisoria_blocco            (→ revisione_provvisoria)
   revisione_provvisoria_pdc               (→ revisione_provvisoria,
                                              turno_pdc)

STRATO 5 — turno PdC (LIV 3)
   turno_pdc_extension                     (ALTER: + azienda_id, ciclo_giorni)
   turno_pdc_giornata_extension            (nessun cambio strutturale)
   turno_pdc_blocco_extension              (ALTER: + corsa_commerciale_id,
                                              corsa_materiale_vuoto_id,
                                              giro_blocco_id)

STRATO 6 — anagrafica + pianificazione (LIV 4)
   persona                                 (→ azienda, depot)
   assegnazione_giornata                   (→ persona, turno_pdc_giornata)
   indisponibilita_persona                 (→ persona)

STRATO 7 — anagrafica supporto secondaria (popolata DOPO i giri)
   localita_manutenzione_dotazione         (→ localita_manutenzione)
```

Ogni strato si esegue solo dopo che il precedente è stato creato e
validato.

---

## 3. Fase A — Anagrafiche (Strato 0+1)

### 3.1 `azienda`

**Schema**:
```
id                  PK
codice              TEXT UNIQUE NOT NULL  -- 'trenord', 'tilo', 'sad'...
nome                TEXT
normativa_pdc_json  TEXT DEFAULT '{}'     -- regole 8h30, 5h30 per ora vuoto
attivo              INTEGER DEFAULT 1
```

**Backfill**: 1 riga `('trenord', 'Trenord SRL', '{}', 1)` da migrazione.

**Validazione**: `SELECT COUNT(*) >= 1`.

### 3.2 `stazione`

**Schema**:
```
codice              PK TEXT          -- 'S01066'
nome                TEXT NOT NULL    -- 'MILANO CADORNA'
nomi_alternativi    TEXT DEFAULT '[]' -- json
rete                TEXT             -- 'RFI', 'FN'
sede_deposito       INTEGER DEFAULT 0
azienda_id          INTEGER NOT NULL FK
```

**Backfill**: la prima volta che importeremo il PdE Numbers,
genereremo l'anagrafica (10580 corse → ~600 stazioni distinte).
Inizialmente, però, popoliamo dai nomi presenti in `train_segment`
(c'è già una lista canonicalizzata).

**Validazione**: `COUNT >= 100` dopo backfill da train_segment.

### 3.3 `materiale_tipo`

**Schema**:
```
codice              PK TEXT          -- 'Coradia526', 'Vivalto', 'TAF'
nome_commerciale    TEXT
componenti_json     TEXT DEFAULT '{}'
velocita_max_kmh    INTEGER
posti_per_pezzo     INTEGER
azienda_id          INTEGER FK
```

**Backfill**: dal seed `data/depositi_manutenzione_trenord_seed.json`
estraiamo i tipi distinti dal campo `tipi_materiale_unici` di ogni
deposito. Anche da `depot_enabled_material` esistente.

**Validazione**: contiene almeno i ~50 tipi visti nei turni materiali
(ALe710, ALe711, nBBW, TN-Ale204-A1, ecc.).

### 3.4 `localita_manutenzione` + dotazione

**Schema**:
```
-- localita_manutenzione
id                              PK
codice                          TEXT UNIQUE NOT NULL  -- 'IMPMAN_MILANO_FIORENZA'
nome_canonico                   TEXT
nomi_alternativi                TEXT DEFAULT '[]'
stazione_collegata_codice       TEXT FK   -- nullable
azienda_id                      INTEGER FK NOT NULL
is_pool_esterno                 INTEGER DEFAULT 0
azienda_proprietaria_esterna    TEXT      -- 'TILO' se is_pool_esterno
attivo                          INTEGER DEFAULT 1

-- localita_manutenzione_dotazione
id                              PK
localita_manutenzione_id        FK NOT NULL
materiale_tipo_codice           FK NOT NULL  -- → materiale_tipo
quantita                        INTEGER NOT NULL
note                            TEXT DEFAULT ''
UNIQUE(localita_id, materiale_tipo_codice)
```

**Backfill**:
- `localita_manutenzione`: 7 righe dal seed JSON (FIORENZA, NOVATE,
  CAMNAGO, CREMONA, LECCO, ISEO, POOL_TILO_SVIZZERA).
- `dotazione`: ~80 righe (somma tipi_pezzo × 7 depositi) dal seed.

**Validazione**:
```sql
SELECT codice, COUNT(*) AS n_tipi, SUM(quantita) AS pezzi
FROM localita_manutenzione lm
JOIN localita_manutenzione_dotazione d ON lm.id = d.localita_manutenzione_id
GROUP BY codice;
-- atteso: MILANO_FIORENZA → n_tipi=49, pezzi=974
```

### 3.5 ALTER `depot`

```sql
ALTER TABLE depot ADD COLUMN tipi_personale_ammessi TEXT DEFAULT 'PdC';
-- enum: 'PdC', 'CT', 'ENTRAMBI'
```

`company` esiste già in `depot`, è il `azienda`. Tradurre da string
('trenord') a FK in fase finale, non ora.

**Validazione**: tutte le righe esistenti hanno `tipi_personale_ammessi='PdC'`.

---

## 4. Fase B — Corse commerciali (Strato 2, LIV 1)

### 4.1 `corsa_commerciale`

**Schema** (estratto, vedi `MODELLO-DATI.md §LIV 1` per lista completa):
```
id                          PK
numero_treno                TEXT NOT NULL      -- '10603'
rete                        TEXT               -- 'FN' / 'RFI'
categoria                   TEXT               -- 'R', 'RE', 'S'
codice_linea                TEXT               -- 'R22'
direttrice                  TEXT
codice_origine              TEXT FK            -- → stazione
codice_destinazione         TEXT FK            -- → stazione
ora_partenza                TEXT               -- '06:39:00'
ora_arrivo                  TEXT
min_tratta                  INTEGER
km_tratta                   REAL
valido_da                   TEXT
valido_a                    TEXT
codice_periodicita          TEXT
periodicita_breve           TEXT
treno_garantito_feriale     INTEGER
treno_garantito_festivo     INTEGER
fascia_oraria               TEXT
giorni_per_mese_json        TEXT               -- {gen: 31, feb: 28, ...}
valido_in_date_json         TEXT               -- denormalizzata, calcolata
azienda_id                  INTEGER FK NOT NULL
import_source               TEXT DEFAULT 'pde'
import_run_id               INTEGER FK         -- → corsa_import_run
imported_at                 TEXT

UNIQUE(numero_treno, valido_da, azienda_id)
INDEX idx on (numero_treno, valido_da)
INDEX idx on (codice_origine, ora_partenza)
```

**Tabella di accompagnamento** `corsa_import_run` per tracciabilità:
```
id, source_file, imported_at, n_corse, hash_file
```

**Backfill primo giro**: importer dedicato (Fase C del codice, **non
ora**) leggerà PdE Numbers e popolerà ~10580 righe.

**Validazione**:
- `COUNT(*) ≈ 10580` dopo import PdE
- `valido_in_date_json` lunghezza media ~330 (giorni in cui circola)
- nessun NULL su `numero_treno`, `codice_origine`, `codice_destinazione`

### 4.2 `corsa_composizione`

Figlia: una riga per ogni delle 9 combinazioni stagione × giorno-tipo.

**Schema**:
```
id                              PK
corsa_commerciale_id            FK NOT NULL
stagione                        TEXT  -- 'invernale', 'estiva', 'agosto'
giorno_tipo                     TEXT  -- 'feriale', 'sabato', 'festivo'
categoria_posti                 TEXT
doppia_composizione             INTEGER
tipologia_treno                 TEXT
vincolo_dichiarato              TEXT
categoria_bici                  TEXT
categoria_prm                   TEXT

UNIQUE(corsa_commerciale_id, stagione, giorno_tipo)
```

**Backfill**: 9 righe per corsa × 10580 corse = ~95K righe.
Direttamente dal PdE Numbers.

### 4.3 `corsa_materiale_vuoto`

**Schema** (vedi `MODELLO-DATI.md §LIV 1 corsa_materiale_vuoto`):
```
id                              PK
numero_treno_vuoto              TEXT NOT NULL  -- 'U316', '93058'
codice_origine                  TEXT FK
codice_destinazione             TEXT FK
ora_partenza                    TEXT
ora_arrivo                      TEXT
min_tratta                      INTEGER
km_tratta                       REAL
origine                         TEXT NOT NULL  -- 'importato_pde' | 'generato_da_giro_materiale' | 'manuale'
giro_materiale_id               INTEGER FK     -- nullable
valido_in_date_json             TEXT
azienda_id                      INTEGER FK NOT NULL

UNIQUE(numero_treno_vuoto, valido_da, giro_materiale_id)
```

**Backfill iniziale**: tabella **vuota**. Si popolerà man mano che
l'algoritmo di costruzione giro materiale (futura Fase E codice) genera
treni di servizio. I numeri vuoti nei `train_segment` esistenti (es.
93058, 28220) verranno migrati come `origine='importato_pde'`
(approssimazione: arrivano dal PDF turno materiale, non dal PdE — il
flag andrebbe rinominato in `origine='importato_da_pdf_giro'`,
discutere in v0.6).

---

## 5. Fase C — Giro materiale (Strato 3, LIV 2)

### 5.1 ALTER `material_turn` → arricchimento per `giro_materiale`

Non rinominiamo la tabella SQL (rischio rompere troppi punti del
codice). La rinomina è **logica**: nel nuovo modello le query la
chiamano `giro_materiale`, ma fisicamente resta `material_turn` con
ALTER per i campi nuovi.

```sql
ALTER TABLE material_turn ADD COLUMN azienda_id INTEGER DEFAULT 1;
ALTER TABLE material_turn ADD COLUMN localita_manutenzione_partenza_id INTEGER FK;
ALTER TABLE material_turn ADD COLUMN localita_manutenzione_arrivo_id INTEGER FK;
ALTER TABLE material_turn ADD COLUMN materiale_tipo_codice TEXT FK;  -- nullable
ALTER TABLE material_turn ADD COLUMN descrizione_materiale TEXT DEFAULT '';
ALTER TABLE material_turn ADD COLUMN numero_giornate INTEGER DEFAULT 0;
ALTER TABLE material_turn ADD COLUMN km_media_giornaliera REAL DEFAULT 0;
ALTER TABLE material_turn ADD COLUMN km_media_annua REAL DEFAULT 0;
ALTER TABLE material_turn ADD COLUMN posti_1cl INTEGER DEFAULT 0;
ALTER TABLE material_turn ADD COLUMN posti_2cl INTEGER DEFAULT 0;
```

**Backfill**: dal `data/depositi_manutenzione_trenord_seed.json`
(turni_dettaglio[]), risolvendo `deposito` (string) a FK
`localita_manutenzione_partenza_id`.

### 5.2 `versione_base_giro`

```sql
CREATE TABLE versione_base_giro (
    id PK,
    giro_materiale_id INTEGER UNIQUE FK NOT NULL,
    data_deposito TEXT,
    source_file TEXT,
    imported_at TEXT
)
```

**Backfill**: 1 riga per turno esistente in `material_turn`.

### 5.3 `giro_finestra_validita`

```sql
CREATE TABLE giro_finestra_validita (
    id PK,
    versione_base_giro_id INTEGER FK NOT NULL,
    valido_da TEXT NOT NULL,
    valido_a TEXT NOT NULL,
    seq INTEGER DEFAULT 1,
    UNIQUE(versione_base_giro_id, seq)
)
```

**Backfill**: 1 riga per versione_base, da `material_turn.source_file`
desumiamo le date 2/3/26 → 12/12/2026 (default annuale). I casi
discontinui (1161) li gestiamo manualmente via script una tantum dopo
verifica con utente.

### 5.4 `giro_giornata` (nuova)

```sql
CREATE TABLE giro_giornata (
    id PK,
    giro_materiale_id INTEGER FK NOT NULL,
    numero_giornata INTEGER NOT NULL,  -- 1, 2, ...
    UNIQUE(giro_materiale_id, numero_giornata)
)
```

**Backfill**: deriva da `material_turn.total_segments` e
`day_variant.day_index` (esistenti). Per ogni `(material_turn_id,
day_index)` distinto in `day_variant`, una riga.

### 5.5 ALTER `day_variant` → arricchimento per `giro_variante`

```sql
ALTER TABLE day_variant ADD COLUMN giro_giornata_id INTEGER FK;
ALTER TABLE day_variant ADD COLUMN variant_index INTEGER DEFAULT 0;
ALTER TABLE day_variant ADD COLUMN validita_dates_apply_json TEXT DEFAULT '[]';
ALTER TABLE day_variant ADD COLUMN validita_dates_skip_json TEXT DEFAULT '[]';
```

**Backfill**: popolare `giro_giornata_id` con join su
(material_turn_id, day_index). I JSON date list restano vuoti finché
non scriviamo l'importer dedicato.

### 5.6 `giro_blocco` (nuova, scompone train_segment)

```sql
CREATE TABLE giro_blocco (
    id PK,
    giro_variante_id INTEGER FK NOT NULL,
    seq INTEGER NOT NULL,
    tipo_blocco TEXT NOT NULL,         -- 'corsa_commerciale' | 'materiale_vuoto'
                                       --  | 'sosta_disponibile' | 'manovra'
    corsa_commerciale_id INTEGER FK,    -- popolato se tipo='corsa_commerciale'
    corsa_materiale_vuoto_id INTEGER FK,
    stazione_da_codice TEXT FK,
    stazione_a_codice TEXT FK,
    ora_inizio TEXT,
    ora_fine TEXT,
    descrizione TEXT DEFAULT '',
    train_segment_id_legacy INTEGER FK -- traccia l'origine durante migrazione
)
```

**Backfill**: per ogni `train_segment` esistente con
`day_index, material_turn_id, seq`, una riga in `giro_blocco`.
Linking a `corsa_commerciale_id` via match `(numero_treno, valido_da)`.
Match miss → `tipo_blocco='materiale_vuoto'` (fallback).

**Strategia incrementale**: durante il backfill, **NON cancelliamo**
`train_segment`. Ogni `giro_blocco` ha campo
`train_segment_id_legacy` che punta all'originale. Questo permette di:
- Confrontare nuove vs vecchie con query SQL
- Rollback selettivi se serve
- Rimuovere il legacy_id solo dopo cutover finale

**Validazione**:
```sql
-- Ogni train_segment ha un giro_blocco corrispondente
SELECT COUNT(*) FROM train_segment ts
LEFT JOIN giro_blocco gb ON gb.train_segment_id_legacy = ts.id
WHERE gb.id IS NULL;
-- atteso: 0
```

---

## 6. Fase D — Revisioni provvisorie (Strato 4)

Tutte le tabelle revisione partono **vuote**. Si popoleranno quando
implementeremo l'import delle revisioni provvisorie da PDF (futura
fase codice).

### 6.1 `revisione_provvisoria` (nuova)

```sql
CREATE TABLE revisione_provvisoria (
    id PK,
    giro_materiale_id INTEGER FK NOT NULL,
    codice_revisione TEXT NOT NULL,         -- '1100-REV-2026-A'
    causa TEXT NOT NULL,                    -- 'interruzione_rfi' | 'sciopero' |
                                            --  'manutenzione_straordinaria' |
                                            --  'evento_speciale' | 'altro'
    comunicazione_esterna_rif TEXT,         -- 'PIR-2026-345'
    descrizione_evento TEXT,
    finestra_da TEXT NOT NULL,
    finestra_a TEXT NOT NULL,
    data_pubblicazione TEXT,
    source_file TEXT,
    imported_at TEXT
)
```

### 6.2 `revisione_provvisoria_blocco`

I blocchi in override sulla versione base (override per tipologia:
modifica/sostituzione/aggiunta/cancellazione).

```sql
CREATE TABLE revisione_provvisoria_blocco (
    id PK,
    revisione_id INTEGER FK NOT NULL,
    operazione TEXT NOT NULL,  -- 'modifica' | 'aggiungi' | 'cancella'
    giro_blocco_originale_id INTEGER FK,  -- da modificare/cancellare
    -- + tutti i campi di giro_blocco se è una modifica/aggiunta
    seq INTEGER,
    tipo_blocco TEXT,
    corsa_commerciale_id INTEGER FK,
    corsa_materiale_vuoto_id INTEGER FK,
    stazione_da_codice TEXT FK,
    stazione_a_codice TEXT FK,
    ora_inizio TEXT,
    ora_fine TEXT
)
```

### 6.3 `revisione_provvisoria_pdc` (cascading)

```sql
CREATE TABLE revisione_provvisoria_pdc (
    id PK,
    revisione_giro_id INTEGER FK NOT NULL,  -- → revisione_provvisoria del giro
    turno_pdc_id INTEGER FK NOT NULL,
    codice_revisione TEXT NOT NULL,
    finestra_da TEXT NOT NULL,
    finestra_a TEXT NOT NULL,
    -- ereditati dalla rev del giro, denormalizzati per query veloci
    UNIQUE(revisione_giro_id, turno_pdc_id)
)
```

E una analoga `revisione_provvisoria_pdc_blocco` per i blocchi PdC
modificati. Schema dettagliato in fase implementativa.

---

## 7. Fase E — Turno PdC (Strato 5)

Tutto ALTER su tabelle esistenti, nessuna creazione.

### 7.1 ALTER `pdc_turn`

```sql
ALTER TABLE pdc_turn ADD COLUMN azienda_id INTEGER DEFAULT 1;
ALTER TABLE pdc_turn ADD COLUMN ciclo_giorni INTEGER DEFAULT 7;
```

### 7.2 ALTER `pdc_block`

Il vero linking del triangolo PdE-MAT-PdC:

```sql
ALTER TABLE pdc_block ADD COLUMN corsa_commerciale_id INTEGER FK;
ALTER TABLE pdc_block ADD COLUMN corsa_materiale_vuoto_id INTEGER FK;
ALTER TABLE pdc_block ADD COLUMN giro_blocco_id INTEGER FK;
```

**Backfill**: per ogni `pdc_block` con `train_id` valorizzato, cerca
`corsa_commerciale` con stesso `numero_treno` e `valido_da` ≤
`pdc_turn.valid_from` ≤ `valido_a`. Linkalo. Match miss →
`corsa_materiale_vuoto_id`.

**Validazione (vincolo §6 modello v0.5)**:
```sql
-- "Triangolo chiuso": ogni blocco PdC condotta/vettura su corsa
-- commerciale ha un giro_blocco corrispondente.
SELECT COUNT(*)
FROM pdc_block pb
LEFT JOIN giro_blocco gb ON gb.corsa_commerciale_id = pb.corsa_commerciale_id
WHERE pb.block_type IN ('CONDOTTA', 'VETTURA')
  AND pb.corsa_commerciale_id IS NOT NULL
  AND gb.id IS NULL;
-- atteso: 0
```

Se il count > 0: c'è una corsa che il PdC dichiara di guidare ma
che nessun giro materiale copre. Errore di consistenza dati →
notifica utente e correzione manuale.

---

## 8. Fase F — Anagrafica personale (Strato 6, LIV 4)

### 8.1 `persona`

```sql
CREATE TABLE persona (
    id PK,
    codice_dipendente TEXT UNIQUE NOT NULL,  -- 'M00845'
    nome TEXT NOT NULL,
    cognome TEXT NOT NULL,
    profilo TEXT NOT NULL,                    -- 'PdC' | 'CT' (in v1 solo PdC)
    sede_residenza_id INTEGER FK,             -- → depot
    qualifiche_json TEXT DEFAULT '[]',
    matricola_attiva INTEGER DEFAULT 1,
    data_assunzione TEXT,
    azienda_id INTEGER FK NOT NULL
)
```

**Backfill**: tabella vuota. L'utente popolerà via UI o import CSV
in fase successiva.

### 8.2 `assegnazione_giornata`

```sql
CREATE TABLE assegnazione_giornata (
    id PK,
    persona_id INTEGER FK NOT NULL,
    data TEXT NOT NULL,                       -- '2026-04-27'
    turno_pdc_giornata_id INTEGER FK,         -- popolato (CT in v2)
    stato TEXT DEFAULT 'pianificato',         -- 'pianificato' | 'confermato' | 'sostituito' | 'annullato'
    sostituisce_persona_id INTEGER FK,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(persona_id, data)
)
```

### 8.3 `indisponibilita_persona`

```sql
CREATE TABLE indisponibilita_persona (
    id PK,
    persona_id INTEGER FK NOT NULL,
    tipo TEXT NOT NULL,                       -- 'ferie' | 'malattia' | 'congedo' |
                                              -- 'ROL' | 'sciopero' | 'formazione'
    data_inizio TEXT NOT NULL,
    data_fine TEXT NOT NULL,
    approvato INTEGER DEFAULT 0,
    note TEXT DEFAULT ''
)
```

---

## 9. Fase G — Validazione e cutover

Dopo aver popolato gli strati 0-6, prima di considerare la migrazione
"completa", eseguire i 5 vincoli di consistenza di
`MODELLO-DATI.md §6` come query SQL.

### 9.1 I 5 vincoli come query

1. **Triangolo chiuso PdE-MAT-PdC**:
   ```sql
   SELECT COUNT(*) FROM pdc_block pb
   LEFT JOIN giro_blocco gb ON gb.corsa_commerciale_id = pb.corsa_commerciale_id
   WHERE pb.block_type IN ('CONDOTTA','VETTURA')
     AND pb.corsa_commerciale_id IS NOT NULL
     AND gb.id IS NULL;
   -- atteso: 0
   ```
2. **Coerenza temporale** (tolleranza ±1 min):
   ```sql
   SELECT COUNT(*) FROM pdc_block pb
   JOIN corsa_commerciale cc ON cc.id = pb.corsa_commerciale_id
   WHERE ABS(strftime('%s', pb.start_time) - strftime('%s', cc.ora_partenza)) > 60
      OR ABS(strftime('%s', pb.end_time) - strftime('%s', cc.ora_arrivo)) > 60;
   -- atteso: 0
   ```
3. **Una persona-una giornata**: già garantito da UNIQUE.
4. **Indisponibilità rispettate**:
   ```sql
   SELECT COUNT(*) FROM assegnazione_giornata ag
   JOIN indisponibilita_persona ip
     ON ip.persona_id = ag.persona_id
    AND ag.data BETWEEN ip.data_inizio AND ip.data_fine
    AND ip.approvato = 1
   WHERE ag.stato != 'annullato';
   -- atteso: 0
   ```
5. **Stessa azienda**:
   ```sql
   SELECT COUNT(*) FROM giro_materiale gm
   JOIN giro_blocco gb ON gb.giro_variante_id IN (...)
   JOIN corsa_commerciale cc ON cc.id = gb.corsa_commerciale_id
   WHERE gm.azienda_id != cc.azienda_id;
   -- atteso: 0
   ```

Tutti e 5 questi controlli vivono in `tests/test_data_consistency.py`
(da scrivere) che gira in CI dopo ogni migrazione.

### 9.2 Cutover graduale

Quando i 5 vincoli ritornano 0:

1. **Codice in shadow read** (settimane 1-2 dopo cutover): il backend
   continua a leggere da tabelle vecchie. Ma in parallelo legge dalle
   nuove e logga differenze.
2. **Cutover read**: il backend legge dalle nuove. Le vecchie restano
   popolate per safety. Frontend invariato.
3. **Cutover write**: gli importer scrivono SOLO sulle nuove. Le
   vecchie smettono di crescere.
4. **Validazione N+30 giorni**: se nessun bug critico → si valuta
   deprecazione vecchie.
5. **Drop tabelle vecchie** (`train_segment`, `non_train_event`, ecc.):
   solo dopo conferma esplicita utente. Backup fisico DB prima del DROP.

---

## 10. Cosa NON tocchiamo nella v1 di questa migrazione

Esplicito per evitare scope creep:

- **`saved_shift`, `weekly_shift`, `shift_day_variant`**: tabelle UI
  editor turni. Non legate al modello v0.5 in modo diretto. Restano.
- **Frontend Gantt**: nessuna modifica. Continua a leggere dagli
  endpoint esistenti che leggono da train_segment. Quando il backend
  fa il "cutover read", la fonte cambia ma l'API resta uguale.
- **`auto_builder.py`, `build_from_material.py`, TurnValidator**: zero
  modifiche al codice in questa fase. Migrano dopo.
- **Multi-azienda completo**: SAD/TILO restano voce in `azienda` ma
  nessun import reale.
- **Performance tuning**: indici minimi (quelli essenziali). Tuning
  query post-cutover.

---

## 11. Fasi di esecuzione effettiva (ordine)

Questo è il **TODO list ad alto livello** della migrazione, da
spacchettare in commit individuali quando inizieremo a scrivere
codice. **Ognuna è 1 commit + 1 test di consistenza.**

| # | Fase | Output | Test |
|---|------|--------|------|
| 1 | Crea `azienda`, popola Trenord | 1 riga `trenord` | `SELECT COUNT(*) >= 1` |
| 2 | Crea `materiale_tipo`, popola dal seed | ~50 righe | conta tipi distinti |
| 3 | Crea `stazione`, popola da `train_segment` | ~600 righe | `COUNT >= 100` |
| 4 | Crea `localita_manutenzione`, popola dal seed | 7 righe | `COUNT = 7` |
| 5 | Crea `localita_manutenzione_dotazione` | ~80 righe | sum quantita per dep |
| 6 | ALTER `depot` (+ tipi_personale_ammessi) | tutte righe DEFAULT 'PdC' | check default |
| 7 | Crea `corsa_commerciale` (vuota) + indici | schema OK, 0 righe | `COUNT = 0` |
| 8 | Crea `corsa_composizione` (vuota) | schema OK, 0 righe | `COUNT = 0` |
| 9 | Crea `corsa_materiale_vuoto` (vuota) | schema OK, 0 righe | `COUNT = 0` |
| 10 | ALTER `material_turn` (+ campi LIV 2) | schema OK | `PRAGMA table_info` |
| 11 | Crea `versione_base_giro`, popola da `material_turn` | 1:1 con material_turn | `COUNT = COUNT(material_turn)` |
| 12 | Crea `giro_finestra_validita`, default 1 finestra annuale | 1 per versione_base | check |
| 13 | Crea `giro_giornata`, popola da `day_variant` | 1 per `(mt_id, day_index)` distinto | check |
| 14 | ALTER `day_variant` (+ giro_giornata_id) | linking back | nessun NULL |
| 15 | Crea `giro_blocco`, popola da `train_segment` | 1:1 con train_segment | `COUNT = COUNT(train_segment)` |
| 16 | ALTER `pdc_turn` (+ azienda_id, ciclo_giorni) | tutti default | check |
| 17 | ALTER `pdc_block` (+ FK corsa, giro_blocco) | NULL inizialmente | schema OK |
| 18 | Backfill linking `pdc_block.corsa_commerciale_id` (richiede import PdE prima) | matches >= 80% | report mismatch |
| 19 | Crea revisione_* (vuote) | schema OK | `COUNT = 0` |
| 20 | Crea `persona`, `assegnazione_giornata`, `indisponibilita_persona` (vuote) | schema OK | `COUNT = 0` |
| 21 | Esegui 5 vincoli consistenza | tutti 0 | passing |

**Stop al passo 21.** Solo dopo, con OK utente, si parte con codice
importer e consumer.

---

## 12. Decisioni aperte

Da risolvere con utente prima di iniziare passo 1:

1. **Mantenere nomi SQL vecchi (`material_turn`, `pdc_block`...) o rinominare in `giro_materiale`, `turno_pdc_blocco`**?
   - **Proposta**: mantenere fisici, rinominare logici. Riduce rischio di rompere API/codice esistente.
2. **L'import PdE Numbers (passo 18 dipende) avverrà PRIMA della migrazione strutturale o DOPO**?
   - **Proposta**: la migrazione strutturale può essere fatta a vuoto (passi 1-17, 19-21). Il backfill 18 si fa quando arriva il primo import PdE.
3. **Backup DB prima del passo 1?**
   - **Proposta SI obbligatorio**: copia `turni.db` → `turni.db.backup-pre-migrazione-vXX-{data}` come primo step.
4. **Versionamento migrazioni**: usare un file `migrations/NNN_descrizione.sql` o restare dentro `db.py` con `_run_migration()`?
   - **Proposta**: restare in `db.py` ma con funzioni numerate
     `_run_migration_001_azienda()`, `_run_migration_002_stazione()`...
     così leggibili e idempotenti.

---

**Fine draft v0.1.** Da revisionare con l'utente prima di toccare DB.
