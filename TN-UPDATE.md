# TN-UPDATE — Diario del nuovo programma (greenfield)

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-26 (11) — Sprint 3 raffinamento: testo Periodicità = verità

### Contesto

Iterazione su Sprint 3 dopo discussione con utente. Il commit
precedente lasciava 8/38 righe della fixture (~21%) con `valido_in_date`
"approssimativo" e parser che falliva il cross-check Gg_*. L'utente
ha chiarito:

1. Il testo **`Periodicità` è la fonte di verità**, non `Codice Periodicità`.
2. Avere un calendario festività italiane interno al codice (sempre
   aggiornato per qualsiasi anno).

### Modifiche

**Nuovo `backend/src/colazione/importers/holidays.py`**:
- `easter_sunday(year)`: algoritmo gaussiano-gregoriano (verificato per
  2024-2030)
- `italian_holidays(year)`: 12 festività civili italiane (10 fisse +
  Pasqua + Pasquetta calcolate dinamicamente)
- `italian_holidays_in_range(start, end)`: subset in un intervallo

Disponibile come utility per il builder giro materiale e altre logiche.
**NON usato** in `compute_valido_in_date` (vedi sotto).

**`importers/pde.py` — aggiornamenti parser**:

1. `PeriodicitaParsed` ha nuovo campo `filtro_giorni_settimana: set[int]`
   (0=lun ... 6=dom).
2. `parse_periodicita` riconosce frasi come "Circola il sabato e la
   domenica" → filtro globale (solo se la frase contiene SOLO nomi
   giorno-settimana, no intervalli/date).
