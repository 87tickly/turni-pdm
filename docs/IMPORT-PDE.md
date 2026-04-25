# IMPORT PdE — lettura proposta commerciale Numbers/Excel (draft v0.1)

> Specifica del primo importer del programma. L'**unica fonte
> autorevole** del sistema: il PdE (Programma di Esercizio) di Trenord
> in formato Apple Numbers (`.numbers`) o Excel (`.xlsx`). Output:
> popolamento delle tabelle `corsa_commerciale`, `corsa_composizione`,
> `corsa_import_run` (vedi `SCHEMA-DATI-NATIVO.md`).
>
> **Modulo target**: `backend/src/colazione/importers/pde.py`.
>
> **Esempio reale**: il file fornito dall'utente
> `All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.numbers` —
> 10580 corse × 124 colonne, validità 14/12/2025 → 12/12/2026.

---

## 1. Input

### Formati supportati

| Formato | Libreria | Note |
|---------|----------|------|
| **`.numbers`** (priorità) | `numbers-parser` (Python) | Formato nativo Apple. Già testato in fase di analisi del repo. |
| **`.xlsx`** (alternativo) | `openpyxl` | Per export da altri sistemi. Stessa struttura colonne. |
| **`.csv`** (futuro) | `pandas` | Solo se serve. Niente in v1. |

### Struttura file Trenord

Il file PdE Trenord ha **3 sheet**:
1. `PdE RL` — 10580 righe × 124 colonne (le corse)
2. `NOTE Treno` — 122 righe × 5 colonne (note testuali per treni
   specifici)
3. `NOTE BUS` — 47 righe × 5 colonne (idem per bus)

**Solo lo sheet 1 va importato in `corsa_commerciale`**. Gli altri due
sono note testuali, possibili da gestire in v1.x come tabelle figlie
opzionali.

---

## 2. Mapping colonne PdE → schema DB

Le 124 colonne dello sheet `PdE RL`. Ogni riga = una corsa giornaliera-
tipo.

### 2.1 Identificativi → `corsa_commerciale`

| PdE col | Nome colonna PdE | Campo DB | Tipo | Note |
|---------|------------------|----------|------|------|
| 0 | Variazione | (skip) | — | — |
| 1 | VCO | (skip) | — | — |
| 2 | Descrizione VCO | (skip) | — | — |
| 3 | AUTORIZZAZIONE REGIONALE PEC | (skip) | — | — |
| 4 | Valido da | `valido_da` | DATE | — |
| 5 | Valido a | `valido_a` | DATE | — |
| 6 | Modalità di effettuazione | (skip) | — | "T" sempre per i treni |
| 7 | Treno 1 | `numero_treno` | VARCHAR | Cast a string (PdE lo dà come float) |
| 8 | Rete 1 | `rete` | VARCHAR | "FN" / "RFI" |
| 9 | Treno 2 | (note alt.) | — | Casi rari, salvare in `note_extra_json` |
| 10 | Rete 2 | (note alt.) | — | — |
| 11 | Treno RFI | `numero_treno_rfi` | VARCHAR | quando differisce dal 1 |
| 12 | Treno FN | `numero_treno_fn` | VARCHAR | idem |
| 13 | Cambio Num Treno stessa rete | (note) | — | — |
| 14 | Categoria linea | `categoria` | VARCHAR | "R" / "RE" / "S" |
| 15 | Descrizione Categoria | (skip) | — | "Regionale" / "Regio Express" |
| 16 | Ex Treno 1 | (note) | — | — |
| 17 | Ex Treno 2 | (note) | — | — |
| 18 | Codice linea | `codice_linea` | VARCHAR | "R22", "RE1" |
| 19 | Descrizione linea | (skip) | — | testo umano |
| 20 | Codice direttrice | (skip) | — | numero |
| 21 | Direttrice | `direttrice` | TEXT | "LAVENO-VARESE-..." |

### 2.2 Geografia → `corsa_commerciale`

