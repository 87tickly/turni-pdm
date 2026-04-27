# SPRINT 5 — Ripensamento builder giro materiale (plan completo)

> Documento operativo per la sessione di lavoro che riscrive il
> builder con il **modello mentale corretto** del pianificatore Trenord.
> Sprint 4.4 (chiuso il 2026-04-26) ha prodotto un MVP funzionante
> end-to-end ma con **assunzioni di design sbagliate**, smentite dallo
> smoke test su dati reali con l'utente come dominio expert.
>
> Questo documento è autosufficiente: leggilo dopo `CLAUDE.md` e
> `TN-UPDATE.md` per capire cosa fare.

---

## 1. Cosa è successo (in due paragrafi)

Sprint 4.4 ha implementato pipeline pure (catena → posiziona →
multi-giornata → composizione) + persister + endpoint API. 313 test
verdi, mypy strict, codice solido tecnicamente. Ma lo smoke test con
fixture e poi col PdE reale ha fatto emergere che il **modello
operativo che avevo assunto è sbagliato in radice**:

- Ho assunto "ogni convoglio esce dalla sede al mattino e rientra la
  sera" → falso. Un convoglio sta in linea **5000-10000 km** = giorni
  multipli. Dorme nelle stazioni dove finisce il servizio.
- Ho assunto "vuoti tecnici di posizionamento ovunque" (es. Fiorenza
  → Asso) → falso. **I vuoti si fanno solo tra stazioni vicine alla
  sede manutentiva** (area metropolitana milanese per FIO/NOV). Verso
  periferia si va con corse commerciali della sera prima.
- Ho assunto "una regola = un materiale + un numero di pezzi" → falso
  in casi importanti (Tirano, Verona) dove la **doppia composizione
  mista è la norma** (es. ETR526 + ETR425).
- Ho usato regole "matcha tutto" (filtri vuoti) per dimostrazione →
  in produzione è **errato dimostrativo**: ogni materiale ha vincoli
  specifici di linea.

Validato 2026-04-27 dall'utente (ex-pianificatore Trenord). Memoria
aggiornata in `feedback_no_inventare_dati.md` e
`project_pianificazione_ferroviaria_modello.md`.

---

## 2. Modello operativo corretto (vincoli rigidi)

I 6 principi che il nuovo builder deve rispettare:

1. **Posizionamento commerciale, mai tecnico verso periferia.**
   Convoglio per andare da Milano a Tirano/Asso/Laveno fa una
   **corsa commerciale serale** + dorme in stazione. Mai vuoti
   tecnici verso quelle stazioni.

2. **Vuoti solo intra-whitelist sede.** Per ogni sede manutentiva
   c'è una whitelist di stazioni "vicine" tra cui sono permessi i
   vuoti. Se la coppia (origine, destinazione) non è entrambe in
   whitelist, il vuoto è **vietato**.

3. **Multi-giornata = norma.** Un giro tipico copre N giornate
   (5-10), il convoglio dorme in stazioni diverse ogni sera. Single
   day deve essere l'eccezione (es. servizio fortunato che inizia e
   finisce in sede).

4. **Rientro a fine ciclo: corsa commerciale + vuoto breve.** Quando
   il giro raggiunge cap km o n_giornate, il treno fa una corsa
   commerciale verso una stazione whitelist (Mi.Centrale per FIO,
   Mi.Cadorna per NOV, ecc), poi eventuale vuoto breve nella
   whitelist fino alla sede.

5. **Composizioni miste con vincoli.** Alcune linee/servizi
   richiedono doppia composizione obbligatoria. Non tutte le coppie
   sono ammesse. Es. ammesse: 421+421, 526+526, 526+425. Più una
   modalità "manuale" dove il pianificatore può forzare composizioni
   custom anche fuori dai vincoli standard.

6. **Materiali ↔ linee specifici.** Le regole devono filtrare
   esplicitamente per `codice_linea`. Niente regole "matcha tutto".

---

## 3. Decisioni di design (validate con utente)