3. `compute_valido_in_date` applica:
   - Default base: `is_tutti_giorni` o `filtro_giorni_settimana`
   - Apply intervals (override del filtro: tutti i giorni dell'intervallo)
   - Apply dates esplicite
   - Skip intervals + dates
4. **NESSUN auto-suppress festività**: il parser segue letteralmente il
   testo. Se `Periodicità` dice "Circola tutti i giorni", il treno
   circola anche a Natale. La regola dell'utente: testo = verità.
5. `Codice Periodicità` rimane non parsato (dato informativo).
6. Cross-check `Gg_*` declassato a **warning informativo**: non blocca
   l'import. Se il testo Periodicità diverge dai conteggi Trenord, il
   parser segue il testo e logga la discrepanza.

### Risultati sulla fixture (38 righe)

- **33/38 (87%)** righe hanno `valido_in_date` = Gg_anno PdE → zero warning
- **5/38 (13%)** righe hanno discrepanza, ma il parser segue il testo:
  - Treni 83/84 (Δ=+39): testo dichiara 5 grandi intervalli, Codice
    Periodicità interno conta meno. Trenord usa Codice per Gg_anno.
  - Treni 393/394 (Δ=+1), 701 (Δ=+2): off-by-piccolo simile.

Per questi 5, il parser dice `valido_in_date_json` = quello che il
testo afferma; le warning loggano la discrepanza per audit.

### Test aggiornati

**`tests/test_holidays.py`** (7 nuovi):
- Pasqua corretta per 2024-2030
- 12 festività italiane in un anno
- Subset in range parziale
- Range cross-anno (cattura festività di entrambi gli anni)

**`tests/test_pde_periodicita.py`** (+5 nuovi):
- "Circola il sabato e la domenica" → `{5, 6}`
- "Circola il sabato" → `{5}`
- Filtro + override intervals (treno 786 reale)
- Frase con intervallo NON setta filtro globale
- `compute_valido_in_date` con filtro + override

**`tests/test_pde_row_parser.py`** (sostituito 2 test):
- `test_high_match_with_pde_gg_anno`: ≥80% righe combaciano (era 75%)
- `test_warnings_are_info_not_errors`: warning devono iniziare con
  `gg_*:` (sono cross-check info, non bug di parsing)

### Verifiche

- `pytest`: **82/82 verdi** (era 69, +13 nuovi: 7 holidays + 5 periodicità + nuove varianti)
- `ruff check` / `ruff format`: tutti verdi
- `mypy strict`: no issues in **35 source files** (era 34, +1 holidays.py)

### Stato

Sprint 3.1-3.5 raffinato secondo regole utente. Parser pronto per
Sprint 3.6 (DB + idempotenza + CLI).

### Prossimo step

Sprint 3.6-3.8 invariato:
- `pde_importer.py` con bulk insert + tracking
- Idempotenza SHA-256
- CLI argparse

---

## 2026-04-26 (10) — FASE D Sprint 3.1-3.5: Parser PdE puro

### Contesto

Sprint 3.1-3.5 del PIANO-MVP: parser puro PdE, no DB. Pipeline lettura
file → dataclass intermedio → calcolo `valido_in_date_json`
denormalizzato. DB + idempotenza + CLI rimandati a Sprint 3.6-3.8.

### Modifiche

**Nuovo `backend/src/colazione/importers/pde.py`** (~480 righe):

- **3 Pydantic models intermedi**:
  - `PeriodicitaParsed`: output del parser testuale (apply/skip
    intervals + dates + flag is_tutti_giorni)
  - `ComposizioneParsed`: 1 di 9 combinazioni stagione × giorno_tipo
  - `CorsaParsedRow`: corsa completa con composizioni nested + warnings

- **Reader** (`read_pde_file`): auto-detect dall'estensione, supporta
  `.numbers` (via `numbers-parser`) e `.xlsx` (via `openpyxl`). Header
  riga 0 → dict[colonna → valore].

- **Helper di normalizzazione**: `_to_str_treno` (float `13.0` → `'13'`),
  `_to_date`, `_to_time`, `_to_opt_decimal`, `_to_bool_si_no` (`SI`/`NO`
  + bool nativi).

- **`parse_corsa_row`**: mappa 1:1 i campi PdE → modello DB
  `corsa_commerciale`. Calcola `giorni_per_mese_json` (16 chiavi
  `gg_dic1AP`...`gg_anno`) e `valido_in_date_json` (lista ISO date).

- **`parse_composizioni`**: estrae le 9 righe di `corsa_composizione`
  (3 stagioni × 3 giorno_tipo × 6 attributi). Le 9 sono sempre
  presenti, anche se vuote.

- **`parse_periodicita`** (regex-based): tokenizza il testo per frasi
  su `". "`, riconosce 5 sub-pattern:
  - `Circola tutti i giorni` → `is_tutti_giorni=True`
  - `Circola dal X al Y` (anche multipli `, dal Z al W`)
  - `Circola DD/MM/YYYY, DD/MM/YYYY, ...`
  - `Non circola dal X al Y`
  - `Non circola DD/MM/YYYY, dal Z al W, ...` (misti)

- **`compute_valido_in_date`**: applica la periodicità all'intervallo
  `[valido_da, valido_a]`. Algoritmo:
  1. Se `is_tutti_giorni`, popola tutto il range
  2. Aggiungi `apply_intervals` (clip al range)
  3. Aggiungi `apply_dates` (filter al range)
  4. Sottrai `skip_intervals` e `skip_dates`

- **`cross_check_gg_mensili`**: confronta date calcolate con i
  `Gg_*` PdE per gen-nov (anno principale), dicembre split (dic1/dic2,
  dic1AP/dic2AP), e totale `gg_anno`. Ritorna lista di warning,
  vuota = match perfetto.

### Limite noto MVP (documentato in modulo)

Il parser usa **solo il campo testuale `Periodicità`**. Il PdE Trenord
ha anche `Codice Periodicità`, un mini-DSL con filtri giorno-della-
settimana (token tipo `G1-G7`, `EC`, `NCG`, `S`, `CP`, `P`, `ECF`)
che è la fonte di verità completa. Per i treni con filtri weekend
(es. `EC G6, G7 ...` = solo sabato/domenica), il `valido_in_date_json`
calcolato è **approssimativo** (eccessivo del ~50%).

Sulla fixture reale: **30/38 righe** (~79%) hanno periodicità
"semplice" e passano cross-check. **8/38 righe** (~21%) hanno
periodicità complessa con warning.

Decisione MVP: accetta i warning, importa comunque, log centralizzato.
Parser DSL `Codice Periodicità` rimandato a v1.x.

### Test (3 file, 31 nuovi test)

**`tests/test_pde_reader.py`** (5):
- Fixture esiste, ritorna 38 righe, 124 colonne
- Tipi: Periodicità è str, Treno 1 non None
- Formato non supportato → `ValueError`

**`tests/test_pde_periodicita.py`** (15):
- Empty text, `Circola tutti i giorni` puro, con skip interval, apply
  interval only, apply dates short list, `tutti i giorni dal X al Y`
  → apply_interval (NON is_tutti), long apply dates list, skip mixed,
  date interne intervallo non doppie
- `compute_valido_in_date`: tutti i giorni, minus skip, apply interval,
  apply dates filtered, skip overrides apply, clip to validity range

**`tests/test_pde_row_parser.py`** (11):
- Tutte le 38 righe parsano senza eccezioni
- Ogni riga ha 9 composizioni con keys complete (3×3 stagioni×giorni)
- ≥75% righe passano cross-check (threshold MVP, attualmente 79%)
- Sanity inverso: parser DEVE flaggare le righe complesse (non bug
  silenziosi)
- Riga 0 (treno 13 FN Cadorna→Laveno): campi base, valido_in_date
  popolato correttamente (383 giorni dal 14/12/2025 al 31/12/2026)
- Decimal preservati (`Decimal("72.152")` per km_tratta)
- Numero treno normalizzato a stringa intera (no trailing `.0`)

### Verifiche

- `pytest`: **69/69 verdi** (era 38/38, +31 nuovi)
- `ruff check`: All checks passed
- `ruff format --check`: 47 files formatted
- `mypy strict`: no issues found in **34 source files** (era 33, +1
  importers/pde.py)

### Stato

Sprint 3.1-3.5 completo. Parser PdE puro funzionante su fixture reale.
Limite documentato (filtro giorni settimana → v1.x).

### Prossimo step

**Sprint 3.6-3.8 — DB + CLI + idempotenza**:

- 3.6 `pde_importer.py`: orchestrator con bulk insert + transazione
  unica + tracking `corsa_import_run`
- 3.7 Idempotenza: SHA-256 file → skip se già importato; upsert per
  `(azienda_id, numero_treno, valido_da)`
- 3.8 CLI argparse: `python -m colazione.importers.pde --file ... --azienda ...`

Test integration end-to-end fixture → DB temp.

---

## 2026-04-26 (9) — Doc operativa import PdE

### Contesto

L'utente vuole tenere a portata di mano i comandi per importare il
PdE reale, così non si dimentica fra mesi. Documentati in 2 posti
complementari:

1. `docs/IMPORT-PDE.md` §9 — spec + workflow completo (per chi cerca
   "come funziona l'import")
2. `backend/data/pde-input/README.md` — quick reference dei comandi
   pronti copy-paste (per chi apre la cartella)

### Modifiche

**`docs/IMPORT-PDE.md`** §9 ricostruita: prima era 1 riga astratta
(`uv run ... --file ... --azienda trenord`), ora ha 6 sotto-sezioni:
- 9.1 Pre-requisiti (docker compose + alembic upgrade)
- 9.2 Procedura import (mkdir + cp + comando)
- 9.3 Output atteso
- 9.4 Verifica post-import (query DB)
- 9.5 Re-import + flag `--force`
- 9.6 Aggiornare la fixture quando arriva un nuovo PdE

**Nuovo `backend/data/pde-input/README.md`**: quick reference della
cartella locale. Ricorda comandi essenziali, convenzioni di
naming, workflow per multipli anni di PdE.

**`.gitignore`** raffinato: era `backend/data/pde-input/`
(ignora tutta la cartella). Ora `backend/data/pde-input/*` +
eccezione `!backend/data/pde-input/README.md`. Risultato verificato
con `git check-ignore`:
- `fake.numbers` → ignorato (regola riga 80)
- `README.md` → tracciato (eccezione riga 81)

### Verifica

`git check-ignore -v backend/data/pde-input/fake.numbers` ritorna
match con la regola `*` → ignorato. `git check-ignore -v README.md`
ritorna match con la regola `!` → committato.

### Stato

Fatto. La procedura di import PdE è documentata + accessibile sia
via `docs/` (spec) sia via cartella locale (cheat sheet).

### Prossimo step

Sprint 3.1+ vero — `importers/pde.py` con parser, idempotenza, CLI.
Stesso piano di prima, niente cambio scope.

---

## 2026-04-26 (8) — Sprint 3 prep: fixture PdE per test

### Contesto

Prima di scrivere il parser PdE (Sprint 3.1+), serve una **fixture
committata** per i test unitari + CI. Il file PdE reale (10580 righe,
6.9 MB) vive sul Mac dell'utente in
`/Users/spant87/Library/Mobile Documents/com~apple~Numbers/Documents/`,
**non si committa**: è dato commerciale e cambia ogni anno.

La fixture è una mini-versione del file reale, ~40 righe scelte per
coprire tutti i pattern di periodicità, salvata come `.xlsx` (formato
portable che gira ovunque, niente dipendenza `numbers-parser` su CI
Linux).

### Modifiche

**Nuovo `backend/scripts/build_pde_fixture.py`** (~140 righe):
- One-shot script per (ri)generare la fixture quando serve
- Apre file Numbers via `numbers-parser`, categorizza ~10580 righe per
  pattern (skip/apply interval, date list, doppia composizione,
  garantito festivo)
- Selezione deterministica: prime N indici per bucket
- Scrive `.xlsx` con `openpyxl` (header + righe + sheet "PdE RL")
- CLI: `--source <numbers-path>` `--output <xlsx-path>`

**Nuovo `backend/tests/fixtures/pde_sample.xlsx`** (19.5 KB):
- 124 colonne (header completo del PdE Trenord)
- 38 righe dati selezionate
- Coverage pattern Periodicità:
  - 10 skip interval (`Non circola dal X al Y`)
  - 8 apply interval (`Circola dal X al Y`)
  - 6 date list lunga (>20 slash, ~50-100 date)
  - 14 date list corta (1-5 date)
- Numero treno arriva come `int` (openpyxl converte i float
  integer-valued — comodo per il parser)

**`.gitignore`**: aggiunta sezione PdE input
(`backend/data/pde-input/`) per quando l'utente caricherà il file
reale localmente. Convenzione path:
`backend/data/pde-input/PdE-YYYY-MM-DD.numbers`.

### Verifica

- Script eseguito sul file reale Trenord 14dic2025-12dic2026 Rev5_RL
- Fixture rilegga correttamente con openpyxl: 124 colonne + 38 righe
- Conta pattern in fixture: 10+8+6+14 = 38 ✓
- File 19.5 KB → ben sotto soglia ragionevole per commit

### Stato

Sprint 3 prep fatto. Fixture committata, builder riproducibile.

### Prossimo step

**Sprint 3.1+ — Parser PdE vero** (`backend/src/colazione/importers/pde.py`):

- Lettura file `.numbers` o `.xlsx` (auto-detect dall'estensione)
- Parser singola riga → dataclass intermedio
- Parser composizione 9 combinazioni (stagione × giorno_tipo) per i 6
  attributi (categoria_posti, doppia_comp, vincolo, tipologia,
  bici, prm)
- Parser periodicità testuale → set di date ISO
- Calcolo `valido_in_date_json` denormalizzato (cross-validato con
  totali Gg_*)
- Bulk insert + transazione + tracking `corsa_import_run` + SHA-256
  per idempotenza
- CLI argparse

Effort stimato: ~3-4 turni di lavoro (Sprint 3 è il pezzo più fragile
del PIANO-MVP, parser periodicità è critico).

---

## 2026-04-26 (7) — FASE D Sprint 2: Auth JWT (Sprint 2 COMPLETATA)

### Contesto

Sprint 2 del PIANO-MVP: autenticazione JWT custom + bcrypt, endpoint
login/refresh/me, dependencies FastAPI per autorizzazione, seed di
2 utenti applicativi.

### Modifiche

**Modulo `backend/src/colazione/auth/`** (4 file):

- `password.py`: `hash_password()` + `verify_password()` su bcrypt
  (cost factor default 12). `verify_password` ritorna False (no
  raise) per hash malformati.
- `tokens.py`: `create_access_token()` (claims: sub, type=access,
  iat, exp, username, is_admin, roles, azienda_id),
  `create_refresh_token()` (claims minimi: sub, type=refresh, iat,
  exp), `decode_token(token, expected_type)` con
  `InvalidTokenError` per firma/scaduto/tipo errato. HS256.
- `dependencies.py`: `get_current_user()` da
  `Authorization: Bearer <token>` (HTTPBearer FastAPI), no DB query
  per request — claims vivono nel JWT. `require_role(role)` factory
  + `require_admin()` factory ritornano dependency che check
  ruolo/admin (admin bypassa role check).
- `__init__.py`: ri-esporta API pubblica del modulo.

**`backend/src/colazione/schemas/security.py`** (nuovo):
- `LoginRequest`, `TokenResponse`, `RefreshRequest`, `RefreshResponse`,
  `CurrentUser`. Distinto da `schemas/auth.py` perché qui sono shape
  I/O API, non entità DB.

**`backend/src/colazione/api/auth.py`** (nuovo):
- `POST /api/auth/login`: verify password → emette access+refresh,
  aggiorna `last_login_at`. Stessa risposta 401 per username
  inesistente o password sbagliata (no info leak).
- `POST /api/auth/refresh`: decode refresh → riemette access con
  ruoli aggiornati dal DB.
- `GET /api/auth/me`: ritorna `CurrentUser` corrente (utile per
  debug + frontend "chi sono io").

**`backend/src/colazione/main.py`**: registra
`app.include_router(auth_routes.router)`.

**Migrazione `backend/alembic/versions/0003_seed_users.py`**:
- 2 utenti: `admin` (is_admin=TRUE, ruolo ADMIN) +
  `pianificatore_giro_demo` (ruolo PIANIFICATORE_GIRO)
- Password da env `ADMIN_DEFAULT_PASSWORD` / `DEMO_PASSWORD`,
  fallback `admin12345` / `demo12345` per dev locale
- Hash bcrypt calcolato a runtime (cost 12) — implica che
  down/up cambia hash ma password resta uguale
- `downgrade()`: DELETE in ordine FK-safe (ruoli prima, app_user dopo)

**`backend/pyproject.toml`**: aggiunto
`[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` per
ignorare B008 sulle `Depends/Query/Path/Body/Header/Cookie/Form/
File/Security` di FastAPI (pattern standard).

**`.github/workflows/backend-ci.yml`**: aggiunto step
`Apply Alembic migrations` (`alembic upgrade head`) prima di
pytest. Necessario per i test che richiedono schema + seed
(test_models_match_db_tables, test_auth_endpoints).
**Bug fix preesistente** introdotto in Sprint 1.7 — la CI con
test_models_match_db_tables falliva perché lo schema non era
applicato. Adesso risolto.

### Test (4 file, 24 test nuovi)

**`tests/test_auth_password.py`** (5):
- hash è stringa bcrypt-prefixed
- hash è random per call (salt diverso)
- verify password corretta
- verify password sbagliata
- verify ritorna False per hash malformato

**`tests/test_auth_tokens.py`** (6):
- access token roundtrip (claims completi)
- refresh token roundtrip (claims minimi)
- decode rifiuta type errato (access usato come refresh)
- decode rifiuta token scaduto
- decode rifiuta firma sbagliata
- decode rifiuta garbage

**`tests/test_auth_endpoints.py`** (13):
- login admin (200, claims is_admin + ruolo ADMIN)
- login demo (200, ruolo PIANIFICATORE_GIRO)
- login wrong password (401)
- login unknown user (401)
- login missing fields (422 validation)
- refresh success (200 + nuovo access valido)
- refresh rifiuta access token (401)
- refresh rifiuta garbage (401)
- refresh rifiuta user_id inesistente (401)
- /me senza auth (401)
- /me con access valido (200)
- /me rifiuta refresh come access (401)
- /me rifiuta scheme non Bearer (401)

### Verifiche

- `pytest`: **38/38 verdi** (era 14/14, +24 nuovi)
- `ruff check`: All checks passed (B008 esentato per FastAPI Depends)
- `ruff format --check`: 39 files formatted
- `mypy strict`: no issues found in **33 source files** (era 28, +5
  nuovi: password, tokens, dependencies, schemas/security, api/auth)
- `alembic upgrade head` (3 migrazioni applicate)
- `alembic downgrade -1` (0003 reverted) → `app_user` count = 0
- `alembic upgrade head` (re-apply) → idempotente, conteggi
  ripristinati

Login funzionale verificato direttamente:
- admin/admin12345 → access token con `is_admin=True`, `roles=[ADMIN]`
- pianificatore_giro_demo/demo12345 → `roles=[PIANIFICATORE_GIRO]`

### Stato

**Sprint 2 COMPLETATA**. Tutto Sprint 2.1-2.5 chiuso in un commit
unico (vs ipotesi PIANO-MVP di 5 commit separati).

Backend ora ha:
- Schema DB completo (Sprint 1)
- Seed Trenord + 2 utenti applicativi (Sprint 1.6 + 2.5)
- Modelli ORM (Sprint 1.7) e schemas Pydantic (Sprint 1.8)
- Auth JWT funzionante con login/refresh/me + role-based access
  control via `require_role(...)`

### Prossimo step

**Sprint 3 — Importer PdE** (stima 3-4 giorni nel PIANO-MVP, il pezzo
più fragile):

- 3.1 `importers/pde.py` skeleton + lettura file Numbers
- 3.2 Parser singola riga → CorsaCommercialeCreate
- 3.3 Parser composizione 9 combinazioni stagione × giorno_tipo
- 3.4 Parser periodicità testuale (intervalli skip, date singole,
      date extra)
- 3.5 Calcolo `valido_in_date_json` denormalizzato
- 3.6 Bulk insert + transazione + tracking corsa_import_run
- 3.7 Idempotenza (SHA-256 file, re-import 0 nuovi insert)
- 3.8 CLI: `uv run python -m colazione.importers.pde --file ...`

Il file PdE reale Trenord è ~10580 corse, target import < 30s.
Spec dettagliata in `docs/IMPORT-PDE.md`. Servirà fixture: prendere
50 righe del file reale.

Decision aperta: il file Numbers reale del PdE 2025-12-14 → 2026-12-12
è disponibile localmente o serve l'utente per fornirlo? Da chiedere
quando si parte con Sprint 3.

---

## 2026-04-26 (6) — FASE D Sprint 1.8: Schemas Pydantic (Sprint 1 COMPLETATA)

### Contesto

Sprint 1.8 (ULTIMO della Sprint 1): schemas Pydantic per
serializzazione I/O API. Specchio dei modelli ORM in 7 file per strato.

### Modifiche

**Nuovo `backend/src/colazione/schemas/` (7 file)**:

- `anagrafica.py`: AziendaRead, StazioneRead, MaterialeTipoRead,
  LocalitaManutenzioneRead, LocalitaManutenzioneDotazioneRead,
  DepotRead, DepotLineaAbilitataRead, DepotMaterialeAbilitatoRead
- `corse.py`: CorsaImportRunRead, CorsaCommercialeRead (~30 campi),
  CorsaComposizioneRead, CorsaMaterialeVuotoRead
- `giri.py`: GiroMaterialeRead, VersioneBaseGiroRead,
  GiroFinestraValiditaRead, GiroGiornataRead, GiroVarianteRead,
  GiroBloccoRead
- `revisioni.py`: RevisioneProvvisoriaRead, RevisioneProvvisoriaBloccoRead,
  RevisioneProvvisoriaPdcRead
- `turni_pdc.py`: TurnoPdcRead, TurnoPdcGiornataRead, TurnoPdcBloccoRead
- `personale.py`: PersonaRead, AssegnazioneGiornataRead,
  IndisponibilitaPersonaRead
- `auth.py`: AppUserRead (no `password_hash` per non leakare bcrypt
  in API), AppUserRuoloRead, NotificaRead, AuditLogRead

**Pattern Pydantic v2**:
- `model_config = ConfigDict(from_attributes=True)` su ogni schema
  (parsing da modelli ORM o da dict)
- Tipi standard Python (`int`, `str`, `bool`, `datetime`, `date`,
  `time`, `Decimal`, `dict[str, Any]`, `list[Any]`)
- `Mapped[X | None] = None` per nullable, default `None`
- Niente `Create`/`Update` (verranno aggiunti quando le route
  POST/PATCH ne avranno bisogno, Sprint 4+)
- Niente nested relationships (es. `composizioni: list[...]` su
  CorsaCommerciale) — minimalismo, si arricchirà quando servirà

**`schemas/__init__.py`**: importa e ri-esporta 31 schemi, ordinato
per strato in `__all__`.

### Test

**Nuovo `backend/tests/test_schemas.py`** (6 test):
- `test_schemas_all_exported`: 31 schemi nel `__all__`, tutti
  importabili
- `test_azienda_read_from_dict_fixture`: parsing da dict (input API
  request body)
- `test_azienda_read_from_orm_instance`: parsing da Azienda ORM
  in memoria (path response_model)
- `test_localita_manutenzione_read_pool_esterno`: schema con
  campo nullable + flag bool (POOL_TILO con `is_pool_esterno=True`)
- `test_corsa_commerciale_read_with_decimal_and_time`: tipi
  complessi (time, date, Decimal, JSONB)
- `test_schemas_serialize_to_json`: output `model_dump_json()`
  serializzabile (per FastAPI response)

### Verifiche

- `pytest`: **14/14 verdi** (era 8/8, +6 nuovi su schemi)
- `ruff check`: All checks passed (autofix applicato:
  `timezone.utc` → `datetime.UTC` per Python 3.11+)
- `ruff format --check`: 34 files already formatted
- `mypy strict`: no issues found in **28 source files** (era 21,
  +7 nuovi: 7 file schemas)

### Stato

**Sprint 1 COMPLETATA**. Backend ha:
- main.py + /health + config.py (Sprint 1.1, 1.2)
- db.py async (Sprint 1.3)
- Alembic setup (Sprint 1.4)
- Migrazione 0001 con 31 tabelle (Sprint 1.5)
- Migrazione 0002 con seed Trenord (Sprint 1.6)
- 31 modelli ORM (Sprint 1.7)
- 31 schemi Pydantic Read (Sprint 1.8)

Pronto per scrivere endpoint REST (auth + corse + depositi).

### Riepilogo Sprint 1

| Passo | Output | Commit |
|-------|--------|--------|
| 1.1 | main.py + /health | (in 0.1, `83b4f85`) |
| 1.2 | config.py Pydantic Settings | (in 0.1, `83b4f85`) |
| 1.3 | db.py async + Postgres CI | `4f4edcd` |
| 1.4 | Alembic setup async | `44e8fe8` |
| 1.5 | Migrazione 0001 (31 tabelle) | `e047672` |
| 1.6 | Migrazione 0002 seed Trenord | `59455ca` |
| 1.7 | Modelli SQLAlchemy ORM (31) | `56dfaee` |
| 1.8 | Schemas Pydantic Read (31) | (questo commit) |

Effort reale Sprint 1: ~1 sessione lavoro, vs stima 2-3 giorni
del PIANO-MVP. Stima generosa ma corretta come buffer.

### Prossimo step

**Sprint 2 — Auth + utenti** (stima 2 giorni):
- 2.1 `colazione/auth/` (hash bcrypt, JWT encode/decode, dependencies)
- 2.2 Endpoint `POST /api/auth/login`
- 2.3 Endpoint `POST /api/auth/refresh`
- 2.4 Dependency `get_current_user` + `require_role`
- 2.5 Migrazione `0003_seed_users.py` → admin + pianificatore_giro_demo

Modulo `auth/` da costruire da zero. JWT custom + bcrypt come da
STACK-TECNICO.md §6. Schemas dedicati in `schemas/security.py` (non
nel `auth.py` strato 5 dei modelli).

---

## 2026-04-26 (5) — FASE D Sprint 1.7: Modelli SQLAlchemy ORM

### Contesto

Sprint 1.7 del PIANO-MVP: mappare le 31 tabelle create dalle
migrazioni 0001/0002 in classi SQLAlchemy ORM, in modo che il backend
possa usarle via session async.

### Decisione layout (deviazione dal PIANO-MVP)

PIANO-MVP §2 step 1.7 dice "(1 file per entità)" → 31 file. Ho
optato per **1 file per strato (7 file)**:
- evita 31 file da 10-20 righe (boilerplate × 7)
- entità dello stesso strato sono fortemente correlate (es. `giro_*`
  o `turno_pdc_*`)
- pattern standard nei progetti SQLAlchemy seri
- la docstring di `db.py` (Sprint 1.3) è stata aggiornata di
  conseguenza

Le 31 classi restano tutte importabili da `colazione.models`.

### Modifiche

**Nuovo `backend/src/colazione/models/` (7 file)**:

- `anagrafica.py` (Strato 0, 8 classi): Azienda, Stazione,
  MaterialeTipo, LocalitaManutenzione, LocalitaManutenzioneDotazione,
  Depot, DepotLineaAbilitata, DepotMaterialeAbilitato
- `corse.py` (Strato 1, 4 classi): CorsaImportRun, CorsaCommerciale
  (la più grossa, ~30 colonne), CorsaComposizione, CorsaMaterialeVuoto
- `giri.py` (Strato 2, 6 classi): GiroMateriale, VersioneBaseGiro,
  GiroFinestraValidita, GiroGiornata, GiroVariante, GiroBlocco
- `revisioni.py` (Strato 2bis, 3 classi): RevisioneProvvisoria,
  RevisioneProvvisoriaBlocco, RevisioneProvvisoriaPdc
- `turni_pdc.py` (Strato 3, 3 classi): TurnoPdc, TurnoPdcGiornata,
  TurnoPdcBlocco
- `personale.py` (Strato 4, 3 classi): Persona, AssegnazioneGiornata,
  IndisponibilitaPersona
- `auth.py` (Strato 5, 4 classi): AppUser, AppUserRuolo, Notifica,
  AuditLog

**`models/__init__.py`**: importa e ri-esporta tutte le 31 classi
(elenco esplicito in `__all__`, ordinato per strato).

**Stile SQLAlchemy 2.0 moderno**:
- `Mapped[T]` + `mapped_column()` per type safety
- `Mapped[dict[str, Any]]` / `Mapped[list[Any]]` per JSONB
  (mypy strict richiede tipi parametrizzati)
- `Mapped[X | None]` per nullable
- `BigInteger`, `String(N)`, `Text`, `Boolean`, `Integer`,
  `Date`, `Time`, `DateTime(timezone=True)`, `Numeric(p,s)` per i
  tipi DB
- `JSONB` da `sqlalchemy.dialects.postgresql`, `INET` per audit IP
- `server_default=func.now()` per `created_at`/`updated_at`
- `default=dict` / `default=list` per JSONB Python-side default

**Cosa NON è incluso** (intenzionalmente, per minimalismo):
- CHECK constraint (sono in DB, validazione DB-side)
- UNIQUE multi-colonna come `__table_args__` (sono in DB)
- Indici secondari (sono in DB)
- `relationship()` (verrà aggiunto in Sprint 4 quando le route ne
  avranno bisogno)

L'ORM è "specchio della struttura DB" minimale. L'autorità del
schema resta nelle migrazioni Alembic, non nei modelli.

**Aggiornato `backend/src/colazione/db.py`**: docstring di `Base`
allineata al nuovo layout per-strato.

### Test

**Nuovo `backend/tests/test_models.py`** (3 test):
- `test_models_register_on_metadata`: 31 tabelle su `Base.metadata`
- `test_models_all_exported`: `__all__` contiene 31 nomi e tutti
  importabili
- `test_models_match_db_tables`: `__tablename__` ORM matchano le
  tabelle reali in `pg_tables` (skippato se DB non configurato)

### Verifiche

- `python -c "from colazione.models import *"` → 31 classi importate
  senza errori
- `Base.metadata.tables` → 31 tabelle, nomi tutti coerenti con DB
  (verificato anche via query `pg_tables`)
- `pytest`: **8/8 verdi** (era 5/5, +3 nuovi su modelli)
- `ruff check`: All checks passed
- `ruff format`: 26 files formatted
- `mypy src/colazione`: no issues found in **21 source files**
  (era 14 prima, +7 nuovi: 7 modelli)

### Stato

Sprint 1.7 completo. Backend ha schema DB completo + dati seed +
modelli ORM tutti registrati su `Base.metadata`. Pronto per scrivere
schemas Pydantic (Sprint 1.8) e poi gli endpoint API.

### Prossimo step

Sprint 1.8 del PIANO-MVP: schemas Pydantic in
`backend/src/colazione/schemas/` per serializzazione I/O API. Naming
convention `<Entita>Read`, `<Entita>Create`, `<Entita>Update` (vedi
PIANO-MVP §2 step 1.8). Tipico parsing con `from_attributes=True` per
costruire da modello ORM.

---

## 2026-04-26 (4) — FASE D Sprint 1.6: Migrazione 0002 seed Trenord

### Contesto

Sprint 1.6 del PIANO-MVP: popolamento iniziale dati Trenord nelle
tabelle anagrafica create da 0001. Materializza la sezione §12 di
`SCHEMA-DATI-NATIVO.md` in INSERT eseguibili via Alembic.

### Modifiche

**Nuovo `backend/alembic/versions/0002_seed_trenord.py`** (~340 righe):

Dati statici come liste Python in cima al file (estratti da
`docs/SCHEMA-DATI-NATIVO.md` §12 + `data/depositi_manutenzione_trenord_seed.json`):
- `LOCALITA_MANUTENZIONE` (7 tuple)
- `DEPOT_TRENORD` (25 tuple)
- `MATERIALE_CODES` (69 codici, ordinati alfabeticamente)
- `DOTAZIONE` (84 tuple)

Helper `_sql_str()` e `_sql_bool()` per costruire VALUES SQL safe (NULL
e quoting standard).

`upgrade()` — 5 sezioni di INSERT:
- §12.1 azienda Trenord con `normativa_pdc_json` completo (15 campi
  da NORMATIVA-PDC: 510/420 min, finestre refezione 11:30-15:30 e
  18:30-22:30, FR 1/sett 3/28gg, riposo 62h, ecc.)
- §12.2 7 località manutenzione: 6 IMPMAN reali + POOL_TILO_SVIZZERA
  (`is_pool_esterno=TRUE`, `azienda_proprietaria_esterna='TILO'`)
- §12.3 25 depot PdC, tutti `tipi_personale_ammessi='PdC'`
- `materiale_tipo` (69 codici, solo `codice` + `azienda_id`, altri
  campi NULL/default — arricchimento a builder time)
- `localita_manutenzione_dotazione` (84 righe, JOIN su
  `localita_manutenzione.codice` per risolvere FK runtime)

Stile `(VALUES …) AS v CROSS JOIN azienda` come da spec §12, evita
hard-coding di `azienda_id` (auto-generato).

`downgrade()`: 5 DELETE in ordine FK-safe (figli → padri), filtrati
per `azienda_id = (SELECT id FROM azienda WHERE codice='trenord')` —
non tocca seed di altre aziende future.

POOL_TILO_SVIZZERA è creato senza dotazione (pool esterno, materiale
non gestito da Trenord). NON_ASSEGNATO del seed JSON è escluso
(placeholder applicativo).

### Verifiche locali

`alembic upgrade head` → conteggi:
- `azienda` = 1
- `localita_manutenzione` = 7
- `depot` = 25
- `materiale_tipo` = 69
- `localita_manutenzione_dotazione` = 84

Totale pezzi materiale: 1612 (974 FIORENZA + 299 NOVATE + 169 CAMNAGO
+ 92 CREMONA + 57 LECCO + 21 ISEO).

`normativa_pdc_json` verificato con `jsonb_pretty()`: 15 chiavi
presenti coi valori corretti (max_prestazione 510, refez 30, finestre
[690,930] e [1110,1350], ecc.).

`alembic downgrade -1` → 5 tabelle a 0 righe (clean).
`alembic upgrade head` (di nuovo) → conteggi identici → **idempotente**.

`pytest`: 5/5 verdi.
`ruff check`: All checks passed.
`ruff format --check`: 18 files already formatted.
`mypy src/colazione`: no issues found in 14 source files.

### Stato

Sprint 1.6 completo. DB Postgres ha azienda Trenord + 7 località
manutenzione + 25 depot + 69 tipi materiale + 84 righe dotazione.
Schema 0001 + seed 0002 = base anagrafica pronta per Strato 1 (corse
PdE).

### Prossimo step

Sprint 1.7: modelli SQLAlchemy ORM in `backend/src/colazione/models/`,
una classe per entità (Azienda, LocalitaManutenzione, Depot,
MaterialeTipo, …). Usano `Base` da `db.py` (Sprint 1.3) e mappano le
tabelle create dalle migrazioni 0001/0002.

---

## 2026-04-26 (3) — FASE D Sprint 1.5: Migrazione 0001 (31 tabelle)

### Contesto

Sprint 1.5 del PIANO-MVP: il pezzo grosso. Materializza
SCHEMA-DATI-NATIVO.md in DDL eseguibile via Alembic.

### Modifiche

**`alembic.ini`**: post-write hook ruff_format cambiato da
`type=console_scripts` (non funziona con uv) a `type=exec` con
`executable=ruff`. Ora i file di migrazione generati sono auto-formattati.

**Nuovo `backend/alembic/versions/0001_initial_schema.py`** (~600 righe):

`upgrade()`:
- Estensione `pg_trgm`
- **Strato 0** (8 tabelle anagrafica): azienda, stazione,
  materiale_tipo, localita_manutenzione +dotazione, depot
  +linea_abilitata +materiale_abilitato
- **Strato 1** (4 tabelle LIV 1): corsa_import_run,
  corsa_commerciale, corsa_composizione, corsa_materiale_vuoto
- **Strato 2** (6 tabelle LIV 2): giro_materiale, versione_base_giro,
  giro_finestra_validita, giro_giornata, giro_variante, giro_blocco
- **Strato 2bis** (3 tabelle revisioni): revisione_provvisoria,
  revisione_provvisoria_blocco, revisione_provvisoria_pdc
- **Strato 3** (3 tabelle LIV 3): turno_pdc, turno_pdc_giornata,
  turno_pdc_blocco
- **Strato 4** (3 tabelle LIV 4): persona, assegnazione_giornata,
  indisponibilita_persona
- **Strato 5** (4 tabelle auth+audit): app_user, app_user_ruolo,
  notifica, audit_log
- FK cross-table risolte con ALTER (corsa_materiale_vuoto.giro_materiale_id,
  persona.user_id, indisponibilita_persona.approvato_da_user_id)
- ~30 indici secondari (FK, query frequenti, GIN su JSONB e trigram
  per persona.cognome/nome)

**Totale 31 tabelle** + `alembic_version` di Alembic = 32.

`downgrade()`: drop di tutto in ordine inverso, FK cross-table prima,
poi tabelle CASCADE. Ripristina DB pulito.

### Verifiche locali

- `alembic upgrade head`: 32 tabelle create (verificato con `\dt` +
  `SELECT COUNT(*) FROM information_schema.tables`)
- `alembic downgrade base`: torna a 1 tabella (alembic_version)
- `alembic upgrade head` (di nuovo): di nuovo 32 → **idempotente**
- `pytest`: 5/5 verdi
- `ruff/format/mypy`: tutti verdi

### Stato

Sprint 1.5 completo. DB Postgres ha schema completo del modello v0.5,
testato roundtrip up/down/up.

### Prossimo step

Sprint 1.6: migrazione `0002_seed_trenord.py` con 1 azienda + 7
località manutenzione + 25 depot + dotazione iniziale dal seed JSON.

---

## 2026-04-26 (2) — FASE D Sprint 1.4: Alembic setup async

### Contesto

Sprint 1.4 del PIANO-MVP: setup Alembic con env.py async-compatible.
Ancora niente migrazioni reali (quelle in 1.5).

### Modifiche

**`backend/alembic.ini`**:
- `script_location = alembic`
- `prepend_sys_path = src` (per import `colazione`)
- `file_template` con timestamp + slug per nomi file ordinati cronologicamente
- `sqlalchemy.url` vuoto (settato runtime da env in env.py)
- Post-write hook `ruff_format` (auto-format dei file generati)

**`backend/alembic/env.py`** (async support):
- Override `sqlalchemy.url` con `settings.database_url`
- `target_metadata = Base.metadata` (vuoto in v0, popolato in 1.7)
- `run_migrations_offline()` per modalità offline
- `run_async_migrations()` con `async_engine_from_config` + `connection.run_sync(do_run_migrations)`
- `compare_type=True`, `compare_server_default=True` per autogenerate accurato

**`backend/alembic/script.py.mako`**: template moderno con type hints
(`Sequence`, `str | None`).

### Verifiche

- `alembic current`: connessione DB OK, output pulito
- `alembic upgrade head`: no-op (nessuna migrazione presente, ok)
- `alembic history`: vuoto
- `pytest`: 5/5 passati
- `ruff`/`mypy`: tutti verdi

### Stato

Sprint 1.4 completo. Alembic pronto per accogliere migrazioni.

### Prossimo step

Sprint 1.5: migrazione `0001_initial_schema.py` con tutte le 31
tabelle da SCHEMA-DATI-NATIVO.md. È il pezzo grosso (~1000 righe SQL).

---

## 2026-04-26 — FASE D Sprint 1.3: db.py async + Postgres in CI

### Contesto

Inizio Sprint 1 (backend reale). Utente ha installato Docker Desktop
(v29.4.0) → Postgres 16.13 ora gira su localhost:5432 via
`docker compose up -d db`.

Sprint 1.3 del PIANO-MVP: layer DB async SQLAlchemy.

### Modifiche

**Nuovo `backend/src/colazione/db.py`**:
- `Base(DeclarativeBase)`: classe base ORM
- `get_engine()`: singleton lazy `AsyncEngine` con `pool_pre_ping`
- `get_session_factory()`: `async_sessionmaker`
- `session_scope()`: context manager async per script standalone
  (auto commit/rollback)
- `get_session()`: FastAPI dependency yields sessione per request
- `dispose_engine()`: cleanup al shutdown

**`pyproject.toml`**: deps DB rinforzate
- `sqlalchemy[asyncio]>=2.0` (era plain `sqlalchemy>=2.0`)
- `greenlet>=3.0` esplicito (richiesto per async SQLAlchemy)

**`backend/tests/test_db.py`**: 2 smoke test
- `test_db_connection_returns_one`: SELECT 1
- `test_db_postgres_version`: server_version_num >= 160000
- Skip automatico se `SKIP_DB_TESTS=1` env var

**`.github/workflows/backend-ci.yml`**: aggiunto service Postgres 16
- `services.postgres` con healthcheck
- env `DATABASE_URL` puntata a `localhost:5432`
- I test DB ora girano anche in CI

### Verifiche locali

- Postgres 16.13 healthy via Docker (5432 esposta)
- `pytest`: **5/5 passati** (3 main.py + 2 db)
- `ruff check`: All checks passed
- `ruff format --check`: 17 files formatted
- `mypy src/colazione`: no issues 14 source files

### Stato

Sprint 1.3 completo. Postgres locale in funzione, layer DB async
testato.

### Prossimo step

Sprint 1.4: Alembic setup (`alembic.ini` + `env.py` async + script.py.mako).

---

## 2026-04-25 (14) — FASE D Sprint 0.5: README.md (Sprint 0 COMPLETATA)

### Contesto

Sprint 0.5 del PIANO-MVP §2: README quick start per chiunque cloni il
repo. Ultimo passo della Sprint 0.

### Modifiche

**Nuovo `README.md` root** (~190 righe):
- Frase manifesto + diagramma piramide (PdE → giro → PdC → persone)
- Badge CI per backend-ci e frontend-ci
- Stato attuale (Sprint 0 quasi completa)
- Prerequisiti (Python 3.12, Node 20, uv, pnpm, Docker)
- Quick start in 5 comandi (clona → docker db → backend → frontend →
  browser)
- Alternativa "tutto in Docker"
- Comandi sviluppo backend + frontend (sync/test/lint/format/build)
- Albero struttura repo commentato
- Indice documentazione `docs/` (10 documenti linkati)
- Sezione "Contribuire" (Conventional Commits + TN-UPDATE +
  METODO-DI-LAVORO)
- Licenza Proprietary + manifesto greenfield

### Stato

**Sprint 0 COMPLETATA**. 5 passi atomici ognuno con commit + verifica.

### Riepilogo Sprint 0

| Passo | Output | Commit |
|-------|--------|--------|
| 0.1 | backend/ skeleton (FastAPI + uv + ruff + mypy + pytest) | `83b4f85` |
| 0.2 | frontend/ skeleton (React + Vite + TS + Tailwind + Vitest) | `b5873ca` |
| 0.3 | docker-compose.yml (Postgres + backend + frontend) | `d700e24` |
| 0.4 | GitHub Actions CI (backend-ci + frontend-ci) | `27b5914` |
| 0.5 | README.md quick start | (questo commit) |

### Verifiche locali (cumulative)

- Backend: pytest 3/3, ruff 0 errori, mypy strict no issues
- Frontend: vitest 2/2, eslint 0 errori, typecheck OK, build 143 KB
  gzip 46 KB, prettier check OK
- docker-compose.yml: YAML valido (3 servizi)
- CI workflows: YAML valido (2 workflow, jobs e triggers definiti)

### Verifica end-to-end CI

Da controllare a breve dopo questo push: stato di backend-ci e
frontend-ci su GitHub Actions per master. Se entrambi diventano verdi,
**Sprint 0 e' confermata funzionante anche su Linux pulito** (no
quirk path iCloud locale).

### Prossimo step

**Sprint 1 — Backend skeleton vero**:
- 1.1 main.py + /health (gia fatto in 0.1)
- 1.2 config.py Pydantic Settings (gia fatto in 0.1)
- 1.3 db.py async engine + session manager
- 1.4 Alembic setup + env.py async
- 1.5 Migrazione 0001_initial_schema.py (31 tabelle da SCHEMA-DATI-NATIVO.md)
- 1.6 Migrazione 0002_seed_trenord.py (azienda + 7 depositi + 25 depot)
- 1.7 Modelli SQLAlchemy ORM in models/
- 1.8 Schemas Pydantic in schemas/

Effort stimato Sprint 1: 2-3 giorni lavorativi. La parte grossa è la
migrazione 0001 (31 tabelle).

---

## 2026-04-25 (13) — FASE D Sprint 0.4: GitHub Actions CI

### Contesto

Sprint 0.4 del PIANO-MVP §2: CI automatica su push/PR per backend e
frontend. La CI girerà su Linux pulito (Ubuntu) e validerà che lo
skeleton funziona indipendentemente dalle quirk locali (path iCloud).

### Modifiche

**`.github/workflows/backend-ci.yml`**:
- Trigger: push su master, PR, workflow_dispatch (manual). Path
  filter su `backend/**` + workflow stesso.
- Steps: checkout → setup-python 3.12 → astral-sh/setup-uv (cache
  built-in) → `uv sync --extra dev` → `ruff check` → `ruff format
  --check` → `mypy strict` → `pytest --cov`.
- Working dir `backend/`.
- Timeout 10 min.

**`.github/workflows/frontend-ci.yml`**:
- Trigger: push su master, PR, workflow_dispatch (manual). Path
  filter su `frontend/**` + workflow stesso.
- Steps: checkout → setup-node 20 → pnpm/action-setup v10.33.2 →
  cache pnpm store → `pnpm install --frozen-lockfile` →
  `format:check` → `lint` → `typecheck` → `test` (vitest) → `build`.
- Cache `~/.pnpm-store` con key da hash di `pnpm-lock.yaml`.

### Verifiche

- Validato YAML manualmente con PyYAML: entrambi i workflow hanno
  triggers e jobs ben definiti.
- **La verifica vera arriverà al push**: GitHub Actions girerà
  backend-ci e frontend-ci. Se entrambi diventano verdi, lo skeleton
  e' confermato funzionante in CI Linux pulita.

### Stato

Sprint 0.4 file pronti, push imminente attiva i workflow.

### Prossimo step

Sprint 0.5 (ULTIMO della Sprint 0): `README.md` con quick start (clona
repo → 5 comandi per arrivare alla pagina home). Dopo questo, Sprint 0
finito, si passa a Sprint 1 (backend skeleton vero: SQLAlchemy +
Alembic + 31 tabelle).

---

## 2026-04-25 (12) — FASE D Sprint 0.3: docker-compose.yml

### Contesto

Sprint 0.3 del PIANO-MVP §2: orchestrazione 3 container (Postgres + backend
+ frontend) per dev locale.

### Modifiche

**Nuovo `docker-compose.yml`** (alla root):
- Service `db`: `postgres:16-alpine`, healthcheck `pg_isready`,
  volume nominato `colazione_pgdata`, porta 5432
- Service `backend`: build da `./backend/Dockerfile`, env DATABASE_URL
  pointing a `db:5432`, porta 8000, volumi montati per hot reload
  (src, tests, alembic), command override con `--reload --app-dir src`
- Service `frontend`: build da `./frontend/Dockerfile`, env
  `VITE_API_BASE_URL=http://localhost:8000`, porta 5173, volumi
  montati per hot reload (src, public, index.html)
- Dependency chain: frontend → backend → db (con `service_healthy`)

**`.gitignore`**: aggiunto `*.tsbuildinfo` (escludi cache TypeScript
incremental build, era trapelata in Sprint 0.2). Untracked
`frontend/tsconfig.app.tsbuildinfo` e `frontend/tsconfig.node.tsbuildinfo`.

### Verifiche

- Docker non installato sul sistema utente → impossibile
  `docker compose up` o `docker compose config`
- **Validato YAML manualmente** con PyYAML: 3 servizi (db, backend,
  frontend), 1 volume nominato (colazione_pgdata), porte 5432/8000/5173.
  Struttura coerente con STACK-TECNICO.md §7

### TODO post-Docker-install (sistema utente)

Quando l'utente installa Docker Desktop o OrbStack:
1. `docker compose config` → valida la sintassi con compose engine
2. `docker compose up -d db` → verifica Postgres parte (healthcheck OK)
3. `docker compose up backend` → verifica build + uvicorn risponde su :8000/health
4. `docker compose up frontend` → verifica Vite dev su :5173, app
   contatta backend
5. `docker compose down -v` → pulizia (cancella anche volume DB)

### Stato

Sprint 0.3 file committato. Verifica funzionale rinviata a quando
Docker sarà disponibile.

### Prossimo step

Sprint 0.4: GitHub Actions CI per backend + frontend. La CI gira su
container Linux puliti (no quirk path iCloud), quindi sarà la prima
verifica end-to-end "ufficiale" che lo skeleton funziona.

---

## 2026-04-25 (11) — FASE D Sprint 0.2: frontend skeleton

### Contesto

Sprint 0.2 del PIANO-MVP §2: scaffolding frontend React+TypeScript+
Vite+Tailwind. Niente template `npm create vite` (interattivo) — file
scritti a mano per controllo esplicito.

### Modifiche

**pnpm 10.33.2 installato** via `npm install -g pnpm` (corepack non
disponibile sul sistema utente).

**Nuovo `frontend/`**:
- `package.json`: deps React 18, react-router-dom, TanStack Query,
  Radix primitives (dialog, dropdown, popover, toast, slot), Tailwind
  3, lucide-react, class-variance-authority, clsx, tailwind-merge.
  Dev deps: TypeScript 5.7, ESLint 9 flat config, Prettier 3 +
  prettier-plugin-tailwindcss, Vitest 2 + @testing-library/react +
  jsdom, Vite 5.4 (compatibile Vitest 2)
- `tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`:
  TypeScript strict, path alias `@/*` → `src/*`, target ES2022
- `vite.config.ts`: import da `vitest/config` per supportare campo
  `test`. Plugin React, alias `@`, server porta 5173
- `tailwind.config.ts`: palette base shadcn (background, foreground,
  primary, secondary, muted, accent, destructive)
- `postcss.config.js`: tailwindcss + autoprefixer
- `eslint.config.js`: flat config con typescript-eslint + react-hooks
  + react-refresh
- `.prettierrc.json`: semi true, double quotes, plugin Tailwind
- `.prettierignore`: dist/, node_modules/, lockfile
- `.env.example`: VITE_API_BASE_URL=http://localhost:8000
- `.nvmrc`: node 20
- `Dockerfile`: node:20-alpine + corepack + pnpm install
- `.dockerignore`

**`frontend/src/`**:
- `main.tsx`: createRoot + StrictMode + import App
- `App.tsx`: skeleton con titolo "Colazione" + sottotitolo Sprint
  0.2 + smoke test connessione backend (fetch `/health`)
- `index.css`: Tailwind directives + reset minimo body
- `lib/utils.ts`: helper shadcn `cn()` (clsx + tailwind-merge)
- `test/setup.ts`: import `@testing-library/jest-dom/vitest`
- `App.test.tsx`: 2 test smoke (titolo, sottotitolo Sprint)

**Cartelle vuote** create per moduli futuri:
- `components/ui/` (shadcn add per componente)
- `components/domain/` (componenti dominio)
- `routes/` (1 cartella per ruolo, vedi RUOLI-E-DASHBOARD.md)
- `hooks/` (TanStack Query hooks)

### Verifiche

- `pnpm install`: deps installate
- `pnpm typecheck`: no errori
- `pnpm lint`: no errori
- `pnpm test`: **2/2 test passati**
- `pnpm format:check`: All matched files use Prettier code style
- `pnpm build`: dist generato, **143 KB JS gzipped 46 KB**

### Quirk risolti durante setup

1. `defineConfig` da `vite` non supporta campo `test` → cambiato a
   import `from "vitest/config"`.
2. Vite 6 incompatibile con Vitest 2 (mismatch tipi PluginOption) →
   declassato Vite a `^5.4.0`.
3. ESLint 9 flat config richiede `@eslint/js` come dipendenza
   esplicita → aggiunta a devDependencies.

### Stato

Sprint 0.2 completo. Frontend skeleton pronto, smoke test backend
nella UI (mostrerà "non raggiungibile" se backend non gira).

### Prossimo step

Sprint 0.3: `docker-compose.yml` (Postgres + backend + frontend).
**Richiede installazione Docker Desktop o OrbStack** sul sistema
utente. Suggerisco di chiedere all'utente prima di procedere.

---

## 2026-04-25 (10) — FASE D Sprint 0.1: backend skeleton

### Contesto

Inizio costruzione codice. Sprint 0.1 del PIANO-MVP §2: scaffolding
backend FastAPI con Python 3.12 + uv, struttura cartelle per moduli
futuri.

### Modifiche

**Nuovo `backend/`**:
- `pyproject.toml`: dipendenze runtime (FastAPI, SQLAlchemy 2.0,
  alembic, psycopg3, Pydantic v2, bcrypt, pyjwt, openpyxl,
  numbers-parser) + extras dev (ruff, mypy, pytest, pytest-cov,
  pytest-asyncio, httpx). Config ruff line-length 100, mypy strict,
  pytest pythonpath=["src"]
- `.python-version`: 3.12
- `Dockerfile`: image python:3.12-slim + uv per build, multi-stage
  (deps cached, project install separato)
- `.dockerignore`
- `.env.example`: template per .env.local

**Struttura `backend/src/colazione/`**:
- `__init__.py` (versione 0.1.0)
- `main.py`: FastAPI app skeleton con `/health` endpoint + CORS
- `config.py`: Pydantic Settings (DATABASE_URL, JWT, admin, CORS)
- Cartelle vuote (con `__init__.py`) per: `auth/`, `models/`,
  `schemas/`, `api/`, `domain/{builder_giro,builder_pdc,normativa,revisioni}`,
  `importers/`

**`backend/tests/test_main.py`**:
- `test_health_endpoint_returns_ok` → 200 OK
- `test_app_metadata` → titolo + versione corretti
- `test_openapi_schema_exists` → /openapi.json contiene /health

**`backend/alembic/versions/.gitkeep`** (Alembic vero in Sprint 1.4)

**`.gitignore`** aggiornato: `.claude/` interamente ignorato (era
solo `.claude/settings.local.json`).

### Verifiche

- `uv sync --extra dev`: deps installate (~50 pacchetti)
- `uv run pytest -v`: **3/3 test passati**
- `uv run ruff check .`: All checks passed (dopo --fix automatico)
- `uv run ruff format --check .`: 15 files already formatted
- `uv run mypy src/colazione`: no issues found in 13 source files

### Quirk locale documentato

Il path repo `Mobile Documents/com~apple~CloudDocs/...` (iCloud sync)
con spazi e tilde **impedisce a Python di processare il file `.pth`
editable** generato da uv. Sintomo: `import colazione` da `python -c`
fallisce con ModuleNotFoundError. **Workaround**: `pythonpath = ["src"]`
in `[tool.pytest.ini_options]` per i test, `PYTHONPATH=src` per
script standalone. **In Docker/CI il problema non si presenta**
(nessuno spazio nel path).

### Stato

Sprint 0.1 completo. Backend skeleton committato, tutti i check
verdi.

### Prossimo step

Sprint 0.2: `frontend/` skeleton (React + Vite + TypeScript +
Tailwind + shadcn). Richiede installazione `pnpm` (suggerirò
`corepack enable` o `npm i -g pnpm`).

---

> Questo file viene aggiornato dopo **ogni modifica** al progetto.
> È il diario operativo del nuovo programma, costruito da zero.
>
> **Predecessore archiviato**: `docs/_archivio/LIVE-COLAZIONE-storico.md`
> contiene il diario del progetto vecchio (eliminato il 2026-04-25).
> Lì si trova la storia di come ci siamo arrivati al modello dati e
> all'architettura, in caso serva un riferimento.

---

## 2026-04-25 (9) — FASE C doc 7: PIANO-MVP.md (FASE C COMPLETA)

### Contesto

Ultimo documento architetturale. Definisce primo MVP girabile +
ordine costruzione + definizione "completato".

### Modifiche

**Nuovo `docs/PIANO-MVP.md` v0.1** (~430 righe):

**Definizione MVP v1**:
- Login + 5 dashboard navigabili (2 funzionanti su dati reali, 3
  scaffolding)
- Schema DB completo + seed Trenord
- Importer PdE da CLI (file Numbers reale)
- Vista corse + dashboard manutenzione

**Cosa NON e MVP**: builder giro, builder PdC, editor, persone,
revisioni, notifiche, mobile, deploy prod.

**8 sprint atomici** (1 commit per passo):
- Sprint 0 setup repo (1-2gg)
- Sprint 1 backend skeleton + Alembic + 31 tabelle (2-3gg)
- Sprint 2 auth JWT (2gg)
- Sprint 3 importer PdE Numbers (3-4gg, parser periodicita critico)
- Sprint 4 API base corse + depositi (2gg)
- Sprint 5 frontend skeleton React+shadcn (3-4gg)
- Sprint 6 dashboard MVP (2 reali + 3 scaffolding) (3-4gg)
- Sprint 7 test E2E + docs (1-2gg)

**Effort totale**: 17-23 gg lavorativi (3-4 settimane full time),
con buffer 30% = 22-30 gg reali (~5-6 settimane).

**12 criteri di "MVP completato"** verificabili.

**Roadmap v1.1-v1.7** post-MVP:
- v1.1 Builder giro materiale (Algoritmo A)
- v1.2 Editor giro (lettura)
- v1.3 Anagrafica persone
- v1.4 Builder turno PdC (Algoritmo B)
- v1.5 Editor scrittura (drag&drop)
- v1.6 Assegnazioni
- v1.7 Revisioni provvisorie (Algoritmo C)

**Decisioni rinviate** (non bloccanti MVP): file uploads, real-time
push, audit retention, backup, logging, hosting prod.

### Stato

**FASE C COMPLETATA**. Tutti i 7 documenti architetturali scritti:
1. ✅ VISIONE.md
2. ✅ STACK-TECNICO.md
3. ✅ RUOLI-E-DASHBOARD.md
4. ✅ LOGICA-COSTRUZIONE.md
5. ✅ SCHEMA-DATI-NATIVO.md
6. ✅ IMPORT-PDE.md
7. ✅ PIANO-MVP.md

Repo pronto per FASE D (codice).

### Prossimo step

Aspetto OK utente per iniziare FASE D Sprint 0 passo 0.1
(creare backend/ + pyproject.toml). Oppure utente chiede revisione
di qualche documento.

---

## 2026-04-25 (8) — FASE C doc 6: IMPORT-PDE.md

### Contesto

Specifica del primo importer del programma. Legge PdE Numbers/Excel
e popola corsa_commerciale + corsa_composizione. È il punto di ingresso
del sistema: senza questo, il resto della piramide non si popola.

### Modifiche

**Nuovo `docs/IMPORT-PDE.md` v0.1** (~470 righe):

- §1 Input: formati supportati (.numbers prio, .xlsx alt), 3 sheet
  Trenord (PdE RL = 10580 righe da importare; NOTE Treno e NOTE BUS
  per dopo)
- §2 Mapping completo 124 colonne PdE → schema DB:
  - identificativi (numero treno, rete, categoria, linea, direttrice)
  - geografia (origine/destinazione + CdS, orari, km, durate)
  - periodicità (testuale + flag garantito feriale/festivo)
  - 9 combinazioni stagione × giorno-tipo → corsa_composizione (95K
    record per Trenord)
  - calendario annuale (Gg_gen, Gg_feb, ..., Gg_anno)
  - aggregati (totale km, postikm, velocità commerciale)
- §3 **Algoritmo calcolo valido_in_date_json denormalizzato**:
  - parsing testo "Periodicità" (intervalli skip, date singole skip,
    date extra)
  - validazione incrociata con Gg_* per mese
  - retorna lista date ISO YYYY-MM-DD
- §4 Idempotenza:
  - chiave logica `(azienda_id, numero_treno, valido_da)` → upsert
  - SHA-256 file → skip se già importato
  - tracking corsa_import_run con n_create / n_update / warnings
- §5 Pseudo-codice top-level (transazione unica + bulk insert)
- §6 8 edge case noti (numero treno come float, date all'italiana,
  caratteri Unicode, sheet ordering, ecc.)
- §7 Performance: 10580 × 9 = 95K insert, target < 30s con bulk insert
  + transazione unica
- §8 Test (smoke + idempotenza + modifica + calcolo periodicità)
- §9 CLI: `uv run python -m colazione.importers.pde --file ... --azienda trenord`

### Stato

- Spec pronta per implementazione `backend/src/colazione/importers/pde.py`
- Anche pronta per la fixture di test (50 righe del file reale)

### Prossimo step

`docs/PIANO-MVP.md` (FASE C doc 7, ULTIMO): primo MVP girabile +
ordine costruzione codice + definizione "MVP completato". Dopo
questo, FASE C chiusa e si passa a FASE D (codice).

---

## 2026-04-25 (7) — FASE C doc 5: SCHEMA-DATI-NATIVO.md (DDL eseguibile)

### Contesto

Materializzazione di MODELLO-DATI v0.5 in DDL SQL eseguibile per
Postgres 16. Specifica per la prima migrazione Alembic
(0001_initial_schema.py).

### Modifiche

**Nuovo `docs/SCHEMA-DATI-NATIVO.md` v0.1** (~700 righe):

- §1 Convenzioni (naming, tipi, FK, indici)
- §2 Estensioni Postgres (pg_trgm)
- §3-§9 Schema in 7 strati con CREATE TABLE eseguibili:
  - Strato 0 anagrafica: azienda, stazione, materiale_tipo,
    localita_manutenzione, dotazione, depot, depot_linea_abilitata,
    depot_materiale_abilitato (8 tabelle)
  - Strato 1 corse LIV 1: corsa_commerciale, corsa_composizione,
    corsa_materiale_vuoto, corsa_import_run (4 tabelle)
  - Strato 2 giro LIV 2: giro_materiale, versione_base_giro,
    giro_finestra_validita, giro_giornata, giro_variante,
    giro_blocco (6 tabelle)
  - Strato 2bis revisioni: revisione_provvisoria,
    revisione_provvisoria_blocco, revisione_provvisoria_pdc (3 tabelle)
  - Strato 3 turno PdC LIV 3: turno_pdc, turno_pdc_giornata,
    turno_pdc_blocco (3 tabelle)
  - Strato 4 personale LIV 4: persona, assegnazione_giornata,
    indisponibilita_persona (3 tabelle)
  - Strato 5 auth/audit: app_user, app_user_ruolo, notifica,
    audit_log (4 tabelle)

Totale **31 tabelle**.

- §10 Indici secondari (FK, query frequenti, GIN su JSONB e trigram
  per cognome/nome persona)
- §11 5 vincoli consistenza come query SQL eseguibili (per test
  integrazione)
- §12 Seed iniziale Trenord:
  - 1 azienda Trenord con normativa_pdc_json completa
  - 7 localita_manutenzione (FIORENZA, NOVATE, CAMNAGO, LECCO,
    CREMONA, ISEO, POOL_TILO_SVIZZERA)
  - 25 depot Trenord (NORMATIVA §2.1)
- §13 Riepilogo numerico (record stimati: ~256k record totali in
  produzione Trenord)

### Stato

- DDL pronto per migrazione Alembic.
- 5 vincoli consistenza pronti per test integrazione.
- Seed Trenord pronti per popolamento iniziale.

### Prossimo step

`docs/IMPORT-PDE.md` (doc 6): come si legge PdE Numbers/Excel,
mapping colonne, calcolo valido_in_date denormalizzato, idempotenza.

---

## 2026-04-25 (6) — FASE C doc 4: LOGICA-COSTRUZIONE.md

### Contesto

Documento centrale degli algoritmi nativi. Tre algoritmi descritti in
modo formale + pseudo-codice + mapping a moduli Python.

### Modifiche

**Nuovo `docs/LOGICA-COSTRUZIONE.md` v0.1** (~600 righe):

**Algoritmo A — PdE → Giro Materiale**:
- Input: corse, localita_manutenzione, dotazione, giorno_tipo
- Greedy: per ogni località, costruisci catene di corse rispettando
  continuità geografica + tempo manovra + composizione coerente +
  ciclo chiuso
- Genera `corsa_materiale_vuoto` per posizionamento e rientro
- Multi-giornata + varianti calendario derivate da PdE periodicità

**Algoritmo B — Giro Materiale → Turno PdC**:
- Architettura "centrata sulla condotta" (riferimento ARCHITETTURA-
  BUILDER-V4 storico): seed produttivo (1-2 corse, 2-3h condotta) +
  posizionamento + gap handling + rientro
- 5 step: A scelta seed, B posizionamento, C gap (REFEZ in finestra),
  D rientro, E validazione
- Validazione vincoli singolo turno (NORMATIVA §11.8, §4.1, §9.2,
  §3, §6) + ciclo settimanale (§11.4, §11.5)

**Algoritmo C — Revisione provvisoria + cascading**:
- Crea `revisione_provvisoria` con causa esterna esplicita
- Modifica `giro_blocco` impattati (modifica/cancella/aggiungi)
- **Cascading**: per ogni giro modificato, crea
  `revisione_provvisoria_pdc` con stessa finestra
- Re-build automatico turni PdC nella finestra (Algoritmo B su giri-rev)
- Notifiche cross-ruolo
- Resolver query "cosa succede il giorno D?": base + override rev

**Validazione + scoring**:
- ValidatorePdC unificato in `domain/normativa/validator.py`
- Score per ranking soluzioni (n_pdc, prestazione_sotto_sfruttata,
  violazioni preferenziali §11.7)

**Mapping moduli Python**:
- `domain/builder_giro/`, `domain/builder_pdc/`, `domain/normativa/`,
  `domain/revisioni/` — tutti DB-agnostic
- Test puri in `tests/domain/`, fixtures con seed reali

**Edge case noti** (7 casi):
- Materiale pernotta fuori deposito
- Partenza senza U-numero
- CV Tirano (capolinea inversione)
- Cap 7h notturno
- MI.PG ↔ FIOz taxi obbligatorio
- Composizione mista
- POOL_TILO_SVIZZERA

### Stato

- Documento draft v0.1, ~600 righe.
- Pronto per implementazione (FASE D) ma 3 punti aperti:
  multi-giornata schema-tica, scoring seed con pesi placeholder,
  cascading re-build a maglie larghe.

### Prossimo step

`docs/SCHEMA-DATI-NATIVO.md` (FASE C doc 5): DDL SQL eseguibile.
Materializza `MODELLO-DATI.md` v0.5 in CREATE TABLE + indici + FK +
seed iniziali per Postgres 16.

---

## 2026-04-25 (5) — FASE C doc 3: RUOLI-E-DASHBOARD.md

### Contesto

Specifica dettagliata delle 5 dashboard per ruolo. Ogni ruolo ha
schermate, azioni, dati visualizzati, permessi. Documento operativo
per costruire frontend e backend coerenti.

### Modifiche

**Nuovo `docs/RUOLI-E-DASHBOARD.md` v0.1** (~530 righe):

- §1 Tabella riepilogativa 5 ruoli + ADMIN con privilegi
- §2 Schermate condivise (login, profilo, settings)
- §3 **Dashboard PIANIFICATORE_GIRO** (6 schermate):
  home, vista PdE, lista giri, editor giro (centrale, con Gantt
  orizzontale + drag&drop + valida live), revisioni, nuova revisione
- §4 **Dashboard PIANIFICATORE_PDC** (5 schermate):
  home, vista giri readonly, lista turni, editor turno PdC (centrale,
  Gantt giornaliero + validazione normativa live + pannello vincoli
  ciclo), revisioni cascading
- §5 **Dashboard MANUTENZIONE** (5 schermate):
  home, lista depositi, dettaglio deposito (inventario), spostamenti
  tra depositi, manutenzioni programmate
- §6 **Dashboard GESTIONE_PERSONALE** (6 schermate):
  home, anagrafica, scheda persona (calendario annuale + ore/sett),
  calendario assegnazioni (centrale, persone × date), indisponibilita,
  sostituzioni
- §7 **Dashboard PERSONALE_PDC** (5 schermate):
  oggi (banner + Gantt giornaliero), calendario, dettaglio turno data,
  ferie/assenze, segnalazioni
- §8 Matrix permessi cross-ruolo per 11 entita
- §9 Notifiche cross-ruolo (8 eventi tracciati)
- §10 Settings admin
- §11 Cosa NON e in v1 (dark mode, mobile native, PDF export ricco,
  WebSocket/SSE, drill-down KPI, conversazioni in-app)

### Stato

- Documento draft v0.1, ~30 schermate descritte.
- Pronto per priorizzazione in PIANO-MVP.md (doc 7).

### Prossimo step

`docs/LOGICA-COSTRUZIONE.md` (doc 4): algoritmo nativo PdE → giro
materiale → turno PdC. Riformula ALGORITMO-BUILDER.md + ARCHITETTURA-
BUILDER-V4.md in chiave nativa, senza riferimenti al codice vecchio.

---

## 2026-04-25 (4) — FASE C doc 2: STACK-TECNICO.md (scelte confermate)

### Contesto

Utente ha confermato in blocco le 6 scelte consigliate. Stack tecnico
definito.

### Modifiche

**Nuovo `docs/STACK-TECNICO.md` v1.0** (~390 righe):

Le 6 scelte:
1. Backend: **Python 3.12+**
2. Framework: **FastAPI** (async, OpenAPI auto-gen, Pydantic-native)
3. DB: **PostgreSQL 16+** (anche dev, no più SQLite-PG dual-mode)
4. Frontend: **React 18 + TypeScript + Vite**
5. UI Kit: **shadcn/ui** (Radix + Tailwind CSS)
6. Auth: **JWT custom + bcrypt**

Hosting differito (probabile VPS self-host quando arriva il momento).

**Struttura repo monorepo**:
- `backend/` (FastAPI con `src/colazione/` + `domain/` per business
  logic DB-agnostic)
- `frontend/` (Vite con routes per ruolo, non per tipo)
- `data/` (seed JSON gia presente)
- `docker-compose.yml` per dev (db + backend + frontend)
- Alembic per migrazioni schema versionate

**Tooling**:
- Backend: `uv` (package manager) + `ruff` (lint+format) + `mypy` + `pytest`
- Frontend: `pnpm` + `eslint` + `prettier` + `vitest` + `@testing-library/react`

**Convenzioni**:
- Python: type hints obbligatori, mypy strict, async ovunque
- React: function components, TanStack Query per stato server,
  Tailwind only (no CSS modules/styled-components)
- Commit: Conventional Commits in italiano

**Cosa NON useremo** (esplicito):
- Tauri (web-only per ora)
- GraphQL (REST sufficiente)
- Redis/Celery (non serve in MVP)
- Microservizi/k8s (monolite modulare)
- SSR/SSG (SPA classica)
- i18n (italiano-only)

### Stato

- Documento v1.0, completo per costruzione MVP.
- Modifiche future tracciate qui in TN-UPDATE.md.

### Prossimo step

`docs/RUOLI-E-DASHBOARD.md` (FASE C doc 3): dettaglio delle 5
dashboard, schermate per ruolo, azioni, permessi, mockup testuale.

---

## 2026-04-25 (3) — FASE C doc 1: VISIONE.md scritta

### Contesto

Primo documento architetturale del nuovo progetto. Scopo: chiarire
in modo permanente cosa stiamo costruendo, per chi, e perché. Punto
di riferimento per qualsiasi domanda di scope ("c'è dentro X?" → si
controlla qui).

### Modifiche

**Nuovo `docs/VISIONE.md` (draft v0.1)**:
- §1 Frase manifesto: sistema operativo per pianificazione
  ferroviaria nativa, dal contratto commerciale al singolo
  macchinista
- §2 Il problema reale: 3 silos disconnessi (PdE, turno materiale,
  turno PdC) cuciti con parser fragili
- §3 Cosa fa il programma: 4 funzioni primarie (importa PdE, genera
  giro, genera PdC, assegna persone) + 5a (revisioni provvisorie con
  cascading)
- §4 5 ruoli destinatari: pianificatore giro / pianificatore PdC /
  manutenzione / gestione personale / personale finale (PdC)
- §5 Cosa NON e': 6 esclusioni esplicite (no biglietteria, no real-
  time da zero, no manutenzione predittiva, no payroll, no RFI, no
  solo Trenord)