| PdE col | Nome | Campo DB | Note |
|---------|------|----------|------|
| 22 | Cod Origine | `codice_origine` | "S01066". Inserire stazione se non esiste in `stazione` |
| 23 | Stazione Origine Treno | (usato per upsert `stazione`) | "MILANO CADORNA" |
| 24 | Cod Destinazione | `codice_destinazione` | idem |
| 25 | Stazione Destinazione Treno | (upsert) | — |
| 26 | Ora Or | `ora_partenza` | "06:39:00" → TIME |
| 27 | Ora Des | `ora_arrivo` | TIME |
| 28 | Cod inizio CdS | `codice_inizio_cds` | nullable |
| 29 | Stazione Inizio CdS | (upsert) | — |
| 30 | Cod Fine CdS | `codice_fine_cds` | nullable |
| 31 | Stazione Fine CdS | (upsert) | — |
| 32 | Ora In Cds | `ora_inizio_cds` | nullable |
| 33 | Ora Fin cds | `ora_fine_cds` | — |
| 34 | Min Tratta | `min_tratta` | INTEGER |
| 35 | Min CdS | `min_cds` | — |
| 36 | Km tratta | `km_tratta` | NUMERIC |
| 37 | Km CdS | `km_cds` | — |

### 2.3 Periodicità → `corsa_commerciale`

| PdE col | Nome | Campo DB | Note |
|---------|------|----------|------|
| 38 | Codice Periodicità | `codice_periodicita` | testo tecnico "CP. ECF. S 01/12/25-..." |
| 39 | Periodicità | (parsed → derivare giorni) | testo lungo |
| 40 | Periodicità Breve | `periodicita_breve` | umano |
| 41 | Treno garantito feriale | `is_treno_garantito_feriale` | "SI"/"NO" → BOOLEAN |
| 42 | Fascia oraria | `fascia_oraria` | "FR"/"FNR" |
| 43 | Materiale interoperabile | (note) | "SI"/"NO" |
| 123 | Treno garantito festivo | `is_treno_garantito_festivo` | "SI"/"NO" → BOOLEAN |

### 2.4 Composizione 9 combinazioni → `corsa_composizione`

Per ogni corsa, 9 righe in `corsa_composizione`:
`{invernale, estiva, agosto} × {feriale, sabato, festivo}`.

| PdE col | Stagione × Giorno | Campo `corsa_composizione` |
|---------|-------------------|----------------------------|
| 44, 45, 46 | Invernale Fer/Sab/Fest | `categoria_posti` per le 3 righe invernali |
| 47, 48, 49 | Estiva Fer/Sab/Fest | `categoria_posti` per le 3 righe estive |
| 50, 51, 52 | Agosto Fer/Sab/Fest | `categoria_posti` per le 3 righe agosto |
| 53-61 | Doppia Composizione | `is_doppia_composizione` (9 valori) |
| 62-70 | Vincolo Dichiarato | `vincolo_dichiarato` (9 valori) |
| 71-79 | Tipologia Treno | `tipologia_treno` (9 valori) |
| 80-88 | Categoria Bici | `categoria_bici` (9 valori) |
| 89-97 | Categoria PRM | `categoria_prm` (9 valori) |

### 2.5 Calendario annuale → `corsa_commerciale.giorni_per_mese_json`

| PdE col | Mese | Chiave JSON |
|---------|------|-------------|
| 98 | Gg_dic1AP | `dic1AP` |
| 99 | Gg_dic2AP | `dic2AP` |
| 100 | Gg_gen | `gen` |
| 101 | Gg_feb | `feb` |
| 102 | Gg_mar | `mar` |
| 103 | Gg_apr | `apr` |
| 104 | Gg_mag | `mag` |
| 105 | Gg_giu | `giu` |
| 106 | Gg_lug | `lug` |
| 107 | Gg_ago | `ago` |
| 108 | Gg_set | `set` |
| 109 | Gg_ott | `ott` |
| 110 | Gg_nov | `nov` |
| 111 | Gg_dic1 | `dic1` |
| 112 | Gg_dic2 | `dic2` |
| 113 | Gg_anno | `anno` (totale annuale) |