| Tema | Decisione |
|---|---|
| **Whitelist stazioni-sede** | Tabella M:N `localita_stazione_vicina` (sede_id, stazione_codice). Configurabile per ogni sede. |
| **FIO whitelist** | Mi.Garibaldi, Mi.Centrale, Mi.Lambrate, Mi.Rogoredo, Mi.Greco-Pirelli (5 stazioni) |
| **NOV whitelist** | Mi.Cadorna, Mi.Bovisa, **Saronno** (3 stazioni, Saronno condivisa con CAM) |
| **CAM whitelist** | Seveso, Saronno (2 stazioni, Saronno condivisa con NOV) |
| **LEC whitelist** | Lecco (1 stazione) |
| **CRE whitelist** | Cremona (1 stazione) |
| **ISE whitelist** | Iseo (1 stazione) |
| **TILO** | Pool esterno: i giri TILO restano "blackbox" (girano sulle tracce del PdE TILO). Vincolo rigido **unico**: ogni giro TILO deve rientrare in Svizzera ogni sera. Niente whitelist Italia. |
| **Stazioni condivise** | Es. Saronno appartiene a NOV E a CAM. La M:N `localita_stazione_vicina` lo supporta naturalmente: la scelta di quale sede usa Saronno per un dato giro dipende dal giro stesso (il builder può scegliere). |
| **Composizione regola** | Estensione `programma_regola_assegnazione.composizione_json: list[{materiale_tipo_codice, n_pezzi}]`. Regola single-material esistente migrata a `[{tipo, n}]`. |
| **Vincoli accoppiamento** | Tabella `materiale_accoppiamento_ammesso` (mat_a, mat_b, simmetrica). Inizio con 421+421, 526+526, 526+425. La lista cresce nel tempo; per ora questi 3 bastano. |
| **Override manuale composizione** | Flag `is_composizione_manuale: bool` sulla regola. Se True, bypass del check su `materiale_accoppiamento_ammesso` (il pianificatore sceglie qualunque combinazione). |
| **Menu materiali UI** | Scope frontend (futuro): UI elenca tutti i `materiale_tipo` disponibili dell'azienda → il pianificatore seleziona N materiali per costruire la composizione_json di una regola. Backend Sprint 5: assicura che esista un endpoint `GET /api/materiali` (creiamolo se mancante) per popolare il menu. |
| **Sede manutentiva di default per materiale** | Nuovo campo nullable `materiale_tipo.localita_manutenzione_default_id`, **assegnabile fin da subito** (approccio (b) scelto dall'utente). Inizialmente NULL per tutti i materiali; il pianificatore lo configura via UI/seed/API. Niente estrazione automatica dal PDF turno materiale (scope futuro). |
| **Cap km ciclo** | Nuovo campo `programma_materiale.km_max_ciclo INTEGER` (default 5000, configurabile per programma fino 10000+). Cumulato su tutto il ciclo, NON giornaliero. |
| **`km_max_giornaliero` legacy** | Deprecato ma non rimosso (FK retro-compat). |
| **Strict mode rinominato** | `no_giro_non_chiuso_a_localita` → `no_giro_appeso`. Nuova semantica: "ogni giro deve avere un rientro programmato a fine ciclo, non ogni sera". |
| **Vuoto testa primissimo giorno** | **Eliminato anche quello** — coerente col principio 1: il treno esce dalla sede facendo la prima corsa commerciale, non un vuoto. |
| **Posizionamento serale "preposizione"** | Logica del builder: se il giorno N+1 il treno deve iniziare in periferia, sceglie una corsa commerciale del giorno N che arriva in quella periferia. È quello che è stato chiamato "la nostra bravura" dall'utente. |

---

## 4. Schema DB esteso (migration 0007)

```sql
-- Whitelist M:N stazioni-vicine-sede
CREATE TABLE localita_stazione_vicina (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    localita_manutenzione_id BIGINT NOT NULL
        REFERENCES localita_manutenzione(id) ON DELETE CASCADE,
    stazione_codice VARCHAR(20) NOT NULL
        REFERENCES stazione(codice) ON DELETE RESTRICT,
    UNIQUE (localita_manutenzione_id, stazione_codice)
);

-- Vincoli accoppiamento materiali (simmetrica via constraint o doppio insert)
CREATE TABLE materiale_accoppiamento_ammesso (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    materiale_a_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice),
    materiale_b_codice VARCHAR(50) NOT NULL
        REFERENCES materiale_tipo(codice),
    UNIQUE (materiale_a_codice, materiale_b_codice),
    CHECK (materiale_a_codice <= materiale_b_codice)  -- normalizzazione
);

-- Estensione programma_regola_assegnazione
ALTER TABLE programma_regola_assegnazione
    ADD COLUMN composizione_json JSONB,
    ADD COLUMN is_composizione_manuale BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill regole esistenti: composizione_json = [{tipo, n_pezzi}]
UPDATE programma_regola_assegnazione
SET composizione_json = jsonb_build_array(
    jsonb_build_object(
        'materiale_tipo_codice', materiale_tipo_codice,
        'n_pezzi', numero_pezzi
    )
)
WHERE composizione_json IS NULL;

-- Promuovi NOT NULL
ALTER TABLE programma_regola_assegnazione
    ALTER COLUMN composizione_json SET NOT NULL;

-- I campi materiale_tipo_codice + numero_pezzi diventano LEGACY
-- ma li teniamo per ora (nullable) — li deprechiamo in 5.x dopo cleanup.

-- Cap km ciclo
ALTER TABLE programma_materiale
    ADD COLUMN km_max_ciclo INTEGER;

-- Rinomina strict flag
UPDATE programma_materiale SET strict_options_json = jsonb_set(
    strict_options_json - 'no_giro_non_chiuso_a_localita',
    '{no_giro_appeso}',
    COALESCE(strict_options_json->'no_giro_non_chiuso_a_localita', 'false'::jsonb)
);
-- Aggiorna anche il default JSONB della colonna (statement separato).
```

---

## 5. Sub-sprint Sprint 5 (decomposizione)

### 5.1 — Migration 0007 + modelli ORM

**Scope**: solo schema DB + modelli SQLAlchemy + Pydantic. Niente
algoritmo nuovo.

- Migration `0007_riprogettazione_materiale.py`: tabelle nuove +
  alter + backfill + promozione NOT NULL.
- Aggiorna `models/anagrafica.py` con `LocalitaStazioneVicina`,
  `MaterialeAccoppiamentoAmmesso`.
- Aggiorna `models/programmi.py` con `composizione_json`,
  `is_composizione_manuale`.
- Aggiorna schemi Pydantic in `schemas/programmi.py`:
  - `ComposizioneItem` (materiale_tipo_codice + n_pezzi)
  - `ProgrammaRegolaAssegnazioneCreate.composizione: list[ComposizioneItem]`
  - Validazione: lista non vuota, n_pezzi ≥ 1
- Test smoke: 6-8 test ORM + Pydantic validation.

**Verifiche**: `alembic upgrade head` OK, mypy verde, pytest verde,
schema_count test count aggiornato.

### 5.2 — Seed whitelist + accoppiamenti

**Scope**: popolare i dati di base.

- Migration `0008_seed_whitelist_e_accoppiamenti.py`:
  - Inserisce le 5+2 stazioni in `localita_stazione_vicina` per
    FIO e NOV (basta `stazione_codice` reale del PdE).
  - **Stazioni necessarie nel DB**: prerequisito è che le stazioni
    siano già state create dall'import PdE. La migration 0008
    INSERT è quindi **applicata DOPO l'import PdE**, NON in alembic
    upgrade automatico. Idea: spostare 0008 in uno script di seed
    `scripts/seed_whitelist_e_accoppiamenti.py` invece che migration.
  - Inserisce gli accoppiamenti confermati: 421+421, 526+526,
    526+425. **Lista completa da utente** prima di committare.

**Verifiche**: query DB conferma whitelist + accoppiamenti popolati.

### 5.3 — Riscrittura `posizionamento.py`

**Scope**: vuoti SOLO intra-whitelist. Resto è "il treno dorme in
linea".

- Nuova firma:
  ```python
  def posiziona_su_localita(
      catena: Catena,
      localita: LocalitaManutenzione,
      whitelist_stazioni: set[str],  # codici stazione vicina
      params: ParamPosizionamento,
  ) -> CatenaPosizionata
  ```
- Logica:
  - Vuoto **testa**: solo se `prima.codice_origine ∈ whitelist`
    AND `prima.codice_origine != stazione_collegata`. (Es. stazione
    Mi.Centrale ∈ whitelist FIO, ma sede è Fiorenza → vuoto breve
    Fiorenza→Centrale.) Se prima corsa parte da fuori whitelist,
    **niente vuoto testa**: il treno è già lì da sera prima.
  - Vuoto **coda**: stessa logica simmetrica. Solo se ultima corsa
    arriva in whitelist + ≠ sede. Altrimenti niente vuoto.
  - Catena con prima/ultima corsa **fuori whitelist** →
    `chiusa_a_localita=False` di default (il giro continua il
    giorno dopo).
- Test puri: 12-15 casi per coprire le 4 combinazioni
  (in/out × in/out) × cross-notte.

### 5.4 — Estensione `multi_giornata.py` con cumulo km + trigger rientro

**Scope**: trigger di chiusura ciclo basato su km cumulativi e
strategia di rientro programmato.

- Aggiunta cumulo `km_cumulati` per giro durante l'estensione
  cross-notte.
- Trigger fine ciclo OR:
  - `km_cumulati ≥ programma.km_max_ciclo`
  - `len(giornate) ≥ params.n_giornate_max` (esistente)
  - Geografia favorevole (catena finisce in whitelist sede,
    chiusura "fortunata")
- Identifica **corsa di rientro commerciale**: dalla stazione di
  fine giornata corrente, cerca una corsa commerciale che arrivi in
  whitelist sede. Se trovata, la lega come "ultima corsa del giro".
- Eventuale vuoto breve finale (whitelist → sede) post corsa di
  rientro.
- Output: `Giro` con `motivo_chiusura ∈ {km_cap, n_giornate,
  fortunata, non_chiuso}`.
- Test puri: 8-10 casi (km cap, n_giornate cap, fortunata, mix).

### 5.5 — Estensione `composizione.py` per lista materiali

**Scope**: `risolvi_corsa` ritorna composizione (lista), non singolo
tipo. Eventi composizione su delta lista.

- `AssegnazioneRisolta`: nuova versione con
  `composizione: list[ComposizioneItem]` invece di
  `materiale_tipo_codice + numero_pezzi`.
- `risolvi_corsa()` legge `regola.composizione_json`.
- `rileva_eventi_composizione()`: confronta liste per delta. Es.
  da `[{526,1},{425,1}]` a `[{526,1}]` = sgancio del 425.
- Persister aggiornato: salva composizione completa in
  `metadata_json` di ogni blocco corsa, e blocchi aggancio/sgancio
  con dettaglio "quale materiale entra/esce".
- Validazione: se `regola.composizione_json` ha più materiali e
  NOT `is_composizione_manuale`, verifica che ogni coppia sia in
  `materiale_accoppiamento_ammesso`.
- Test puri: 10-15 casi (singola, doppia ammessa, doppia non
  ammessa con manuale=True, delta su mix).

### 5.6 — Smoke reale ETR526+ETR425 Mi.Centrale↔Tirano

**Scope**: dimostrazione finale su PdE reale.

- Setup: import PdE Trenord 2025-2026 (file in `data/pde-input/`).
- Crea programma "Trenord 2025-2026 invernale ETR526+425 Tirano":
  - 1 regola: `codice_linea = RE2/RE5/X` (chiedere a utente quale
    codice linea Trenord usa per Mi.Centrale-Tirano nel PdE),
    composizione `[{ETR526, 1}, {ETR425, 1}]`,
    `is_composizione_manuale=False` (l'accoppiamento è ammesso).
  - Programma `km_max_ciclo=10000`, `n_giornate_default=5`.
  - Sede manutentiva: TBD (dove vengono manutenuti ETR526/425?
    Probabilmente FIO o NOV — chiedere).
- Lancia `genera_giri()` su una settimana con
  `localita_codice=...`, `data_inizio=...`, `n_giornate=7`.
- Verifica:
  - Giri multi-giornata 5-7 giornate (NON 1).
  - Treno dorme a Tirano la sera (catena finisce a Tirano, riprende
    da Tirano il giorno dopo con corsa commerciale).
  - Vuoti SOLO intra-whitelist Milano (es. Centrale↔sede), niente
    vuoti verso Tirano.
  - Cap km rispettato.
- Visualizzazione timeline come il smoke precedente, ma adesso 1
  giro per N giorni.
- Stop e revisione coi numeri prima di chiudere lo sprint.

---

## 6. Setup pre-implementazione (PRIMO della nuova sessione)

### 6.1 PdE reale

Già copiato in `backend/data/pde-input/All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.xlsx`.

- 10580 righe (10579 corse + header)
- 124 colonne
- 5.3 MB
- Sheets: `PdE RL` (principale), `NOTE Treno`, `NOTE BUS`
- Gitignored come da pattern `backend/data/pde-input/*` (eccetto README)

Comando import (da nuova sessione, dopo 5.1 + 5.2):

```bash
cd backend
uv run python -m colazione.importers.pde_importer \
  --file "data/pde-input/All.1A5_14dic2025-12dic2026_TRENI e BUS_Rev5_RL.xlsx" \
  --azienda trenord
```

Atteso ~25-30s, 10579 corse + ~95k composizioni nel DB.

### 6.2 Risposte utente (2026-04-27) e domande residue

**Risposte confermate:**

1. ✅ Whitelist stazioni vicine: vedi tabella in §3 (FIO/NOV/CAM/LEC/
   CRE/ISE complete; TILO è blackbox con vincolo "rientra in CH ogni
   sera").

2. ✅ Accoppiamenti: iniziamo con 421+421, 526+526, 526+425. La lista
   cresce nel tempo. UI menu materiali permetterà override manuale.

3. ⏳ Codice linea Mi.Centrale-Tirano: lo **scopriamo nel PdE** quando
   lo importiamo (filtro su `codice_origine` Mi.Centrale +
   `codice_destinazione` Tirano). Non serve chiedere all'utente.

4. ⏳ Sede manutentiva default per ETR526 / ETR425: presumibilmente
   Fiorenza per entrambi. **Verificare con utente all'inizio di
   Sprint 5.6** prima di lanciare lo smoke.

**Domande residue (rispondere quando si arriva al punto):**

- **5.6 setup**: per il smoke ETR526+425 Mi.Centrale-Tirano, sede
  manutentiva Fiorenza? Il "vincolo" Tirano = sempre doppia →
  basta una regola con `composizione_json=[{ETR526,1},{ETR425,1}]`?
  `km_max_ciclo` per questo programma: 5000 o 10000?

### 6.3 Sequenza operativa raccomandata

1. Sub 5.1 (schema + ORM + Pydantic). Test verde, commit.
2. Sub 5.2 (seed whitelist + accoppiamenti — incompleti se mancano
   risposte 6.2.1 e 6.2.2). Almeno FIO + NOV + 421/526/425 OK.
3. Import PdE reale (comando §6.1).
4. Sub 5.3 (posizionamento). Test puri. Commit.
5. Sub 5.4 (multi-giornata cumulo km). Test puri. Commit.
6. Sub 5.5 (composizione lista). Test puri + persister update.
   Commit.
7. Sub 5.6 (smoke ETR526+425 Tirano). Stop, mostro numeri all'utente,
   discutiamo eventuali raffinamenti.

Ogni sub chiude con: pytest verde, ruff, mypy strict, TN-UPDATE
entry, commit + push.

---

## 7. Cosa NON fare (lessons learned)

1. **Mai inventare dati ferroviari** per smoke o demo. Solo PdE reale
   o fixture esistenti committate.
2. **Mai dare per scontato il modello operativo** senza chiedere.
   L'esperienza dell'utente è la fonte di verità sul dominio Trenord.
3. **Mai usare regole "matcha tutto"** (`filtri_json=[]`) in smoke
   "dimostrativi". Producono distribuzioni materiali irrealistiche
   e nascondono bug.
4. **Mai assumere che il convoglio rientri ogni sera.**
   Multi-giornata è la norma operativa.
5. **Mai generare vuoti tecnici verso periferia.** Mi→Tirano è
   sempre commerciale.

---

## 8. Stato del codice attuale (Sprint 4.4 chiuso)

Il codice di Sprint 4.4 resta in repo come "MVP didattico":

- `domain/builder_giro/catena.py` — riusabile (greedy chain ok)
- `domain/builder_giro/multi_giornata.py` — base ok, da estendere
  in 5.4 (cumulo km + trigger rientro)
- `domain/builder_giro/composizione.py` — da estendere in 5.5
  (lista materiali invece di singolo)
- `domain/builder_giro/persister.py` — da aggiornare in 5.5
  (composizione_json invece di tipo+numero)
- `domain/builder_giro/posizionamento.py` — **da riscrivere
  profondamente** in 5.3 (whitelist invece di vuoti automatici)
- `domain/builder_giro/builder.py` — orchestrator, da aggiornare
  per nuova firma posizionamento + cumulo km
- `api/giri.py` — endpoint, refactor minimo per nuove firme

Nessun rollback Git: i 313 test esistenti restano verdi durante 5.x
(adattati man mano). Lo sprint è additivo + refactor incrementale.

---

## 9. Riferimenti

- `CLAUDE.md` — regole operative permanenti del progetto
- `TN-UPDATE.md` — diario operativo (entry Sprint 5 da aggiungere
  prima di iniziare)
- `docs/PROGRAMMA-MATERIALE.md` v0.2 — spec programma materiale
  (resta valida, lo schema viene esteso non sostituito)
- `docs/LOGICA-COSTRUZIONE.md` §3 — Algoritmo A (resta concettualmente
  valido, l'implementazione cambia)
- Memoria persistente:
  - `feedback_no_inventare_dati.md`
  - `project_pianificazione_ferroviaria_modello.md`

---

**Fine plan**. Pronto per essere caricato dalla nuova sessione.