- §6 7 principi guida: costruzione non importazione, no parser
  fragili come ingresso primario, modello a piramide, multi-tenant
  giorno 1, 5 dashboard 1 modello, revisioni provvisorie tracciate,
  sviluppo iterativo
- §7 Definizione di successo (uomo davanti al monitor + scala
  industriale)
- §8 Ambito rilascio: MVP v1 → v1.0 → v1.x → v2.0 → v2.x (no date)
- §9 Riferimenti incrociati a documenti gia esistenti e in coda

### Stato

- Documento draft v0.1, ~250 righe.
- Pronto per revisione utente.

### Prossimo step

**MI FERMO QUI.** Il prossimo documento (`STACK-TECNICO.md`) richiede
decisioni dell'utente su:
- Linguaggio backend (Python? Node? Go? Rust?)
- Framework backend (FastAPI? Express? Fastify? altro?)
- Frontend (React? Vue? Svelte? Next/Remix?)
- DB primario (SQLite locale + Postgres prod come prima?)
- Hosting (Railway? Vercel? Fly.io? Cloudflare? self-host?)
- Auth (JWT? sessions? OAuth? Clerk/Auth0?)

Aspetto input dell'utente prima di scrivere STACK-TECNICO.md.

---

## 2026-04-25 (2) — FASE B completata: nuovo CLAUDE.md + .gitignore

