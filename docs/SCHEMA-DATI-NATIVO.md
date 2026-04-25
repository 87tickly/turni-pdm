# SCHEMA DATI NATIVO — DDL PostgreSQL eseguibile (draft v0.1)

> Materializzazione di `MODELLO-DATI.md` v0.5 in DDL SQL **pronto da
> eseguire** su PostgreSQL 16.
>
> Questo documento è la **specifica per la prima migrazione Alembic**
> (`alembic/versions/0001_initial_schema.py`). Quando si scriverà il
> codice, i `CREATE TABLE` qui sotto diventano `op.create_table(...)`.
>
> **Niente codice Python in questo file**, solo SQL puro che documenta
> lo schema in modo eseguibile manualmente con `psql`.

---

## Indice

1. [Convenzioni](#1-convenzioni)
2. [Estensioni Postgres](#2-estensioni-postgres)
3. [Schema strato 0 — anagrafica](#3-schema-strato-0--anagrafica)
4. [Schema strato 1 — corse commerciali (LIV 1)](#4-schema-strato-1--corse-commerciali-liv-1)
5. [Schema strato 2 — giro materiale (LIV 2)](#5-schema-strato-2--giro-materiale-liv-2)
6. [Schema strato 3 — revisioni provvisorie](#6-schema-strato-3--revisioni-provvisorie)
7. [Schema strato 4 — turno PdC (LIV 3)](#7-schema-strato-4--turno-pdc-liv-3)
8. [Schema strato 5 — anagrafica personale (LIV 4)](#8-schema-strato-5--anagrafica-personale-liv-4)
9. [Schema strato 6 — autenticazione e audit](#9-schema-strato-6--autenticazione-e-audit)
10. [Indici secondari](#10-indici-secondari)
11. [Vincoli di consistenza (vincoli §6 di MODELLO-DATI)](#11-vincoli-di-consistenza)
12. [Seed iniziale Trenord](#12-seed-iniziale-trenord)

---

## 1. Convenzioni

### Naming

- **Tabelle**: `snake_case`, singolare quando possibile (`persona`,
  `giro_materiale`), plurale solo se naturale (`indisponibilita_persona`)
- **Colonne PK**: sempre `id` come `BIGSERIAL` o `BIGINT GENERATED ALWAYS AS IDENTITY`
- **Colonne FK**: `<entità_target>_id` (es. `azienda_id`, `corsa_commerciale_id`)
- **Colonne data/ora**: `_at` per timestamp (`created_at`, `imported_at`),
  `_da/_a` per range date (`valido_da`, `finestra_da`), `_in` per JSON
  array di date (`valido_in_date`)
- **Colonne booleane**: prefisso `is_` (`is_pool_esterno`, `is_admin`)

### Tipi standard

| Concetto | Tipo Postgres | Note |
|----------|---------------|------|
| ID surrogati | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Postgres-native, no sequence manuale |
| Stringhe corte (codici) | `VARCHAR(50)` con CHECK | Es. `azienda.codice` |
| Stringhe lunghe (nomi, descrizioni) | `TEXT` | No limite arbitrario |
| Date | `DATE` | Senza timezone |
| Orari giornalieri | `TIME` | `'06:39:00'` |
| Timestamp | `TIMESTAMPTZ` | Con timezone, sempre UTC |
| Importi/quantità | `INTEGER` o `NUMERIC(p,s)` | Integer per pezzi, NUMERIC per km |
| JSON strutturato | `JSONB` | Indicizzabile con GIN |
| Liste di date | `JSONB` (array) | Es. `valido_in_date_json` |
| Booleani | `BOOLEAN NOT NULL DEFAULT FALSE` | Mai NULL su bool |
| Enum | `VARCHAR(N) CHECK (col IN (...))` | Più flessibile di TYPE ENUM |

### Foreign keys

- `ON DELETE RESTRICT` di default (preserva, non distruggere)
- `ON DELETE CASCADE` solo per relazioni di composizione strette (es.
  `giro_blocco` → `giro_variante` → `giro_giornata` → `giro_materiale`)
- `ON UPDATE CASCADE` quasi mai (PK sono surrogati immutabili)

### Indici

- Indici **espliciti** alla fine di ogni strato
- PK e UNIQUE auto-creano già indici
- FK auto-creano già indici (Postgres non sempre, controllare —
  vedi §10)

---

## 2. Estensioni Postgres

```sql
-- Per indici trigram su ricerche fuzzy (futuro: cerca persona/stazione)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Niente uuid-ossp: usiamo BIGINT IDENTITY, non UUID
-- Niente btree_gin: i nostri JSONB hanno indici GIN nativi quando servono
```

---

## 3. Schema strato 0 — anagrafica

### `azienda`

Multi-tenant primario. Ogni entità sotto porta `azienda_id`.

```sql
CREATE TABLE azienda (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codice VARCHAR(50) NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    normativa_pdc_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_attiva BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT azienda_codice_format CHECK (codice ~ '^[a-z0-9_]+$')
);
```

### `stazione`

Anagrafica canonica delle stazioni.

```sql
CREATE TABLE stazione (
    codice VARCHAR(20) PRIMARY KEY,
    nome TEXT NOT NULL,
    nomi_alternativi_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    rete VARCHAR(10),
    is_sede_deposito BOOLEAN NOT NULL DEFAULT FALSE,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT stazione_codice_format CHECK (codice ~ '^S[0-9]+$' OR codice ~ '^[A-Z]+$')
);
```

### `materiale_tipo`

Anagrafica dei rotabili (tipi di pezzi: ALe710, nBBW, E464N...).

```sql
CREATE TABLE materiale_tipo (
    codice VARCHAR(50) PRIMARY KEY,
    nome_commerciale TEXT,
    famiglia TEXT,                                     -- 'TSR', 'Vivalto', 'Coradia 526', ...
    componenti_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    velocita_max_kmh INTEGER,
    posti_per_pezzo INTEGER,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `localita_manutenzione`

Sede del materiale fisico (IMPMAN FIORENZA, NOVATE, ecc.).

```sql
CREATE TABLE localita_manutenzione (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codice VARCHAR(80) NOT NULL UNIQUE,                -- 'IMPMAN_MILANO_FIORENZA'
    nome_canonico TEXT NOT NULL,
    nomi_alternativi_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    stazione_collegata_codice VARCHAR(20) REFERENCES stazione(codice) ON DELETE SET NULL,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    is_pool_esterno BOOLEAN NOT NULL DEFAULT FALSE,
    azienda_proprietaria_esterna VARCHAR(100),         -- 'TILO' se pool esterno
    is_attiva BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `localita_manutenzione_dotazione`

Inventario per località (somma dei pezzi per tipo).

```sql
CREATE TABLE localita_manutenzione_dotazione (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    localita_manutenzione_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id) ON DELETE CASCADE,
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
    quantita INTEGER NOT NULL CHECK (quantita >= 0),
    famiglia_rotabile TEXT,
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(localita_manutenzione_id, materiale_tipo_codice)
);
```

### `depot` (sede personale PdC/CT)

Diversa da `localita_manutenzione`. È la sede del **personale**.

```sql
CREATE TABLE depot (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codice VARCHAR(80) NOT NULL UNIQUE,                -- 'ALESSANDRIA', 'GARIBALDI_ALE'
    display_name TEXT NOT NULL,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    stazione_principale_codice VARCHAR(20) REFERENCES stazione(codice) ON DELETE SET NULL,
    tipi_personale_ammessi VARCHAR(20) NOT NULL DEFAULT 'PdC',
        -- 'PdC' | 'CT' | 'ENTRAMBI'
    is_attivo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT depot_tipi_personale_check
        CHECK (tipi_personale_ammessi IN ('PdC', 'CT', 'ENTRAMBI'))
);
```

### `depot_linea_abilitata`

Quale deposito copre quali linee (replicabilità del vecchio
`depot_enabled_line` ma riadattato).

```sql
CREATE TABLE depot_linea_abilitata (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    depot_id BIGINT NOT NULL REFERENCES depot(id) ON DELETE CASCADE,
    stazione_a_codice VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    stazione_b_codice VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    UNIQUE(depot_id, stazione_a_codice, stazione_b_codice)
);
```

### `depot_materiale_abilitato`

Quale deposito può guidare quali tipi materiale.

```sql
CREATE TABLE depot_materiale_abilitato (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    depot_id BIGINT NOT NULL REFERENCES depot(id) ON DELETE CASCADE,
    materiale_tipo_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice) ON DELETE RESTRICT,
    UNIQUE(depot_id, materiale_tipo_codice)
);
```

---

## 4. Schema strato 1 — corse commerciali (LIV 1)

### `corsa_commerciale`

Una corsa = una riga del PdE Numbers. ~10580 righe per Trenord.

```sql
CREATE TABLE corsa_commerciale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

    -- Identificativi
    numero_treno VARCHAR(20) NOT NULL,
    rete VARCHAR(10),                                  -- 'FN' | 'RFI'
    numero_treno_rfi VARCHAR(20),
    numero_treno_fn VARCHAR(20),
    categoria VARCHAR(20),                             -- 'R' | 'RE' | 'S'
    codice_linea VARCHAR(20),
    direttrice TEXT,

    -- Geografia
    codice_origine VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    codice_destinazione VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    codice_inizio_cds VARCHAR(20) REFERENCES stazione(codice),
    codice_fine_cds VARCHAR(20) REFERENCES stazione(codice),

    -- Tempi
    ora_partenza TIME NOT NULL,
    ora_arrivo TIME NOT NULL,
    ora_inizio_cds TIME,
    ora_fine_cds TIME,
    min_tratta INTEGER,
    min_cds INTEGER,
    km_tratta NUMERIC(10,3),
    km_cds NUMERIC(10,3),

    -- Validità
    valido_da DATE NOT NULL,
    valido_a DATE NOT NULL,
    codice_periodicita TEXT,
    periodicita_breve TEXT,
    is_treno_garantito_feriale BOOLEAN NOT NULL DEFAULT FALSE,
    is_treno_garantito_festivo BOOLEAN NOT NULL DEFAULT FALSE,
    fascia_oraria VARCHAR(10),                         -- 'FR' | 'FNR'

    -- Calendario
    giorni_per_mese_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- { "gen": 31, "feb": 28, ..., "anno": 365 }
    valido_in_date_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- ["2025-12-14", "2025-12-15", ...] denormalizzato per query veloci

    -- Aggregati
    totale_km NUMERIC(12,3),
    totale_minuti INTEGER,
    posti_km NUMERIC(15,3),
    velocita_commerciale NUMERIC(8,4),

    -- Source tracking
    import_run_id BIGINT,                              -- → corsa_import_run, definito sotto
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(azienda_id, numero_treno, valido_da)
);
```

### `corsa_composizione`

9 combinazioni (stagione × giorno-tipo) per ogni corsa.

```sql
CREATE TABLE corsa_composizione (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    corsa_commerciale_id BIGINT NOT NULL
        REFERENCES corsa_commerciale(id) ON DELETE CASCADE,
    stagione VARCHAR(20) NOT NULL,                     -- 'invernale' | 'estiva' | 'agosto'
    giorno_tipo VARCHAR(20) NOT NULL,                  -- 'feriale' | 'sabato' | 'festivo'
    categoria_posti TEXT,
    is_doppia_composizione BOOLEAN NOT NULL DEFAULT FALSE,
    tipologia_treno TEXT,
    vincolo_dichiarato TEXT,
    categoria_bici VARCHAR(10),
    categoria_prm VARCHAR(10),
    UNIQUE(corsa_commerciale_id, stagione, giorno_tipo),
    CONSTRAINT corsa_composizione_stagione_check
        CHECK (stagione IN ('invernale', 'estiva', 'agosto')),
    CONSTRAINT corsa_composizione_giorno_check
        CHECK (giorno_tipo IN ('feriale', 'sabato', 'festivo'))
);
```

### `corsa_materiale_vuoto`

Treni di servizio (U316, 28183, ecc.) generati dal builder o
importati. Tabella sorella di `corsa_commerciale`.

```sql
CREATE TABLE corsa_materiale_vuoto (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    numero_treno_vuoto VARCHAR(20) NOT NULL,           -- 'U316', '28183', '93058'

    codice_origine VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    codice_destinazione VARCHAR(20) NOT NULL REFERENCES stazione(codice),
    ora_partenza TIME NOT NULL,
    ora_arrivo TIME NOT NULL,
    min_tratta INTEGER,
    km_tratta NUMERIC(10,3),

    origine VARCHAR(40) NOT NULL,
        -- 'importato_pde' | 'generato_da_giro_materiale' | 'manuale'
    giro_materiale_id BIGINT,                          -- popolato se generato per giro
    valido_in_date_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    valido_da DATE,
    valido_a DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT corsa_materiale_vuoto_origine_check
        CHECK (origine IN ('importato_pde', 'generato_da_giro_materiale', 'manuale'))
);
-- FK a giro_materiale aggiunta dopo (dipendenza circolare → ALTER TABLE)
```

### `corsa_import_run`

Tracciabilità ogni import del PdE.

```sql
CREATE TABLE corsa_import_run (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_hash VARCHAR(64),                           -- SHA-256
    n_corse INTEGER NOT NULL DEFAULT 0,
    n_corse_create INTEGER NOT NULL DEFAULT 0,
    n_corse_update INTEGER NOT NULL DEFAULT 0,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    note TEXT
);

ALTER TABLE corsa_commerciale
    ADD CONSTRAINT corsa_commerciale_import_run_fk
    FOREIGN KEY (import_run_id) REFERENCES corsa_import_run(id) ON DELETE SET NULL;
```

---

## 5. Schema strato 2 — giro materiale (LIV 2)

### `giro_materiale`

Un giro = una rotazione fisica di un convoglio.

```sql
CREATE TABLE giro_materiale (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,

    numero_turno VARCHAR(20) NOT NULL,                 -- '1100', '1161A'
    validita_codice VARCHAR(10),                       -- 'P' | 'I' | 'E' (storico)

    tipo_materiale TEXT NOT NULL,                      -- '1npBDL+5nBC-clim+1E464N'
    descrizione_materiale TEXT,                        -- 'PR 270 - PPF 120 - m.174 - MD'
    materiale_tipo_codice VARCHAR(50) REFERENCES materiale_tipo(codice),
        -- famiglia (es. 'Coradia526')

    numero_giornate INTEGER NOT NULL CHECK (numero_giornate >= 1),
    km_media_giornaliera NUMERIC(10,2),
    km_media_annua NUMERIC(12,2),
    posti_1cl INTEGER NOT NULL DEFAULT 0,
    posti_2cl INTEGER NOT NULL DEFAULT 0,

    localita_manutenzione_partenza_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id) ON DELETE RESTRICT,
    localita_manutenzione_arrivo_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id) ON DELETE RESTRICT,

    stato VARCHAR(20) NOT NULL DEFAULT 'bozza',        -- 'bozza' | 'pubblicato' | 'archiviato'
    generation_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(azienda_id, numero_turno),
    CONSTRAINT giro_materiale_stato_check
        CHECK (stato IN ('bozza', 'pubblicato', 'archiviato'))
);

-- FK circolare risolta
ALTER TABLE corsa_materiale_vuoto
    ADD CONSTRAINT corsa_materiale_vuoto_giro_fk
    FOREIGN KEY (giro_materiale_id) REFERENCES giro_materiale(id) ON DELETE SET NULL;
```

### `versione_base_giro`

1:1 con `giro_materiale`. Versione pubblicata in offerta commerciale
annuale.

```sql
CREATE TABLE versione_base_giro (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    giro_materiale_id BIGINT NOT NULL UNIQUE
        REFERENCES giro_materiale(id) ON DELETE CASCADE,
    data_deposito DATE,
    source_file TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `giro_finestra_validita`

1+ finestre per versione (es. Turno 1161 ha 2 finestre discontinue).

```sql
CREATE TABLE giro_finestra_validita (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    versione_base_giro_id BIGINT NOT NULL
        REFERENCES versione_base_giro(id) ON DELETE CASCADE,
    valido_da DATE NOT NULL,
    valido_a DATE NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    UNIQUE(versione_base_giro_id, seq),
    CONSTRAINT giro_finestra_validita_range CHECK (valido_da <= valido_a)
);
```

### `giro_giornata`

Giornata del ciclo (G1, G2, ..., GN).

```sql
CREATE TABLE giro_giornata (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    giro_materiale_id BIGINT NOT NULL
        REFERENCES giro_materiale(id) ON DELETE CASCADE,
    numero_giornata INTEGER NOT NULL CHECK (numero_giornata >= 1),
    UNIQUE(giro_materiale_id, numero_giornata)
);
```

### `giro_variante`

Variante calendario di una giornata (LV / S / D / SD / F + date specifiche).

```sql
CREATE TABLE giro_variante (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    giro_giornata_id BIGINT NOT NULL
        REFERENCES giro_giornata(id) ON DELETE CASCADE,
    variant_index INTEGER NOT NULL DEFAULT 0,
    validita_testo TEXT NOT NULL DEFAULT 'GG',
    validita_dates_apply_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    validita_dates_skip_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE(giro_giornata_id, variant_index)
);
```

### `giro_blocco`

Singolo evento della sequenza giornaliera (corsa, materiale vuoto,
sosta, manovra).

```sql
CREATE TABLE giro_blocco (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    giro_variante_id BIGINT NOT NULL
        REFERENCES giro_variante(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    tipo_blocco VARCHAR(40) NOT NULL,
        -- 'corsa_commerciale' | 'materiale_vuoto'
        --  | 'sosta_disponibile' | 'manovra'

    corsa_commerciale_id BIGINT REFERENCES corsa_commerciale(id) ON DELETE RESTRICT,
    corsa_materiale_vuoto_id BIGINT REFERENCES corsa_materiale_vuoto(id) ON DELETE RESTRICT,

    stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
    stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
    ora_inizio TIME,
    ora_fine TIME,
    descrizione TEXT,

    UNIQUE(giro_variante_id, seq),
    CONSTRAINT giro_blocco_tipo_check
        CHECK (tipo_blocco IN ('corsa_commerciale', 'materiale_vuoto',
                               'sosta_disponibile', 'manovra')),
    CONSTRAINT giro_blocco_link_coerente
        CHECK (
            (tipo_blocco = 'corsa_commerciale' AND corsa_commerciale_id IS NOT NULL
             AND corsa_materiale_vuoto_id IS NULL)
         OR (tipo_blocco = 'materiale_vuoto' AND corsa_materiale_vuoto_id IS NOT NULL
             AND corsa_commerciale_id IS NULL)
         OR (tipo_blocco IN ('sosta_disponibile', 'manovra')
             AND corsa_commerciale_id IS NULL AND corsa_materiale_vuoto_id IS NULL)
        )
);
```

---

## 6. Schema strato 3 — revisioni provvisorie

### `revisione_provvisoria`

Modifica temporanea con causa esterna esplicita.

```sql
CREATE TABLE revisione_provvisoria (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    giro_materiale_id BIGINT NOT NULL
        REFERENCES giro_materiale(id) ON DELETE CASCADE,
    codice_revisione VARCHAR(50) NOT NULL,
    causa VARCHAR(40) NOT NULL,
    comunicazione_esterna_rif TEXT,
    descrizione_evento TEXT NOT NULL,
    finestra_da DATE NOT NULL,
    finestra_a DATE NOT NULL,
    data_pubblicazione DATE NOT NULL DEFAULT CURRENT_DATE,
    source_file TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT revisione_provvisoria_causa_check
        CHECK (causa IN ('interruzione_rfi', 'sciopero',
                         'manutenzione_straordinaria', 'evento_speciale', 'altro')),
    CONSTRAINT revisione_provvisoria_finestra_range
        CHECK (finestra_da <= finestra_a),
    UNIQUE(giro_materiale_id, codice_revisione)
);
```

### `revisione_provvisoria_blocco`

Override sui blocchi del giro per la finestra di revisione.

```sql
CREATE TABLE revisione_provvisoria_blocco (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revisione_id BIGINT NOT NULL
        REFERENCES revisione_provvisoria(id) ON DELETE CASCADE,
    operazione VARCHAR(20) NOT NULL,
        -- 'modifica' | 'aggiungi' | 'cancella'
    giro_blocco_originale_id BIGINT REFERENCES giro_blocco(id) ON DELETE SET NULL,
    seq INTEGER,
    tipo_blocco VARCHAR(40),
    corsa_commerciale_id BIGINT REFERENCES corsa_commerciale(id),
    corsa_materiale_vuoto_id BIGINT REFERENCES corsa_materiale_vuoto(id),
    stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
    stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
    ora_inizio TIME,
    ora_fine TIME,
    CONSTRAINT revisione_blocco_op_check
        CHECK (operazione IN ('modifica', 'aggiungi', 'cancella'))
);
```

### `revisione_provvisoria_pdc`

Cascading: revisione del giro → revisione dei turni PdC che lo coprivano.

```sql
CREATE TABLE revisione_provvisoria_pdc (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revisione_giro_id BIGINT NOT NULL
        REFERENCES revisione_provvisoria(id) ON DELETE CASCADE,
    turno_pdc_id BIGINT NOT NULL,                      -- → turno_pdc(id), aggiunto sotto
    codice_revisione VARCHAR(50) NOT NULL,
    finestra_da DATE NOT NULL,
    finestra_a DATE NOT NULL,
    UNIQUE(revisione_giro_id, turno_pdc_id)
);
```

(FK a `turno_pdc` aggiunta dopo creazione di `turno_pdc`.)

---

## 7. Schema strato 4 — turno PdC (LIV 3)

### `turno_pdc`

```sql
CREATE TABLE turno_pdc (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    codice VARCHAR(50) NOT NULL,                       -- 'ALOR_C [65046]'
    impianto VARCHAR(80) NOT NULL,                     -- depot codice oppure free string per ora
    profilo VARCHAR(40) NOT NULL DEFAULT 'Condotta',
    ciclo_giorni INTEGER NOT NULL DEFAULT 7 CHECK (ciclo_giorni BETWEEN 1 AND 14),
    valido_da DATE NOT NULL,
    valido_a DATE,                                     -- NULL se vigente
    source_file TEXT,
    generation_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    stato VARCHAR(20) NOT NULL DEFAULT 'bozza',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT turno_pdc_stato_check
        CHECK (stato IN ('bozza', 'pubblicato', 'archiviato')),
    UNIQUE(azienda_id, codice, valido_da)
);

-- FK aggiunta dopo creazione di turno_pdc
ALTER TABLE revisione_provvisoria_pdc
    ADD CONSTRAINT revisione_provvisoria_pdc_turno_fk
    FOREIGN KEY (turno_pdc_id) REFERENCES turno_pdc(id) ON DELETE CASCADE;
```

### `turno_pdc_giornata`

Giornata del ciclo PdC.

```sql
CREATE TABLE turno_pdc_giornata (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    turno_pdc_id BIGINT NOT NULL REFERENCES turno_pdc(id) ON DELETE CASCADE,
    numero_giornata INTEGER NOT NULL CHECK (numero_giornata BETWEEN 1 AND 14),
    variante_calendario VARCHAR(20) NOT NULL DEFAULT 'LMXGV',
        -- 'LMXGV' | 'S' | 'D' | 'SD' | 'F' | custom
    stazione_inizio VARCHAR(20) REFERENCES stazione(codice),
    stazione_fine VARCHAR(20) REFERENCES stazione(codice),
    inizio_prestazione TIME,
    fine_prestazione TIME,
    prestazione_min INTEGER NOT NULL DEFAULT 0,
    condotta_min INTEGER NOT NULL DEFAULT 0,
    refezione_min INTEGER NOT NULL DEFAULT 0,
    km INTEGER NOT NULL DEFAULT 0,
    is_notturno BOOLEAN NOT NULL DEFAULT FALSE,
    is_riposo BOOLEAN NOT NULL DEFAULT FALSE,
    is_disponibile BOOLEAN NOT NULL DEFAULT FALSE,
    riposo_min INTEGER NOT NULL DEFAULT 0,
    UNIQUE(turno_pdc_id, numero_giornata, variante_calendario)
);
```

### `turno_pdc_blocco`

Singolo evento della giornata PdC.

```sql
CREATE TABLE turno_pdc_blocco (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    turno_pdc_giornata_id BIGINT NOT NULL
        REFERENCES turno_pdc_giornata(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    tipo_evento VARCHAR(20) NOT NULL,
        -- 'CONDOTTA' | 'VETTURA' | 'REFEZ' | 'ACCp' | 'ACCa'
        --  | 'CVp' | 'CVa' | 'PK' | 'SCOMP' | 'PRESA' | 'FINE'

    corsa_commerciale_id BIGINT REFERENCES corsa_commerciale(id) ON DELETE RESTRICT,
    corsa_materiale_vuoto_id BIGINT REFERENCES corsa_materiale_vuoto(id) ON DELETE RESTRICT,
    giro_blocco_id BIGINT REFERENCES giro_blocco(id) ON DELETE SET NULL,
        -- denormalizzato per join veloce con il giro corrispondente

    stazione_da_codice VARCHAR(20) REFERENCES stazione(codice),
    stazione_a_codice VARCHAR(20) REFERENCES stazione(codice),
    ora_inizio TIME,
    ora_fine TIME,
    durata_min INTEGER,
    is_accessori_maggiorati BOOLEAN NOT NULL DEFAULT FALSE,
    cv_parent_blocco_id BIGINT REFERENCES turno_pdc_blocco(id) ON DELETE SET NULL,
    accessori_note TEXT,
    fonte_orario VARCHAR(20) NOT NULL DEFAULT 'parsed',
        -- 'parsed' | 'interpolated' | 'user' | 'generated'
    UNIQUE(turno_pdc_giornata_id, seq),
    CONSTRAINT turno_pdc_blocco_tipo_check
        CHECK (tipo_evento IN ('CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa',
                                'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE'))
);
```

---

## 8. Schema strato 5 — anagrafica personale (LIV 4)

### `persona`

```sql
CREATE TABLE persona (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    codice_dipendente VARCHAR(40) NOT NULL,
    nome TEXT NOT NULL,
    cognome TEXT NOT NULL,
    profilo VARCHAR(20) NOT NULL DEFAULT 'PdC',
    sede_residenza_id BIGINT REFERENCES depot(id) ON DELETE SET NULL,
    qualifiche_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_matricola_attiva BOOLEAN NOT NULL DEFAULT TRUE,
    data_assunzione DATE,
    user_id BIGINT,                                    -- → user(id), aggiunto dopo
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(azienda_id, codice_dipendente),
    CONSTRAINT persona_profilo_check
        CHECK (profilo IN ('PdC', 'CT', 'MANOVRA', 'COORD'))
);
```

### `assegnazione_giornata`

```sql
CREATE TABLE assegnazione_giornata (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    persona_id BIGINT NOT NULL REFERENCES persona(id) ON DELETE RESTRICT,
    data DATE NOT NULL,
    turno_pdc_giornata_id BIGINT REFERENCES turno_pdc_giornata(id) ON DELETE SET NULL,
    -- futuro: turno_ct_giornata_id BIGINT REFERENCES turno_ct_giornata(id),
    stato VARCHAR(20) NOT NULL DEFAULT 'pianificato',
    sostituisce_persona_id BIGINT REFERENCES persona(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(persona_id, data),
    CONSTRAINT assegnazione_stato_check
        CHECK (stato IN ('pianificato', 'confermato', 'sostituito', 'annullato'))
);
```

### `indisponibilita_persona`

```sql
CREATE TABLE indisponibilita_persona (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    persona_id BIGINT NOT NULL REFERENCES persona(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL,
    is_approvato BOOLEAN NOT NULL DEFAULT FALSE,
    approvato_da_user_id BIGINT,                       -- → user(id), aggiunto dopo
    approvato_at TIMESTAMPTZ,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT indisponibilita_tipo_check
        CHECK (tipo IN ('ferie', 'malattia', 'congedo', 'ROL', 'sciopero', 'formazione')),
    CONSTRAINT indisponibilita_range_check
        CHECK (data_inizio <= data_fine)
);
```

---

## 9. Schema strato 6 — autenticazione e audit

### `app_user`

Account dell'applicazione. **Diverso** da `persona` (anagrafica
dipendente). Una persona può avere zero o un user (PdC che usa l'app);
un admin può non avere persona collegata.

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    persona_id BIGINT REFERENCES persona(id) ON DELETE SET NULL,
    azienda_id BIGINT NOT NULL REFERENCES azienda(id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE persona
    ADD CONSTRAINT persona_user_fk
    FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE SET NULL;

ALTER TABLE indisponibilita_persona
    ADD CONSTRAINT indisponibilita_approvatore_fk
    FOREIGN KEY (approvato_da_user_id) REFERENCES app_user(id) ON DELETE SET NULL;
```

### `app_user_ruolo`

Un user può avere più ruoli (vedi `RUOLI-E-DASHBOARD.md` §1).

```sql
CREATE TABLE app_user_ruolo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    ruolo VARCHAR(40) NOT NULL,
    UNIQUE(app_user_id, ruolo),
    CONSTRAINT app_user_ruolo_check
        CHECK (ruolo IN ('PIANIFICATORE_GIRO', 'PIANIFICATORE_PDC',
                         'MANUTENZIONE', 'GESTIONE_PERSONALE',
                         'PERSONALE_PDC', 'ADMIN'))
);
```

### `notifica`

Notifiche cross-ruolo (vedi `RUOLI-E-DASHBOARD.md` §9).

```sql
CREATE TABLE notifica (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    destinatario_user_id BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    tipo VARCHAR(60) NOT NULL,
    titolo TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_letta BOOLEAN NOT NULL DEFAULT FALSE,
    letta_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `audit_log`

Tracciamento modifiche critiche.

```sql
CREATE TABLE audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
    azione VARCHAR(60) NOT NULL,
    target_tipo VARCHAR(60),
    target_id BIGINT,
    payload_json JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 10. Indici secondari

Postgres crea automaticamente indici per PK e UNIQUE. Le FK **non**
generano indici automatici — vanno aggiunti.

```sql
-- LIV 1
CREATE INDEX idx_corsa_numero ON corsa_commerciale(numero_treno);
CREATE INDEX idx_corsa_origine_partenza ON corsa_commerciale(codice_origine, ora_partenza);
CREATE INDEX idx_corsa_destinazione_arrivo ON corsa_commerciale(codice_destinazione, ora_arrivo);
CREATE INDEX idx_corsa_validita ON corsa_commerciale(valido_da, valido_a);
CREATE INDEX idx_corsa_azienda ON corsa_commerciale(azienda_id);
CREATE INDEX idx_corsa_valido_in_date_gin ON corsa_commerciale USING GIN (valido_in_date_json);

CREATE INDEX idx_corsa_composizione_corsa ON corsa_composizione(corsa_commerciale_id);

CREATE INDEX idx_corsa_vuoto_numero ON corsa_materiale_vuoto(numero_treno_vuoto);
CREATE INDEX idx_corsa_vuoto_giro ON corsa_materiale_vuoto(giro_materiale_id);

-- LIV 2
CREATE INDEX idx_giro_azienda ON giro_materiale(azienda_id);
CREATE INDEX idx_giro_localita_partenza ON giro_materiale(localita_manutenzione_partenza_id);
CREATE INDEX idx_giro_stato ON giro_materiale(stato);

CREATE INDEX idx_finestra_versione ON giro_finestra_validita(versione_base_giro_id);
CREATE INDEX idx_finestra_dates ON giro_finestra_validita(valido_da, valido_a);

CREATE INDEX idx_giornata_giro ON giro_giornata(giro_materiale_id);
CREATE INDEX idx_variante_giornata ON giro_variante(giro_giornata_id);
CREATE INDEX idx_blocco_variante ON giro_blocco(giro_variante_id);
CREATE INDEX idx_blocco_corsa ON giro_blocco(corsa_commerciale_id);

-- LIV 2 estensione (revisioni)
CREATE INDEX idx_revisione_giro ON revisione_provvisoria(giro_materiale_id);
CREATE INDEX idx_revisione_finestra ON revisione_provvisoria(finestra_da, finestra_a);
CREATE INDEX idx_rev_blocco_revisione ON revisione_provvisoria_blocco(revisione_id);
CREATE INDEX idx_rev_pdc_revisione ON revisione_provvisoria_pdc(revisione_giro_id);
CREATE INDEX idx_rev_pdc_turno ON revisione_provvisoria_pdc(turno_pdc_id);

-- LIV 3
CREATE INDEX idx_turno_codice ON turno_pdc(codice);
CREATE INDEX idx_turno_impianto ON turno_pdc(impianto);
CREATE INDEX idx_turno_validita ON turno_pdc(valido_da, valido_a);
CREATE INDEX idx_turno_azienda ON turno_pdc(azienda_id);
CREATE INDEX idx_turno_stato ON turno_pdc(stato);

CREATE INDEX idx_giornata_pdc_turno ON turno_pdc_giornata(turno_pdc_id);
CREATE INDEX idx_blocco_pdc_giornata ON turno_pdc_blocco(turno_pdc_giornata_id);
CREATE INDEX idx_blocco_pdc_corsa ON turno_pdc_blocco(corsa_commerciale_id);
CREATE INDEX idx_blocco_pdc_giro_blocco ON turno_pdc_blocco(giro_blocco_id);

-- LIV 4
CREATE INDEX idx_persona_codice ON persona(codice_dipendente);
CREATE INDEX idx_persona_sede ON persona(sede_residenza_id);
CREATE INDEX idx_persona_user ON persona(user_id);
CREATE INDEX idx_persona_cognome_trgm ON persona USING GIN (cognome gin_trgm_ops);
CREATE INDEX idx_persona_nome_trgm ON persona USING GIN (nome gin_trgm_ops);

CREATE INDEX idx_assegnazione_persona ON assegnazione_giornata(persona_id);
CREATE INDEX idx_assegnazione_data ON assegnazione_giornata(data);
CREATE INDEX idx_assegnazione_giornata_pdc ON assegnazione_giornata(turno_pdc_giornata_id);

CREATE INDEX idx_indisponibilita_persona ON indisponibilita_persona(persona_id);
CREATE INDEX idx_indisponibilita_range ON indisponibilita_persona(data_inizio, data_fine);

-- Auth
CREATE INDEX idx_user_persona ON app_user(persona_id);
CREATE INDEX idx_user_ruolo_user ON app_user_ruolo(app_user_id);
CREATE INDEX idx_notifica_destinatario_letta ON notifica(destinatario_user_id, is_letta);
CREATE INDEX idx_audit_target ON audit_log(target_tipo, target_id);
CREATE INDEX idx_audit_actor ON audit_log(actor_user_id, created_at);
```

---

## 11. Vincoli di consistenza

I 5 vincoli di `MODELLO-DATI.md` §6 espressi come query di verifica.
Questi NON sono CHECK constraints (troppo costosi su INSERT) ma
**query da eseguire periodicamente** o on-demand. Vivranno in
`tests/integration/test_consistenza_dati.py`.

```sql
-- §1 Triangolo chiuso PdE-MAT-PdC
-- Per ogni blocco PdC tipo CONDOTTA/VETTURA che riferisce una corsa
-- commerciale, esiste un giro_blocco con stessa corsa_commerciale_id
SELECT COUNT(*) AS violazioni
FROM turno_pdc_blocco pb
LEFT JOIN giro_blocco gb ON gb.corsa_commerciale_id = pb.corsa_commerciale_id
WHERE pb.tipo_evento IN ('CONDOTTA', 'VETTURA')
  AND pb.corsa_commerciale_id IS NOT NULL
  AND gb.id IS NULL;
-- atteso: 0

-- §2 Coerenza temporale (tolleranza 1 minuto)
SELECT pb.id, pb.ora_inizio, cc.ora_partenza, pb.ora_fine, cc.ora_arrivo
FROM turno_pdc_blocco pb
JOIN corsa_commerciale cc ON cc.id = pb.corsa_commerciale_id
WHERE pb.corsa_commerciale_id IS NOT NULL
  AND pb.tipo_evento IN ('CONDOTTA', 'VETTURA')
  AND (
       ABS(EXTRACT(EPOCH FROM (pb.ora_inizio - cc.ora_partenza))) > 60
    OR ABS(EXTRACT(EPOCH FROM (pb.ora_fine - cc.ora_arrivo))) > 60
  );
-- atteso: nessuna riga

-- §3 Una persona-una giornata: già garantito da UNIQUE(persona_id, data)

-- §4 Indisponibilità rispettate
SELECT ag.id
FROM assegnazione_giornata ag
JOIN indisponibilita_persona ip
  ON ip.persona_id = ag.persona_id
 AND ag.data BETWEEN ip.data_inizio AND ip.data_fine
 AND ip.is_approvato = TRUE
WHERE ag.stato != 'annullato';
-- atteso: nessuna riga

-- §5 Stessa azienda
SELECT gm.id, gm.azienda_id, cc.azienda_id
FROM giro_materiale gm
JOIN giro_giornata gg ON gg.giro_materiale_id = gm.id
JOIN giro_variante gv ON gv.giro_giornata_id = gg.id
JOIN giro_blocco gb ON gb.giro_variante_id = gv.id
LEFT JOIN corsa_commerciale cc ON cc.id = gb.corsa_commerciale_id
WHERE cc.id IS NOT NULL
  AND gm.azienda_id != cc.azienda_id;
-- atteso: nessuna riga
```

---

## 12. Seed iniziale Trenord

Inserts da eseguire una sola volta dopo `alembic upgrade head` (o
inclusi in migrazione `0002_seed_trenord.py`).

```sql
-- §12.1 azienda
INSERT INTO azienda (codice, nome, normativa_pdc_json) VALUES
  ('trenord', 'Trenord SRL', '{
    "max_prestazione_min_standard": 510,
    "max_prestazione_min_notte": 420,
    "cap_7h_window_start_min": 60,
    "cap_7h_window_end_min": 299,
    "max_condotta_min": 330,
    "refez_required_above_min": 360,
    "refez_min_duration": 30,
    "meal_window_1": [690, 930],
    "meal_window_2": [1110, 1350],
    "accp_standard_min": 40,
    "acca_standard_min": 40,
    "accp_preriscaldo_min": 80,
    "fr_max_per_settimana": 1,
    "fr_max_per_28_giorni": 3,
    "riposo_settimanale_min_h": 62
  }');

-- §12.2 localita_manutenzione (dal seed JSON)
INSERT INTO localita_manutenzione (codice, nome_canonico, azienda_id, is_pool_esterno, azienda_proprietaria_esterna)
SELECT v.codice, v.nome_canonico, a.id, v.is_pool_esterno, v.azienda_proprietaria_esterna
FROM (VALUES
  ('IMPMAN_MILANO_FIORENZA', 'TRENORD IMPMAN MILANO FIORENZA', FALSE, NULL),
  ('IMPMAN_NOVATE',          'TRENORD IMPMAN NOVATE',           FALSE, NULL),
  ('IMPMAN_CAMNAGO',         'TRENORD IMPMAN CAMNAGO',          FALSE, NULL),
  ('IMPMAN_LECCO',           'TRENORD IMPMAN LECCO',            FALSE, NULL),
  ('IMPMAN_CREMONA',         'TRENORD IMPMAN CREMONA',          FALSE, NULL),
  ('IMPMAN_ISEO',            'TRENORD IMPMAN ISEO',             FALSE, NULL),
  ('POOL_TILO_SVIZZERA',     '(Pool TILO - servizi Svizzera-Italia)', TRUE,  'TILO')
) AS v(codice, nome_canonico, is_pool_esterno, azienda_proprietaria_esterna)
CROSS JOIN azienda a WHERE a.codice = 'trenord';

-- §12.3 depot Trenord (25 voci da NORMATIVA-PDC §2.1)
INSERT INTO depot (codice, display_name, azienda_id, tipi_personale_ammessi)
SELECT v.codice, v.display_name, a.id, 'PdC'
FROM (VALUES
  ('ALESSANDRIA',     'Alessandria'),
  ('ARONA',           'Arona'),
  ('BERGAMO',         'Bergamo'),
  ('BRESCIA',         'Brescia'),
  ('COLICO',          'Colico'),
  ('COMO',            'Como'),
  ('CREMONA',         'Cremona'),
  ('DOMODOSSOLA',     'Domodossola'),
  ('FIORENZA',        'Fiorenza'),
  ('GALLARATE',       'Gallarate'),
  ('GARIBALDI_ALE',   'Milano P. Garibaldi (ALE)'),
  ('GARIBALDI_CADETTI','Milano P. Garibaldi (Cadetti)'),
  ('GARIBALDI_TE',    'Milano P. Garibaldi (TE)'),
  ('GRECO_TE',        'Milano Greco Pirelli (TE)'),
  ('GRECO_S9',        'Milano Greco Pirelli (S9)'),
  ('LECCO',           'Lecco'),
  ('LUINO',           'Luino'),
  ('MANTOVA',         'Mantova'),
  ('MORTARA',         'Mortara'),
  ('PAVIA',           'Pavia'),
  ('PIACENZA',        'Piacenza'),
  ('SONDRIO',         'Sondrio'),
  ('TREVIGLIO',       'Treviglio'),
  ('VERONA',          'Verona'),
  ('VOGHERA',         'Voghera')
) AS v(codice, display_name)
CROSS JOIN azienda a WHERE a.codice = 'trenord';

-- §12.4 admin user (password generata one-time, da forzare cambio al primo login)
-- I dati vivono in env, qui solo placeholder:
-- INSERT INTO app_user (username, password_hash, is_admin, azienda_id) VALUES
--   ('admin', '<bcrypt_hash>', TRUE, (SELECT id FROM azienda WHERE codice='trenord'));
-- INSERT INTO app_user_ruolo (app_user_id, ruolo) VALUES
--   ((SELECT id FROM app_user WHERE username='admin'), 'ADMIN');

-- §12.5 dotazione (50+ righe dal seed JSON, popolate da uno script
-- one-shot in fase B della FASE D, vedi PIANO-MVP.md)
```

---

## 13. Riepilogo numerico

| Strato | Tabelle | Record stimati Trenord |
|--------|---------|------------------------|
| 0 anagrafica | 8 (azienda, stazione, materiale_tipo, localita_manutenzione, dotazione, depot, depot_linea_abilitata, depot_materiale_abilitato) | ~700 (1+600+50+7+80+25+...) |
| 1 corse | 4 (corsa_commerciale, corsa_composizione, corsa_materiale_vuoto, corsa_import_run) | ~106k (10580 + 95k + ~5k + N) |
| 2 giri | 6 (giro_materiale, versione_base_giro, giro_finestra_validita, giro_giornata, giro_variante, giro_blocco) | ~50k (54+54+~70+~270+~1000+~50000) |
| 2bis revisioni | 3 | ~0 inizialmente, decine all'anno |
| 3 turno PdC | 3 (turno_pdc, turno_pdc_giornata, turno_pdc_blocco) | ~80k (200+~1400+~80000) |
| 4 personale | 3 (persona, assegnazione_giornata, indisponibilita_persona) | persona ~1000 + assegnazioni 365k/anno |
| 5 auth/audit | 4 (app_user, app_user_ruolo, notifica, audit_log) | crescita lineare |

**Totale tabelle**: ~31. Postgres 16 le gestisce senza problemi.

---

## 14. Riferimenti

- `docs/MODELLO-DATI.md` v0.5 — modello concettuale
- `docs/STACK-TECNICO.md` — Postgres 16, Alembic
- `docs/LOGICA-COSTRUZIONE.md` — algoritmi che girano sopra
- `docs/IMPORT-PDE.md` (FASE C doc 6) — popolamento corsa_commerciale
- `docs/PIANO-MVP.md` (FASE C doc 7) — quale tabella per prima

---

**Fine draft v0.1**. Da revisionare con l'utente prima di scrivere
la migrazione Alembic `0001_initial_schema.py`.