Esempio JSON salvato:
```json
{
  "dic1AP": 0, "dic2AP": 18, "gen": 31, "feb": 28, "mar": 31, "apr": 30,
  "mag": 31, "giu": 30, "lug": 31, "ago": 31, "set": 30, "ott": 31,
  "nov": 30, "dic1": 12, "dic2": 19, "anno": 365
}
```

### 2.6 Aggregati → `corsa_commerciale`

| PdE col | Nome | Campo DB |
|---------|------|----------|
| 114 | Totale Km | `totale_km` |
| 115 | Totale Minuti | `totale_minuti` |
| 116 | Totale km CdS | (skip o note) |
| 117 | Totale Minuti CdS | (skip) |
| 118 | Postikm | `posti_km` |
| 119 | Velocità commerciale | `velocita_commerciale` |
| 120 | KM RFI | (note) |
| 121 | KM FN | (note) |
| 122 | Treni parzialmente a contratto | (note flag) |

---

## 3. Calcolo `valido_in_date_json` (denormalizzato)

Decisione `MODELLO-DATI.md` v0.5 #1: per ogni corsa salviamo l'elenco
**completo delle date** in cui circola, come array JSON di stringhe
ISO. Permette query rapide "il treno X circola il 22/04/2026?".

### 3.1 Algoritmo

Input:
- `valido_da` / `valido_a` (intervallo annuale)
- `giorni_per_mese_json` (totali per mese)
- `Periodicità` testuale (col 39): "Circola tutti i giorni. Non
  circola dal 01/12/2025 al 13/12/2025, 25/12/2025, 25/12/2026."

Algoritmo:

```python
def calcola_valido_in_date(valido_da, valido_a, periodicita_text, mesi_giorni):
    # Step 1: range completo da valido_da a valido_a
    candidati = list_giorni_tra(valido_da, valido_a)

    # Step 2: parsing del testo "Periodicità"
    intervalli_skip, date_skip_singole, date_extra = parse_periodicita(periodicita_text)
    candidati = [d for d in candidati
                 if d not in date_skip_singole
                 and not in_intervalli(d, intervalli_skip)]
    candidati += date_extra
    candidati = sorted(set(candidati))

    # Step 3: validazione vs giorni_per_mese_json
    # (la somma dei giorni candidati in ciascun mese deve combaciare
    # con `mesi_giorni[mese]` ± tolleranza)
    if not validate_count(candidati, mesi_giorni):
        log_warning(f"Mismatch periodicità calcolata vs dichiarata")

    return [d.isoformat() for d in candidati]
```

### 3.2 Parser `Periodicità`