### Contesto

CLAUDE.md vecchio era pieno di riferimenti al codice eliminato in
FASE A (server.py, FastAPI, Tauri, parser PDF, train_segment, builder
genetico, ecc.). Riscrittura completa per il nuovo progetto greenfield.

### Modifiche

**`CLAUDE.md`** completamente riscritto:
- Stato del progetto: greenfield, in scrittura specifiche
- 7 regole operative obbligatorie (lettura TN-UPDATE.md, aggiornamento
  TN-UPDATE.md dopo ogni task, METODO-DI-LAVORO.md, lettura dominio,
  manifesto greenfield, sviluppo per ruoli)
- Mappa dei documenti di dominio con "quando leggerli"
- Stato fasi A/B/C/D + lista 7 documenti FASE C
- Stack tecnologico: TBD in `docs/STACK-TECNICO.md` (FASE C doc 2)
- Glossario dominio essenziale (PdE, giro materiale, turno PdC, CV,
  PK, ACCp/ACCa, vettura, materiale vuoto, FR, S.COMP, ciclo 5+2)
- Convenzioni naming + riferimenti a tutti i .md

**`.gitignore`** aggiornato:
- Rimosse voci specifiche al vecchio (turni.db, server.log, uploads/
  hardcoded, ecc.)
- Aggiunte sezioni separate per Python e Node.js (entrambi ignorati
  finche non scegliamo lo stack)
