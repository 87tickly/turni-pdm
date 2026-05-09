# Critica SEVERO — Retrospettiva PIANO α Sprint 8.2

**Data**: 2026-05-10
**Commit / range**: `2d1a780..40b64f5` (5 MR + 1 hotfix migration)
**Entry TN-UPDATE**: 277, 279, 280, 281, 282, 283
**Motore usato**: AMILCARE (`mcp__amilcare__reason`) **NO** — 3 timeout
consecutivi (server saturo, pattern entry 248/270/278). Critica
prodotta in **fallback NINO puro**, voto **provvisorio asteriscato**,
**da rifare con AMILCARE operativo** (v. policy `.claude/agents/severo.md`
sezione "Modalità fallback"). Bias di auto-compiacenza inevitabile,
dichiarato esplicitamente.

## Sintesi

PIANO α chiude effettivamente §11.4/§11.5 e A1+A2+A3 della re-critica
MR-PD3, deploy prod SUCCESS, suite verde. Ma il prezzo: **1 regresso
architetturale netto** (facade strangler bypassato dai nuovi MR un
giorno dopo essere stato creato), **1 costante decorativa** (14h
dichiarata in `__all__` mai usata), **1 incidente migration in
prod** (revision ID duplicato → 502), **un campo registro
sovra-strict** (programma_id ignorato MVP). Voto **5/10*** provvisorio.

## Cosa funziona

- **Critica preventiva applicata**. SEVERO PIANO 3b (5/10) e SEVERO
  PIANO PD7b (3/10) sono stati **realmente** integrati: i finding S1
  (migration vs regex), S2 (cross-mezzanotte), S3 (chiave operatore),
  S4 (wild card MVP), S6 (rinomina), S7 (esclusi opt-in) sono nel
  codice. Lo split Z forzato dall'utente sul piano PD7b è stato
  rispettato (3 sub-MR PD7b-1/2/3) invece dello shortcut "validatore
  decorativo" che SEVERO aveva bocciato.
- **Programma context A2** pulito: `BuilderProgrammaContext` è una
  buona astrazione, factory async lineare, lifecycle per-request
  esplicito. La rinomina S6 (da `builder_programma.py` a
  `programma_context.py`) chiusa.
- **Cap HARD post-rientro** (`deposito_first.py:366-371`) implementato
  davvero come HARD — niente "annota e prosegui" del builder
  monolitico. Coerente con manifesto MR-PD3.
- **Documentazione inline**: i moduli nuovi hanno docstring lunghe
  che spiegano scelte conservative + rinvii a SEVERO finding.
  Onesto sulle limitazioni.
- **Hotfix migration 0046** lavorato bene una volta scoperto
  l'incidente (entry 283): rinomina chirurgica, no impatto su
  logica, verifica `alembic heads` post-fix.

## Cosa si poteva fare meglio

### S1 — Regresso facade strangler (MR-PD-FIX-SEVERO 2 distrutto da PD7b)

- **Severità**: HIGH-CRITICAL
- **Dove**:
  - `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:30`
  - `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:42`
- **Cosa**: i 2 nuovi moduli del piano α (entry 281 e 282) importano
  direttamente:
  ```python
  from colazione.domain.builder_pdc.builder import _GiornataPdcDraft
  ```
  bypassando il facade `giornata_base.py` (entry 273 = il giorno prima)
  che esporta `GiornataPdcDraft` (senza underscore) come API pubblica.
  Lo S2 di SEVERO MR-PD3 era stato chiuso APPOSITAMENTE per fermare
  questo pattern.