Pattern testuali da gestire (dall'analisi del file reale):

| Testo | Significato |
|-------|-------------|
| "Circola tutti i giorni." | range pieno, no skip |
| "Non circola dal X al Y" | aggiungi intervallo a `intervalli_skip` |
| "Non circola il X" o "Non circola X-Y-Z" | aggiungi date a `date_skip_singole` |
| "Circola dal X al Y" | (sostituisce range pieno) intervallo unico applicabile |
| "Circola anche il X" | aggiungi a `date_extra` |
| "25/12/2025" (data isolata) | date_skip_singole se in contesto skip, date_extra in contesto extra |

Strategia: regex multiple chained, con priorità "skip" su "include"
in caso di ambiguità.

### 3.3 Verifica incrociata

Dopo aver calcolato la lista, verificare che la cardinalità per mese
combaci con `giorni_per_mese_json`:

```python
def validate_count(date_list, mesi_giorni):
    by_month = defaultdict(int)
    for d in date_list:
        by_month[mese_chiave(d)] += 1
    # Confronta con mesi_giorni dichiarati
    for mese_key, atteso in mesi_giorni.items():
        if mese_key == 'anno':
            continue
        calcolato = by_month.get(mese_key, 0)
        if abs(calcolato - atteso) > 0:
            return False
    return True
```

Se la verifica fallisce, l'import logga un warning ma **non blocca**:
i `Gg_*` PdE sono autoritativi, ma `valido_in_date_json` è derivato
e va corretto nei casi anomali (rari, ma esistono).

---

## 4. Idempotenza dell'import

Re-import dello stesso file PdE deve essere **safe**: nessun
duplicato, nessuna perdita di dati esistenti.

### 4.1 Identificazione corsa esistente

Chiave logica: `(azienda_id, numero_treno, valido_da)`.

```python
def upsert_corsa(corsa_data):
    key = (corsa_data.azienda_id, corsa_data.numero_treno, corsa_data.valido_da)
    existing = query_corsa(*key)
    if existing:
        if has_diff(existing, corsa_data):
            update(existing, corsa_data)
            log_update(corsa_data.numero_treno)
        # else: skip, già coerente
    else:
        insert(corsa_data)
        log_insert(corsa_data.numero_treno)
```

### 4.2 Hash file

Per evitare di rifare l'import inutilmente:

```python
file_hash = sha256(file_bytes)
if exists_run(source_hash=file_hash, completed_at IS NOT NULL):
    print("File già importato il", run.started_at)
    confirm = input("Procedere comunque? [s/N] ")
    if confirm != 's':
        return
```

### 4.3 Tracking in `corsa_import_run`

Ogni esecuzione apre una riga in `corsa_import_run` con:
- `source_file`: path/nome
- `source_hash`: SHA-256
- `started_at`, `completed_at`
- `n_corse_create`, `n_corse_update`
- `note`: errori/warning sintetizzati

L'import linka ogni `corsa_commerciale` creata o aggiornata al run
corrente via `import_run_id`.

---

## 5. Pseudo-codice top-level

```python
async def importa_pde(
    file_path: Path,
    azienda_codice: str = 'trenord',
    confirm_overwrite: bool = False,
) -> ImportResult:
    # Step 1: open
    if file_path.suffix == '.numbers':
        rows = leggi_numbers(file_path)
    elif file_path.suffix == '.xlsx':
        rows = leggi_xlsx(file_path)
    else:
        raise ImportError(f"Formato non supportato: {file_path.suffix}")

    # Step 2: dedup check
    file_hash = compute_sha256(file_path)
    existing_run = await find_existing_run(file_hash)
    if existing_run and not confirm_overwrite:
        return ImportResult(skipped=True, reason="già importato")

    # Step 3: open run
    azienda_id = await get_azienda_id(azienda_codice)
    run = await create_import_run(file_path, file_hash, azienda_id)

    # Step 4: process rows
    n_create = 0
    n_update = 0
    warnings = []

    for row_idx, row in enumerate(rows[1:], start=1):  # skip header
        try:
            corsa = parse_row(row)
            corsa.azienda_id = azienda_id
            corsa.import_run_id = run.id
            corsa.valido_in_date_json = calcola_valido_in_date(
                corsa.valido_da, corsa.valido_a,
                row['Periodicità'], corsa.giorni_per_mese_json
            )

            # Upsert stazioni se mancanti
            await upsert_stazione(corsa.codice_origine, row['Stazione Origine Treno'])
            await upsert_stazione(corsa.codice_destinazione, row['Stazione Destinazione Treno'])
            # ... cds origin/dest se presenti

            existing = await find_corsa(azienda_id, corsa.numero_treno, corsa.valido_da)
            if existing:
                if has_changes(existing, corsa):
                    await update_corsa(existing.id, corsa)
                    n_update += 1
            else:
                corsa_id = await insert_corsa(corsa)
                # 9 righe in corsa_composizione
                await insert_composizione(corsa_id, parse_composizione(row))
                n_create += 1
        except Exception as e:
            warnings.append(f"Riga {row_idx}: {e}")

    # Step 5: close run
    await close_import_run(run.id, n_create, n_update, warnings)

    return ImportResult(
        ok=True,
        n_create=n_create,
        n_update=n_update,
        warnings=warnings,
        run_id=run.id,
    )
```

---

## 6. Edge case noti

### 6.1 Righe con valori incompleti

Es. corse fuori contratto regionale con CdS NULL. Salvare con
nullable, niente eccezione.

### 6.2 Numero treno come float

PdE Numbers restituisce `Treno 1` come `13.0`. Conversione:
`str(int(value))` se `value == int(value)`.

### 6.3 Orario in formato stringa

PdE può dare `"06:39:00"` come stringa o come `datetime.time`.
Normalizzazione: `parse_time(value)` che accetta entrambi.

### 6.4 Date all'italiana

`Periodicità` testuale usa `01/12/2025`. Parser robusto a:
- `dd/mm/yyyy`
- `dd/mm/yy` (assumere 2000+)
- `dd/mm` (senza anno → contesto valido_da/valido_a)

### 6.5 Treni "Treno 2" non null

Casi rari (es. cumulazione treni). Per ora: ignorati, salvati in
`note_extra_json` se serve in futuro.

### 6.6 Caratteri speciali nel testo periodicità

Testo PdE può avere: tabulazioni, doppi spazi, caratteri Unicode
(es. trattini lunghi `–` invece di `-`). Normalizzare prima del parser
regex.

### 6.7 Sheet ordering

Numbers/Excel possono avere sheet in ordine diverso. Cercare per
**nome** ("PdE RL") non per indice 0.

### 6.8 Header riga 0

Le 124 colonne hanno header testuale alla riga 0. Validare che le
prime 5 colonne contengano i nomi attesi prima di iterare.

---

## 7. Performance

10580 corse × 9 composizioni = **~95.000 INSERT** in totale al primo
import.

### Strategia

1. **Bulk insert**: usare `INSERT ... VALUES (...), (...), ...` con
   batch di 1000 righe (SQLAlchemy `bulk_insert_mappings` o
   `Connection.execute(insert(), [...])`).
2. **Transazione unica**: tutto l'import in una sola transazione.
   Se fallisce → rollback completo, nessun stato parziale.
3. **Indici GIN dopo**: se l'import lento sui calcoli `valido_in_date`,
   considerare di costruire l'indice GIN su quel JSONB **dopo** la
   bulk insert (CREATE INDEX CONCURRENTLY).

Tempo target: **< 30 secondi** su laptop decente per il file Trenord
intero.

---

## 8. Test

In `tests/importers/test_pde.py`:

1. **Smoke test**: import file Trenord reale ridotto (50 righe), verifica n.
   record creati.
2. **Idempotenza**: re-import stesso file → 0 nuovi insert, 0 update.
3. **Modifica riga**: cambia un valore nel file, re-import → 1 update.
4. **Calcolo valido_in_date**: per una corsa nota (es. treno 13), verificare
   numero date matcha `Gg_anno`.
5. **Casi limite**: corse con `Treno 2`, corse senza CdS, corse con
   "Non circola dal X al Y, dal Z al W" (intervalli multipli).

Fixture: `tests/fixtures/pde_sample_50.xlsx` (estratto del file reale,
50 corse rappresentative).

---

## 9. CLI

Esposizione del comando via FastAPI CLI o script standalone:

```bash
# Da backend/
uv run python -m colazione.importers.pde \
    --file /path/to/All.1A5_14dic2025-12dic2026_TRENI_e_BUS.numbers \
    --azienda trenord
```

Output sul terminale:
```
[1/3] Apertura file...
      10580 righe trovate in sheet 'PdE RL'
[2/3] Verifica idempotenza... file mai importato
[3/3] Importazione...
      ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰ 100% (10580/10580)
   ✓ 10580 corse importate
   ✓ 95220 record di composizione
   ✓ 0 update, 10580 create
   ⚠ 3 warning di periodicità non validate (vedi log)

Run ID: 1, durata 24.7s
```

---

## 10. Riferimenti

- `docs/SCHEMA-DATI-NATIVO.md` §4 — schema target `corsa_commerciale`
- `docs/STACK-TECNICO.md` §4 — dipendenze (`numbers-parser`, `openpyxl`)
- `data/depositi_manutenzione_trenord_seed.json` — esempio di output da
  parsing PDF (analogo concettuale all'import PdE)
- `docs/PIANO-MVP.md` (FASE C doc 7) — quando si scrive l'importer
  nell'ordine costruzione

---

**Fine draft v0.1**. Da revisionare con l'utente prima di scrivere
`backend/src/colazione/importers/pde.py`.