- Strutturato per essere stack-agnostic e estendibile in FASE C

### Stato

- CLAUDE.md ora rispecchia il progetto attuale (greenfield)
- .gitignore agnostic per qualsiasi stack
- Repo pronto per FASE C (scrittura specifiche architetturali)

### Prossimo step

FASE C documento 1: `docs/VISIONE.md`. Cos'e' il programma, per chi,
cosa risolve, scope esplicito.

---

## 2026-04-25 — Greenfield reset (FASE A completata)

### Decisione

Il progetto vecchio (parser PDF Gantt centrato su `train_segment`,
backend FastAPI 60+ file Python, frontend React 1GB) è stato dichiarato
inutile dall'utente. Si parte da zero col nuovo programma nativo,
basato su:

- Logica di costruzione **PdE → giro materiale → turno PdC → personale**
- 5 dashboard separate per ruolo (pianificatori, manutenzione,
  gestione personale, personale finale)
- Modello dati a piramide v0.5 (vedi `docs/MODELLO-DATI.md`)
- Manifesto "non copiamo Trenord" — usano il loro sistema come
  ispirazione, non come template

### Cancellato in questo commit

| Categoria | Cosa | Motivo |
|-----------|------|--------|
| Backend | `server.py`, `app.py`, `api/` (18 file), `services/`, `src/` (1.2 MB di codice) | Logica vecchia centrata su parser PDF |
| Frontend | `frontend/` (~1 GB con node_modules), `static/`, `mockups/` | UI vecchia da riscrivere |
| Test | `tests/` (808 KB) | Test del codice vecchio |
| Dati runtime | `turni.db` (20 MB), `turni_backup_*.db`, `turno_materiale_treni.json`, `uploads/` (5.2 MB), `fr_stations.txt` | DB locale + dati vecchi |
| Config deploy | `Procfile`, `railway.toml`, `runtime.txt`, `.dockerignore`, `.railwayignore`, `requirements.txt`, `.env.example` | Deploy vecchio Railway |
| Script ad-hoc | `parse_turno_materiale.py`, `import_turno_materiale.py`, `debug_digits.py`, `scripts/enrich_db_*.py` | Tool 1-shot del vecchio |
| Junk | `nul`, `server.log`, `__pycache__/`, `.pytest_cache/`, `.venv/` | Cache + log |
| Config app | `config/` | Config app vecchia |