- **Perché è un problema**: il facade è la "porta stabile" del
  builder-base. Importare i simboli `_underscore` significa accedere
  a API privata: domani quando si farà il refactor di `builder.py`
  (S2-bis previsto), questi 2 moduli si rompono. La regola operativa
  dichiarata in `giornata_base.py:5-23` ("i simboli ESPORTATI da
  questo modulo costituiscono l'API stabile") è stata ignorata dai
  successivi MR del piano α nello stesso Sprint. Strangler pattern
  buchi appena creato.
- **Fix proposto**: 2 righe, sostituire negli import:
  ```python
  # riposo_intraturno.py:30 e riposo_settimanale.py:42
  from colazione.domain.builder_pdc.giornata_base import GiornataPdcDraft
  ```
  e rimpiazzare le occorrenze di `_GiornataPdcDraft` con
  `GiornataPdcDraft`.
- **Costo del fix**: <30 min (4 righe modificate + ruff/mypy verde).

### S2 — Costante decorativa: `RIPOSO_INTRATURNO_FINE_TARDA_MIN` mai usata

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_pdc/riposo_intraturno.py:43`
  + esportata in `__all__` riga 201.
- **Cosa**:
  ```python
  #: Riposo aumentato a 14h se la giornata precedente finisce tra 00:01 e 01:00.
  RIPOSO_INTRATURNO_FINE_TARDA_MIN: int = 14 * 60  # 14h
  ```
  Costante dichiarata con docstring + esportata in `__all__`. Ma
  `riposo_richiesto_min(fine_prestazione)` riga 82-92 collassa
  l'intera fascia [00:01-05:00] (hh<5) in `RIPOSO_INTRATURNO_NOTTURNO_MIN`
  (16h). La 14h non viene MAI restituita. Decisione interpretativa
  NINO documentata "più cautelativa = 16h sempre" (riga 71-73).
- **Perché è un problema**:
  1. **NORMATIVA-PDC §11.5 letterale**: dice 14h dopo fine
     [00:01-01:00] e 16h dopo notturna [00:01-05:00]. Trattare le
     14h come "sotto-caso del 16h cautelativo" è interpretazione
     unilaterale di NINO non concordata col domain expert (utente).
     Se la normativa dice 14h, sarà perché 14h sono sufficienti per
     fine 00:30 — costringere a 16h può forzare lo scarto di
     giornate altrimenti valide nel builder.
  2. **Costante esportata = false signaling**. Un consumatore esterno
     legge `__all__` e crede che 14h sia un cap usato. Non lo è.
  3. **Test del residuo §7 CLAUDE.md**: la decisione "16h cautelativo"
     è scrivibile in 5 minuti come distinzione 14h/16h se la
     conferma utente arrivasse ("uso letterale §11.5 vs cautelativo
     16h") — è chiaramente decisione di dominio non risolta.
     Pigrizia mascherata da "decisione conservativa NINO".
- **Fix proposto**: 2 strade:
  - (a) **Letterale**: `if 1 <= ma <= 60: return 14h; if 60 < ma < 300: return 16h`.
  - (b) **Cautelativo**: lasciare 16h sempre + **rimuovere costante
    morta** + togliere da `__all__`.
  La scelta è dell'utente (domain). Comunque sia, **non lasciare la
  costante decorativa**.
- **Costo del fix**: <30 min (decisione + 4 righe + 1 test
  parametrizzato).

### S3 — Migration revision ID duplicato (0046 = 0029) → deploy 502

- **Severità**: MEDIUM
- **Dove**: `backend/alembic/versions/0046_*.py` (originale entry 279
  + hotfix entry 283).
- **Cosa**: la revision ID `b7c8d9e0f1a2` di 0046 era IDENTICA a quella
  di 0029. Pattern revision ID nel repo:
  ```
  0033 = a1b2c3d4e5f6
  0034 = b2c3d4e5f6a1
  0046 = c8d9e0f1a2b3 (post-hotfix)
  ```
  Sequenze alfabetico-numeriche scelte a mano = collisione probabile
  con le 45 esistenti. **Nessun check pre-commit** verifica unicità.
  Effetto: alembic ciclo + container backend non parte + HTTP 502 +
  blocked retry e2e MR-D5h-bis e MR-D6.
- **Perché è un problema**:
  1. **Regola §5 METODO violata**: "verifica prima del commit". Per
     una migration, la verifica minima è `cd backend && alembic
     upgrade head` su DB locale. Non è stato fatto, o sarebbe stato
     trovato.
  2. **Pattern strutturale**: il fix entry 283 è chirurgico sul
     singolo ID, ma il problema è il workflow di scelta degli ID a
     mano. Ogni nuova migration può ricapitarci.
  3. **Impatto produzione reale**. Non è "edge case test che fallisce",
     è "deploy prod 502". L'utente l'ha visto.
- **Fix proposto**:
  - (a) **Pre-commit hook**: aggiungere a
    `.git/hooks/pre-commit` o equivalente CI un check:
    ```bash
    grep -h "^revision\s*[:=]" backend/alembic/versions/*.py \
      | sort | uniq -d \
      | (! grep -q . || (echo "DUPLICATE revision ID"; exit 1))
    ```
  - (b) **Standard naming**: usare `uuid.uuid4().hex[:12]` o
    `secrets.token_hex(6)` invece di scegliere a mano. Documentare
    in `backend/alembic/README.md`.
  - (c) **Sostituire alembic upgrade locale** come step obbligatorio
    pre-commit per ogni MR che tocca `versions/*.py`.
- **Costo del fix**: 1-2h (hook + doc + retrofit ad un round di
  commit).

### S4 — `RegistroVettureAssegnate.from_db` ignora `programma_id` MVP

- **Severità**: MEDIUM
- **Dove**: `backend/src/colazione/domain/builder_pdc/registro_vetture.py:138-214`
- **Cosa**: la factory MVP wild-card ha 2 limitazioni dichiarate ma
  non innocue in prod:
  1. `programma_id` parametro **ricevuto e loggato ma ignorato dal
     SELECT** (riga 186-191): query carica TUTTI i blocchi VETTURA
     con `numero_treno_vettura IS NOT NULL` di TUTTI i programmi del
     DB.
  2. `data_operativa = None` (riga 204) wild card che collide con
     QUALUNQUE data operativa.
- **Perché è un problema**: in prod oggi 0 turni `deposito_first`
  → 0 entries → 0 falsi positivi. Ma al primo run reale, se 26 turni
  `multi_turno_dp_alpha8` hanno blocchi VETTURA col `numero_treno_vettura`
  popolato (campo introdotto da 0046, ora popolato dal builder MVP =
  riga 162 `_inserisci_blocco_rientro`), il primo turno `deposito_first`
  per il NUOVO programma carica nel registro le vetture del VECCHIO
  programma. `numeri_da_escludere` ritornerà chiavi non pertinenti.
  Effetto: turni `deposito_first` futuri scarteranno candidate vettura
  legittime, sovra-iterando MM/VOCTAXI con falsa scarsità di vetture.
  Dichiarato come "sovra-strict ma sicuro" (riga 162) ma "sovra-strict"
  è un eufemismo per "produrrà falsi negativi sistematici nel primo
  programma multi".
- **Fix proposto**: 1 JOIN. Sostituire la query MVP con:
  ```python
  stmt = select(TurnoPdcBlocco.numero_treno_vettura).join(
      TurnoPdcGiornata
  ).join(TurnoPdc).where(
      TurnoPdcBlocco.tipo_evento == "VETTURA",
      TurnoPdcBlocco.numero_treno_vettura.is_not(None),
      TurnoPdc.programma_id == programma_id,  # ← filtro
  )
  ```
- **Costo del fix**: <1h (query + 2 test JOIN). Se serve aggiungere
  helper `enumera_date_giornata` per la `data_operativa` concreta è
  comunque MR successivo, ma il filtro programma è scrivibile ORA.

### S5 — Codice morto e silenziamento ruff (anti-pattern junior)

- **Severità**: LOW-MEDIUM
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:728`
- **Cosa**:
  ```python
  # Re-export per consistenza (consumatori non devono cercare in builder.py).
  _ = ACCESSORI_MIN_STANDARD  # silence unused-import warning per ruff
  ```
  Costante importata + assegnata a `_` per zittire ruff. Il commento
  dichiara "re-export per consistenza" ma `ACCESSORI_MIN_STANDARD`
  non è in `__all__` di `deposito_first.py` (riga 721-724).
- **Perché è un problema**: 3 cose:
  1. **Falso "re-export"**: senza essere in `__all__`, non è
     veramente re-esportato.
  2. **Pattern "silenzio il linter"**: anti-pattern manuale di
     primo Sprint. Se l'import non serve, si toglie.
  3. **Junior smell**: un senior o aggiunge in `__all__` (e quindi
     l'import HA scopo) o toglie. Mai zittire ruff con `_=`.
- **Fix proposto**:
  ```python
  # rimuovere riga 728 + togliere ACCESSORI_MIN_STANDARD dall'import
  # giornata_base se non usato altrove nel file.
  ```
- **Costo del fix**: <5 min (verifica con ruff post).

### S6 — Import locali dentro funzione (4 occorrenze)

- **Severità**: LOW-MEDIUM
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:595-608`
- **Cosa**: dentro `genera_turni_pdc_deposito_first`, 4 import locali:
  ```python
  from colazione.domain.builder_pdc.riposo_intraturno import (...)
  from colazione.domain.builder_pdc.riposo_settimanale import (...)
  from colazione.domain.calendario import festivita_italiane
  from colazione.models.programmi import ProgrammaMateriale
  ```
- **Perché è un problema**:
  1. **Convenzione Python rotta**: import top-level salvo motivi
     specifici (import circolare, dipendenza opzionale). Qui nessuno
     dei 4 ha quei motivi documentati.
  2. **Code smell di import circolare nascosto**: spesso si usa
     l'import locale per nascondere un import circolare *che esiste*.
     Vale la pena verificare se uno dei 4 moduli importa
     `deposito_first` (rapido `grep`).
  3. **Anti-pattern "stratigrafia rotta"**: una funzione di 240
     righe (`genera_turni_pdc_deposito_first`) con import inline
     fa schifo da leggere.
- **Fix proposto**: spostare i 4 import in cima al modulo. Se causa
  circolare → estrarre `_carica_festivita_programma()` helper privato
  in modulo separato.
- **Costo del fix**: <30 min (sposta + verifica suite).

### S7 — Zero test integration end-to-end del piano α

- **Severità**: MEDIUM
- **Dove**: `backend/tests/test_riposo_intraturno.py`,
  `test_riposo_settimanale.py`, `test_giornate_concrete.py`,
  `test_registro_vetture.py`.
- **Cosa**: +50 test aggiunti dal piano α, **TUTTI unit puri**. Lo
  smoke `test_genera_turno_pdc_deposito_first_smoke_ok`
  (`test_api_programmi_conferma.py:833`) è entry 271 (pre-piano-α),
  testa solo che l'endpoint risponda 201 con builder MVP MR-PD3.
  **Zero test verifica che**:
  - `BuilderProgrammaContext` venga **realmente** creato dall'orchestratore.
  - Il registro `from_db` venga popolato correttamente.
  - `calcola_e_valida_riposi_intraturno` sia chiamato nel path
    completo e popoli `riposo_min` nel DB.
  - `valida_riposo_settimanale` produca le violazioni attese
    salvate in `generation_metadata_json`.
- **Perché è un problema**: senza un test e2e, la prossima
  modifica all'orchestratore (es. refactor `genera_turni_pdc_deposito_first`)
  può rompere silenziosamente le 4 chiamate ai validatori +
  `crea_per_programma`, e la suite passerebbe lo stesso. La copertura
  unitaria è coperta, l'integrazione è scoperta.
- **Fix proposto**: 1 nuovo test e2e in
  `test_api_programmi_conferma.py` con seed più completo (programma
  con `ProgrammaMateriale` reale + 2-3 giornate con orari che fanno
  scattare §11.5 violazione + verifica via response che
  `riposo_intraturno_violazioni` sia presente). Costo: 2-3h (seed +
  fixture).
- **Costo del fix**: 2-3h.

### S8 — Validatore §11.4 perde info su settimane multiple violate

- **Severità**: MEDIUM
- **Dove**: `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py:200-202`
- **Cosa**:
  ```python
  if contatore >= GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO:
      violazioni.append(...)
      # Reset per evitare violazioni ripetute consecutive
      contatore = 0
  ```
  Il reset post-violazione **scarta informazione**. In ciclo 21gg con
  0 riposi settimanali → output = 1 sola violazione `no_in_7gg`
  invece di 3. Si capisce dal commento "evitare violazioni ripetute"
  che la scelta è intenzionale, ma è la scelta sbagliata.
- **Perché è un problema**: il pianificatore PdC vedrà nel turno
  21gg "1 violazione settimanale" e penserà sia un caso isolato. È
  invece una violazione strutturale catastrofica (3 settimane senza
  riposo = il turno è inutilizzabile). L'output del validatore deve
  raccontare la realtà, non sintetizzarla.
- **Fix proposto**: rimpiazzare con contatore non resettato + emettere
  N violazioni con indicazione "violazione N°i":
  ```python
  while contatore >= GIORNATE_CONSECUTIVE_MAX_SENZA_RIPOSO:
      violazioni.append(
          f"riposo_settimanale_no_in_7gg:settimana_{n_violazioni+1}:"
          f"a_G{d.numero_giornata}"
      )
      n_violazioni += 1
      contatore -= 7
  ```
  Oppure usare aggregato finale `riposo_settimanale_numero_insufficiente`
  (già presente riga 205-210) come singola voce + lasciar perdere la
  voce per-occorrenza.
- **Costo del fix**: <1h (riscrittura loop + 1 test parametrizzato).

### S9 — `enumera_date_giornata` fallback sovra-include su PdE Trenord reale

- **Severità**: MEDIUM
- **Dove**: `backend/src/colazione/domain/giornate_concrete.py:146-153`
  + chiamata in `riposo_settimanale.py:243-253`
- **Cosa**: il parser MVP riconosce solo varianti banali (`""`, `GG`,
  `LMXGV`, `LV`, `S`, `D`, `F`, `PF`). Per QUALSIASI testo non
  riconosciuto (es. `"LV 1:5 escl. 22/3"`, `"F escluso FpF"`, `"Si
  eff. 21-28/3"` — ovvero la maggioranza dei `validita_testo` reali
  Trenord, vedi memoria entry 7.7.5 "modello PDF Trenord 1134"),
  fallback **sovra-include** = ritorna tutte le candidate del ciclo.
- **Perché è un problema**: in prod su PdE Trenord 2026 (54 turni di
  cui molti con varianti complesse) probabile che %
  >50% delle giornate cadano in fallback. Effetto sul §11.4
  `valida_riposo_settimanale`:
  - `_conta_giorni_solari_per_riposo` riceve sempre la **prima**
    candidata di una lista sovra-inclusa → la `data_pre_first` può
    essere lontana settimane dalla data reale.
  - Il `gap_min` resta corretto, ma il `start_dt` è arbitrario.
  - **Nessuna evidenza** che questo produca falsi positivi/negativi
    per §11.4, ma neanche che sia OK. Comportamento documentato come
    "sovra-strict conservativo" — può generare violazioni false
    positive sistematiche su ogni turno reale, mascherando le vere.
- **Fix proposto**: 2 strade combinate:
  - (a) **Telemetria**: log INFO ogni volta che si entra nel
    fallback con il `validita_testo` originale, per misurare il %
    sui turni reali Trenord.
  - (b) **Estensione parser DSL**: scope MR-PD7c (ma da pianificare
    SUBITO, non rimandare). Pattern `LV 1:5`, `escl. DD/MM`, `eff.
    DD-DD/MM`, `F escluso FpF` sono finiti — 5-10 regex.
- **Costo del fix**: (a) <30 min, (b) 1-2 giorni a sé (MR-PD7c).

### S10 — Pattern doppio `cache_eff/registro_eff` per backward compat

- **Severità**: LOW
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py:272-273`
- **Cosa**:
  ```python
  cache_eff = context.cache if context is not None else cache
  registro_eff = context.registro if context is not None else None
  ```
  Funzione accetta sia `cache=` che `context=` con override. Doppia
  signature mantiene backward compat con MVP MR-PD3 ma:
- **Perché è un problema**: doppia signature = doppio path da testare.
  Test `test_api_programmi_conferma.py` non chiama mai
  `costruisci_giornata_deposito_first` direttamente — la chiama
  l'orchestratore con `context=...`. Path "cache solo, no context"
  non è coperto. Il commento dichiara "Permette di chiamare la
  funzione sia in modalità vecchio MVP sia in modalità endpoint
  MR-PD5" — ma l'API consumatore è UN solo orchestratore.
  La duplicazione signature è morta in pratica.
- **Fix proposto**: `context` obbligatorio (non `| None`). Eliminare
  parametro `cache=`. 1 commit di cleanup.
- **Costo del fix**: <30 min (signature change + test update).

## Debito tecnico segnalato

NINO ha lasciato 4 residui dichiarati nei commit messages. Verifica
test del residuo §7 CLAUDE.md per ognuno:

1. **Helper `enumera_date_giornata` parser DSL Trenord limitato**
   (commit `b671727` entry 280, "Limitazione 1"): scope MR-PD7c.
   ✅ **Legittimo**: parser DSL è 5-10 regex + set di test = MR a sé,
   non scrivibile in <2h pulitamente. Però va aperto SUBITO come
   ticket, non aspettare prossimo Sprint. Vedi S9.

2. **`from_db` filtra programma_id ignorato MVP** (commit `2d83528`
   entry 279, "Limitazione 2"): scope MR-PD7+. ❌ **Pigrizia
   mascherata**: il fix è 1 JOIN + 2 test = <1h. Vedi S4. Test del
   residuo §7: scrivibile ora in <2h → CHIUDILO.

3. **Wrap-around ultima giornata stima conservativa gap+24h**
   (commit `b9780ff` entry 281, "Limitazione 1"): "raffinamento in
   MR-PD7b-3". ✅ **Chiuso parzialmente** (PD7b-3 ha aggiunto
   `_giorni_solari_interi_in_finestra` e calcolo concreto), ma il
   `riposo_min_post` dell'ultima giornata in `riposo_intraturno.py:194-195`
   resta `gap_singola_notte + 24*60` (placeholder). Non è stato
   rifattorizzato. ❌ **Pigrizia mascherata**, "MR-PD7b-3" doveva
   sostituirlo, non l'ha fatto.

4. **Solo path deposito_first integrato; multi_turno legacy non**
   (commit `b9780ff` entry 281, "Limitazione 2"): scope MR-PD7+.
   ✅ **Legittimo**: integrazione su `multi_turno.py` (DP, multi-turno)
   richiede ripensare come iterare le giornate dei segmenti. Migration
   architetturale grossa, MR a sé.

## Aderenza al METODO-DI-LAVORO

Le 7 regole, valutazione sui MR del piano α:

1. **R1 Diagnosi prima di azione**: ⚠️ **PARZIALE**. Per i validatori
   §11.4/§11.5 sì (decisione conservativa "16h sempre" è UNA
   diagnosi, anche se discutibile vedi S2). Per la migration 0046,
   no — l'incidente revision ID dimostra che non c'è stato `alembic
   upgrade head` locale prima del commit.

2. **R2 Numeri non ipotesi**: ✅ rispettato sui validatori (test
   parametrici con minuti calcolati, no "circa 11h"). ⚠️ Sul
   `_conta_giorni_solari_per_riposo` quando `use_date_concrete=False`
   (`gap_min // (24*60)`) è una **formula proxy stimata**, non
   numero reale. Documentato come "sotto-stima" → onesto. OK.

3. **R3 Un passo alla volta**: ✅ rispettato grazie allo split Z
   forzato dall'utente in 3 sub-MR (PD7b-1/2/3). Senza Z, sarebbe
   stato 1 MR monolitico — Z ha pagato.

4. **R4 Ammettere l'errore**: ✅ entry 283 hotfix migration
   onestamente dichiara "Bug introdotto da altra sessione (entry
   277), scoperto durante deploy MR-D6". A3 (entry 277) ammette
   "AMILCARE falso positivo per grep solo su 2 moduli MR" — onestà
   meta sui finding ausili.

5. **R5 Verifica prima del commit**: ❌ **VIOLATA su migration
   0046**. `alembic upgrade head` locale + `alembic heads` avrebbero
   trovato il duplicato in 30 secondi. La verifica era saltata. È
   esattamente il caso che la critica preventiva 3b doveva
   intercettare e non ha fatto.

6. **R6 Preservare non distruggere**: ⚠️ il facade `giornata_base.py`
   è stato distrutto SEMANTICAMENTE (S1). I 2 nuovi MR PD7b non
   l'hanno usato. Questo è "distruzione passiva" del lavoro entry 273.

7. **R7 Costanza nel tempo**: N/A.

## Voto complessivo

**5/10*** provvisorio (fallback NINO puro, AMILCARE 3 timeout).

Motivazione in 1 riga: piano α chiude obiettivi funzionali ma con
1 regresso architetturale (S1) + 1 costante decorativa (S2) + 1
incidente prod (S3) + 1 sovra-strict in agguato (S4). I 4 finding
HIGH-CRITICAL sono tutti scrivibili in <2h ciascuno = pigrizia
mascherata, non scope-cutting legittimo.

Scala: 5-6 = funziona ma con debito o blind spot non secondari.
Provvisorio: con AMILCARE operativo il voto può oscillare 4-6
(bias auto-compiacenza NINO ammesso).

## Cosa NON ho controllato

- **AMILCARE non ha potuto giudicare**. 3 timeout consecutivi
  (server saturo). Critica fatta in fallback NINO con bias
  auto-compiacenza inevitabile. **Da rifare con AMILCARE operativo**
  appena disponibile (riposare 30-60 min poi retry). Pattern entry 248:
  voto fallback NINO 6/10 → con AMILCARE 4/10 sullo stesso MR.
- **Test runtime non eseguiti**. Non ho lanciato `pytest backend/tests/test_riposo_intraturno.py`
  per verificare i 18 test. Mi fido del commit message "18 passed".
- **Deploy verifica**. Non ho controllato `railway logs --service backend`
  post-deploy SUCCESS dichiarato in entry 283. Mi fido del fatto che
  l'utente abbia visto verde.
- **Coverage cross-modulo dei test**. Non ho misurato copertura
  effettiva dei nuovi moduli (gli unit test sì, ma quanta parte di
  `costruisci_giornata_deposito_first` con `context=...` è coperta?).
- **Performance del registro `from_db`**. Caricare TUTTE le vetture
  del DB (S4) è lineare nel numero di blocchi VETTURA = al momento
  trascurabile, ma non misurato.
- **TILO/operatore matching**. Decisione "operatore=None nel registro
  per compatibilità retro" (`registro_vetture.py:198-204`) non
  verificata contro un dataset reale TILO.

---

## Tracciabilità

- Brief AMILCARE: target 1.5-3KB, 3 retry: ~3KB → ~2KB → ~1KB. Tutti
  e 3 timeout `MCP error -32001`. Pattern entry 248/270/278: server
  saturo periodo.
- Modalità fallback dichiarata + voto asteriscato come da policy
  `.claude/agents/severo.md` "Modalità fallback".
- Dichiarato esplicitamente "da rifare con AMILCARE operativo".
- Bias auto-compiacenza ammesso in "Cosa NON ho controllato".