**Spazio liberato**: ~1.05 GB.

### Archiviato in `docs/_archivio/`

| Cosa | Motivo |
|------|--------|
| `LIVE-COLAZIONE-storico.md` (370 KB) | Memoria storica del progetto vecchio |
| `MIGRAZIONE-DATI.md` | Piano di migrazione DB (rinnegato — questo era progetto greenfield, non migrazione) |
| `GANTT-GUIDE.md`, `HANDOFF-*.md` (×5), `PROMPT-claude-design-*.md` (×5), `REFERENCE-*.css/.html` (×5), `PLAN-parser-refactor.md`, `claude-design-bundles/`, `stitch-mockups/` | UI vecchia (mockup, prompt, riferimenti) |
| `scripts/extract_depositi_manutenzione.py` | Utility 1-shot per estrarre depositi dal PDF (riutilizzabile se serve) |

### Tenuto (dominio + base nuovo progetto)

| Cosa | Motivo |
|------|--------|
| `docs/NORMATIVA-PDC.md` (1292 righe) | **Fonte verità** dominio Trenord |
| `docs/METODO-DI-LAVORO.md` | Framework comportamentale (vale sempre) |
| `docs/MODELLO-DATI.md` v0.5 | Modello concettuale (12 entità + manifesto) |
| `docs/ALGORITMO-BUILDER.md` | Spec algoritmo (riferimento, da riscrivere in chiave nativa) |
| `docs/ARCHITETTURA-BUILDER-V4.md` | Idea "centrata sulla condotta" (riferimento) |
| `docs/schema-pdc.md` | Schema dati turno PdC (riferimento) |
| `data/depositi_manutenzione_trenord_seed.json` | Anagrafica reale 7 depositi + 1884 pezzi |
| `CLAUDE.md` | Da **riscrivere** in FASE B per nuovo progetto |
| `.gitignore` | Da aggiornare per nuovo stack |
| `.claude/` | Config harness Claude Code |

### Stato repo dopo FASE A

```
COLAZIONE/
├── .claude/
├── .git/
├── .gitignore
├── CLAUDE.md                ← da riscrivere (FASE B)
├── TN-UPDATE.md             ← questo diario (nuovo)
├── data/
│   └── depositi_manutenzione_trenord_seed.json
└── docs/
    ├── ALGORITMO-BUILDER.md       ← riferimento
    ├── ARCHITETTURA-BUILDER-V4.md ← riferimento
    ├── METODO-DI-LAVORO.md        ← framework
    ├── MODELLO-DATI.md            ← v0.5
    ├── NORMATIVA-PDC.md           ← dominio
    ├── schema-pdc.md              ← riferimento
    └── _archivio/                 ← memoria progetto vecchio
```

### Prossimi step

- **FASE B**: riscrivere `CLAUDE.md` per il nuovo progetto
- **FASE C** (multi-commit): scrivere documentazione architetturale
  nativa, un documento per volta:
  1. `docs/VISIONE.md`
  2. `docs/STACK-TECNICO.md`
  3. `docs/RUOLI-E-DASHBOARD.md`
  4. `docs/LOGICA-COSTRUZIONE.md`
  5. `docs/SCHEMA-DATI-NATIVO.md`
  6. `docs/IMPORT-PDE.md`
  7. `docs/PIANO-MVP.md`
- **FASE D**: inizio costruzione codice (solo dopo che A+B+C sono
  chiusi e validati dall'utente)
