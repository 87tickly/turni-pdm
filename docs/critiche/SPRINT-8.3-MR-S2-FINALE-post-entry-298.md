# Critica SEVERO — Sprint 8.3 MR-S2 FINALE post entry 298 (retro 2)

**Data**: 2026-05-10
**Commit / range**: `b1ef309` (entry 298, +152/-19, 5 file: TN-UPDATE.md
+ durata_vuoto.py docstring + test_aggregazione_linea_centrica.py + 2
file critica retro 1)
**Entry TN-UPDATE**: 298 (chiude 3/4 HIGH retro 1 entry 297, post
SEVERO retro 1 voto 6/10\* fallback V4 Flash)
**Motore usato**: AMILCARE V4 Flash (`mcp__amilcare__code`,
DeepSeek-V3 chat) — **8° critica consecutiva senza V4 Pro** (pattern
entry 248 cronico: 7 timeout precedenti + V4 Pro `reason` timeout `-32001`
in questa sessione + V4 Flash `code` timeout 1° + 2° tentativo, riuscita
al 3° con brief ~1.5KB). Output V4 Flash filtrato per 4 falsi positivi
tecnici verificati: F1 voto 7/10 troppo generoso vs analisi indipendente
(adottato 6/10\*); F2 "S2 esatto accettabile" parzialmente vero
(riformulato come MED retro-1-residuo, vedi finding R1); F3 "S6 file
.github/workflows/ci.yml + .pre-commit-config.yaml" falso positivo
(verificato `ls`: workflow è `backend-ci.yml`, `.pre-commit-config.yaml`
NON esiste); F4 "S5 fix 15 min, S6 fix 20 min" stima al ribasso
(verificato `wc -l severo.md = 436 righe`, R-PROC-7 in formato canonico
è 30-45 min onesti). Voto provvisorio asterisco perché V4 Pro non
disponibile per benchmark (margine atteso ~0.5-1 punto).

---

## Sintesi (3 righe max)

Entry 298 chiude 3/4 HIGH retro 1 in **60 min totali** (sotto soglia
<2h) con disciplina: smoke prod read-only su DB Railway prog 17 ha
INVALIDATO empiricamente l'ipotesi qualitativa S1 (TIRANO=152 reale,
NON 60-80 ipotizzato), 4 test fixati con pattern `durata_min` calcolato.
**MA: S4 HIGH (R-PROC-7 file `severo.md`) rinviato come "scope diverso"
quando è scrivibile in 30-45 min** — pigrizia §7 mascherata, non
scope-cutting onesto. **Inoltre 3 finding retro 1 (S5 MED, S6 MED,
S7 LOW) sono interamente ignorati senza menzione**. R-PROC-1 cap chiuso
solo al 70% (read-only ≠ end-to-end runtime). Voto **6/10\*** confermato
(retro 1) — **delta zero**: la velocità è reale ma la copertura è
parziale e i residui retro 1 ricorrenti.

---

## Cosa funziona

- **Smoke prod read-only su DB Railway prog 17 effettivamente eseguito**
  (chiude S3 HIGH retro 1 al 70%, R-PROC-4 livello 2). Entry 298
  riporta dati empirici concreti: 326 coppie distinte, 102 stazioni
  baseline, distribuzione mediana 69 min, scenario canonico
  TIRANO→CERTOSA validato (baseline TIRANO=152, CERTOSA=73, fallback
  geometrico=152 vs 60 hardcoded pre-MR-S2 → +92 min realistici). È
  esattamente la verifica DB-first livello 2 che SEVERO retro 1
  contestava ("non hai eseguito query SQL diretta"). **+1 punto
  sostanziale rispetto a retro 1**.
- **S1 HIGH ipotizzato INVALIDATO empiricamente con onestà
  intellettuale**. SEVERO retro 1 aveva costruito ipotesi qualitativa
  "baseline TIRANO ~60-80 skewed da corse brevi infradirettrice"
  basata su memoria progetto (`project_etr425_526_solo_diretti` 130
  diretti su 252). Smoke prod ha mostrato il contrario: 152 min reali
  (long-haul Mi.Cle-Tirano dominante). NINO ha riconosciuto pubblicamente
  il falso positivo SEVERO retro 1 nel TN-UPDATE entry 298 e nel commit
  message — questo è METODO §4 (ammettere l'errore, anche del critico).
  Pattern positivo che va segnato.
- **Docstring `calcola_durata_vuoto_min` aggiornata onestamente**
  (`durata_vuoto.py:165-184`): esempi numerici reali dal smoke
  (TIRANO=152, CERTOSA=73, durata=152) + limite onesto dichiarato
  ("per stazioni con attività dominata da tratte brevi intra-direttrice
  TILO/Malpensa Express, baseline meno predittiva, scope MR-D7
  raffinerà"). Pattern S1 retro 1 opzione (d) "documentazione onesta"
  effettivamente adottato. ✅
- **4 test fixati con pattern robusto a refactor cross-mezzanotte**
  (`test_aggregazione_linea_centrica.py:733-852`). Il calcolo
  `(arrivo.h*60+m) - (partenza.h*60+m)` è semanticamente equivalente
  alla durata, immune a future modifiche di arrotondamento o timezone.
  Questo è meglio dell'`ora_arrivo == _time(X, Y)` esatto pre-fix —
  è un fix sostanziale, anche se non letteralmente "range ±5min" come
  retro 1 raccomandava (vedi finding R1 sotto).
- **+1 perché chiusura veloce: 60 min totali (30 smoke + 20 test +
  10 docstring) sotto target retro 1 <2h**. Disciplina di esecuzione
  riconosciuta. Pattern §3 METODO ("un passo alla volta") ben applicato.
- **Onestà nel dichiarare cosa NON è stato fatto**. TN-UPDATE entry 298
  sezione "Cosa NON è stato fatto in questo MR" elenca esplicitamente:
  S4 HIGH R-PROC-7 rinviato, integration test session.rollback() pipeline
  reale, cambio builder_mode prog 17. Onestà dichiarativa preservata.
- **Read-only safety pattern adottato correttamente**. Smoke prod via
  `DATABASE_PUBLIC_URL` proxy + `session.rollback()` finale + 0
  modifiche DB + 0 toccate su 22 giri esistenti. Pattern conservativo
  appropriato per un primo smoke prod su database condiviso. R-PROC-1
  parzialmente onorata (70% del cap, vedi finding S2 sotto).

---

## Cosa rimane aperto / nuovi finding

### S1 — R-PROC-1 cap chiuso solo al 70%: smoke read-only ≠ verifica e2e runtime

- **Severità**: HIGH (BLOCCANTE per cap voto >7)
- **Dove**: TN-UPDATE entry 298 sezione "Cosa NON è stato fatto" +
  `builder.py:1681` (path produzione `_genera_giri_linea_centrica` con
  nuovo try/except + chiamata `costruisci_lookup_durate`)
- **Cosa**: lo smoke read-only chiama `costruisci_lookup_durate` in
  isolamento + rollback. Valida che la query DB ritorna dati e che i
  due dict (`durata_per_coppia`, `baseline_per_stazione`) sono popolati
  correttamente. **NON valida**:
  - Il try/except difensivo riga 1681 in produzione (= se la query DB
    fallisce, il warning è loggato e i dict sono vuoti silenziosamente
    → builder ricade su fallback 60 senza che nessuno se ne accorga).
  - L'iniezione effettiva dei dict in `ParamPipelineLineaCentrica` →
    `traduci_turno_in_giro` → `_costruisci_catena_posizionata` →
    `calcola_durata_vuoto_min` runtime end-to-end.
  - Persistenza dei giri G-FIO post-MR-S2 (= se il calcolo è 152 vs
    60, le `ora_partenza_vuoto` dei blocchi `sosta_disponibile` saranno
    coerentemente diverse).
  - Performance impact (1 query DB extra in path produzione, prog 17
    ha 6536 corse — costo aggiuntivo 100-300ms attesi non misurato).
- **Perché è un problema**: R-PROC-1 (`severo.md:173-198`) impone
  *"verifica e2e empirica al primo cambio strangler"*. La definizione
  di "e2e" non è "lookup DB read-only", è "esecuzione del builder
  reale su prog 17 con `costruisci_lookup_durate` chiamato dentro
  `_genera_giri_linea_centrica`, persistenza dei giri verificata,
  zero warning silenziati". Lo smoke read-only è **stress-test del
  helper isolato**, non del path produzione. È **70% del cap** —
  meglio di 0%, ma non chiude R-PROC-1 al 100%. Pattern entry 270
  (KO operativo single-sede dopo "8/10 mock-only") è esattamente la
  classe di problema che R-PROC-1 vuole prevenire: smoke isolato non
  rivela bug di integrazione.
- **Fix proposto**: lanciare `POST /programmi/17/build?modalita=esplorativo`
  con `builder_mode=linea_centrica` + DEBUG_LOG attivo + verificare:
  - `costruisci_lookup_durate` chiamato (log line presente)
  - `len(durata_per_coppia) > 0` post-chiamata
  - 0 warnings nuovi tipo "Costruzione lookup durate vuoto fallita"
  - 22 giri persistiti come pre-MR-S2 (no regressione conteggio)
  - 1 giro G-FIO con `vuoto_coda.durata_min > 60` (= fallback geometrico
    attivo per coppie distanti, validazione delta operativo +92 min)
  Costo: 30-45 min (lancio API + screenshot + entry TN-UPDATE).
  Alternativa: dichiarare onestamente che R-PROC-1 è chiusa solo al
  70% in entry 298 (NINO non l'ha fatto, claim è "S3 chiuso").

### S2 — S4 HIGH R-PROC-7 rinviato come "scope diverso" è scope-cutting silente §7 — NON onesto

- **Severità**: HIGH
- **Dove**: TN-UPDATE entry 298 sezione "Cosa NON è stato fatto in
  questo MR" punto 1: *"S4 HIGH proposta R-PROC-7 [...] scope diverso
  (modifica `.claude/agents/severo.md`), può essere formalizzata in
  MR cleanup futuro"*
- **Cosa**: il file `.claude/agents/severo.md` (verificato `wc -l =
  436 righe`) ha già 3 R-PROC formalizzate in formato canonico (R-PROC-1
  riga 173, R-PROC-2 riga 199, R-PROC-3 riga 217). Aggiungere R-PROC-7
  segue lo stesso template:
  - Titolo + paragrafo origine
  - "Regola" + esempio storico
  - "Cap voto" + "Quando applicarla"
  Costo realistico: **30-45 min onesti** (15 min copy-paste struttura
  + 15-30 min ragionamento sul wording specifico). NON è "scope diverso"
  — è esattamente lo stesso tipo di scope di una modifica `severo.md`
  qualunque (NINO ha modificato `severo.md` infinite volte in passato,
  vedi entry 270, 285).
- **Perché è un problema**: regola §7 NIENTE PIGRIZIA del CLAUDE.md è
  esplicita: *"prima di marcarlo aperto in TN-UPDATE/commit, mi chiedo:
  1. Il fix è scrivibile ora in <2h? Se sì → CHIUDILO"*. R-PROC-7
  rinviata risponde §7-test 1 con "sì, ma scope diverso". **"Scope
  diverso" non è una giustificazione oggettiva**: è scope-cutting
  silente travestito da decisione architetturale. Pattern §7 ricorrente:
  vedi storia retro 1 finding S6 ("CI vs pre-commit framework separato"),
  retro 1 finding S3 ("smoke prod separato"), entry 285 piano §11.4-§11.5
  ("prerequisito separato"). **3° volta consecutiva in 2 mesi** che
  NINO usa "scope diverso" come escape valve per fix scrivibili in
  <2h. R-PROC-7 sarebbe stata una vittoria simbolica chiusa anche se
  il valore aggiunto è meta-processo, non runtime.
- **Fix proposto**: aggiungere R-PROC-7 in `severo.md` ora (30-45 min)
  con format canonico + esempio storico (entry 287 falso `ls`). Oppure,
  se davvero rinviato, dichiarare in TN-UPDATE: *"S4 HIGH rinviato
  per [motivazione oggettiva specifica], scope cleanup MR-X dichiarato
  con data/Sprint preciso"* invece del generico "MR cleanup futuro".
- **Costo del fix**: 30-45 min (chiusura immediata) o 5 min
  (dichiarazione onesta del residuo con SLA).

### S3 — 3 finding retro 1 (S5 MED, S6 MED, S7 LOW) silenziati senza menzione

- **Severità**: HIGH
- **Dove**: TN-UPDATE entry 298 + commit message `b1ef309`. Ricevuti
  in retro 1 (`SPRINT-8.3-MR-S2-MR-S6-codice-committato.md` finding
  S5/S6/S7), MAI menzionati in entry 298.
  - **S5 MED** (retro 1) — `aggregazione_linea_centrica.py:359-378`
    zombie placeholder `durata_min_vuoto = DURATA_VUOTO_DEFAULT_MIN`
    quando `aggiungi_vuoto is None`. **Verificato presente ancora oggi**
    (`grep aggiungi_vuoto aggregazione_linea_centrica.py` riga 363-371,
    pattern identico al diff retro 1).
  - **S6 MED** (retro 1) — CI step vs pre-commit framework. Stato
    invariato: `.github/workflows/backend-ci.yml` esiste, ma
    `.pre-commit-config.yaml` NON esiste (verificato `ls .pre-commit-config.yaml
    → No such file or directory`). Finding chiuso al 70% in entry
    296, residuo 30% mai dichiarato in entry 298.
  - **S7 LOW** (retro 1) — Side-fix S1 docstring sync mescolato in
    commit MR-S2. Pattern lesson learned, mai riscritto in TN-UPDATE
    come monito futuro.
- **Cosa**: entry 298 risponde a 4/7 finding retro 1 (S1+S2+S3 HIGH +
  riconoscimento S4) ma ignora i 3 retro 1 di livello inferiore (S5
  MED + S6 MED + S7 LOW). Né li chiude né li dichiara aperti — sono
  invisibili nel diario. Pattern §7 "chiudo l'80% del finding e lascio
  il 20% strutturale" identificato in retro 1 conclusione: **ricorrenza
  confermata** in entry 298. NINO si è concentrato sui finding HIGH
  più visibili e ha lasciato cadere 3 finding di livello inferiore
  che erano ALL FIX rapidi (S5 = 15-20 min, S6 = 0-5 min dichiarazione
  parziale, S7 = 0 min lesson learned).
- **Perché è un problema**: pattern ricorrente di "selective response"
  nelle critiche. SEVERO retro 1 ha identificato 7 finding totali
  (4 HIGH + 2 MED + 1 LOW) — entry 298 ne chiude 3, lascia 4 senza
  risposta esplicita. Test del residuo §7: ognuno dei 3 ignorati è
  scrivibile in <30 min (S5 fix più costoso, ~15-20 min). **Tutti e 3
  passano §7-test 1 ("scrivibile in <2h? sì → CHIUDILO")**. Inoltre
  il pattern segnala bias di NINO: rispondere ai finding HIGH per
  "muoversi velocemente verso voto ≥7" e lasciare cadere i lower-priority.
- **Fix proposto**: in TN-UPDATE entry 298 (o entry follow-up) aggiungere
  sezione "Risposta finding retro 1 livello MED/LOW":
  - S5 MED: chiusura (15-20 min) o dichiarazione "rinviato a MR-Z
    con SLA Sprint 8.4"
  - S6 MED: dichiarazione esplicita "chiuso al 70%, residuo pre-commit
    framework con SLA Sprint X"
  - S7 LOW: lesson learned scritta in `docs/AUSILI-CODICE.md` o
    sezione meta-processo
- **Costo del fix**: 30-45 min totali (S5 reale fix + S6/S7 dichiarazioni).

### S4 — Verifiche entry 298 sono mirate, NON full project (claim "tutto verde" implicito)

- **Severità**: MEDIUM
- **Dove**: commit message `b1ef309` sezione "Verifiche":
  - `pytest tests/test_aggregazione_linea_centrica.py
    tests/test_durata_vuoto.py: 58 passed`
  - `mypy --strict durata_vuoto.py: clean`
  - `ruff check su file modificati: clean`
- **Cosa**: il backend ha 600+ test in `backend/tests/` (verificato
  storicamente in retro 1 commenti su CI). Entry 298 ha eseguito SOLO
  i 58 test mirati ai 2 file modificati. Mypy --strict solo su 1 file
  (`durata_vuoto.py`), NON sull'intero progetto. Ruff "su file
  modificati", NON full project. **Le modifiche entry 298 toccano
  solo docstring + test, quindi il rischio reale è basso** — MA il
  claim implicito "tutto verde" è incompleto. Una rotture in altri
  test che importano `durata_vuoto` o `test_aggregazione_linea_centrica`
  (verifica dependencies) NON sarebbe catturata da questi 3 comandi.
- **Perché è un problema**: METODO §5 ("verifica prima del commit").
  La definizione di "verifica" è "ho fatto girare il full suite e
  ho controllato che non ci siano regressioni", non "ho fatto girare
  i test che ho appena scritto". Pattern critica entry 270, 285:
  smoke isolato non equivale a regression check. Per entry 298
  specificamente il rischio è basso (modifiche chirurgiche), ma il
  claim è generico. Per la prossima volta che NINO modifica codice
  runtime non test-only, lo stesso pattern produrrà falsi negativi.
- **Fix proposto**: aggiungere step `pytest backend/tests/ -x` (full
  suite) + `mypy backend/src` (full strict) + `ruff check backend/`
  (full project) come baseline minima nella sezione "Verifiche" di
  ogni TN-UPDATE entry. Costo: 5 min/entry (i test girano in <30s
  totali per il backend pure-domain).
- **Costo del fix**: 5-10 min (lancio comandi + entry) per la prossima
  volta. Pattern lesson learned.

### R1 — Pattern S2 fix "esatto" vs raccomandazione U piano "range ±5min" — pattern letterale non rispettato

- **Severità**: LOW (residuo retro 1 ridotto da HIGH)
- **Dove**: `test_aggregazione_linea_centrica.py:749, 778, 818, 850`
  (4 test fixati): `assert durata_min == 85`, `== 70`, `== 150`, `== 60`
- **Cosa**: SEVERO retro 1 finding S2 raccomandava letteralmente
  *"trasformare i 4 assert in `assert _time(17, 20) <=
  cat_pos.vuoto_coda.ora_arrivo <= _time(17, 30)` (margine ±5min)
  oppure `assert (durata_min_calcolata - durata_attesa) < 5` per
  durate"*. Entry 298 ha adottato **opzione (a) parziale**: calcolato
  `durata_min` da orari (= robusto a refactor cross-mezzanotte ✅) ma
  asserito `== 85` esatto invece di `<= 5 differenza`. Il pattern è
  semanticamente equivalente (durata calcolata è deterministica per
  test in-memory) ma NON letterale alla raccomandazione.
- **Perché è un problema**: livello LOW, non HIGH. Il rischio reale
  è marginale: la durata in test in-memory è deterministica, non
  fluttua. Range ±5min era difesa contro futuri refactor di
  arrotondamento — assertion esatta `== 85` saltarebbe se MR-D7
  introduce arrotondamento round-up dei min_tratta. Ma il rischio
  è probabilistico, non immediato. Vedi pattern entry 248: il claim
  "U adottata" del commit MR-S2 originale era falso (4/5 test exact).
  Entry 298 fix risolve il problema sostanziale (assert su durata,
  non ora_arrivo) MA non chiude la lettera della raccomandazione.
- **Fix proposto**: trasformare i 4 assert in `assert abs(durata_min -
  85) <= 5` (margine ±5min). Costo: 5 min totali (4 sostituzioni 1 a
  1). Oppure dichiarare onestamente "U adottata in spirito (durata
  calcolata) ma non in lettera (esatto vs range), accettato perché
  test in-memory deterministico".
- **Costo del fix**: 5 min letteralmente, oppure 0 min con dichiarazione
  onesta ex-post.

---

## Risposta puntuale alle 6 domande NINO

### 1. S3 chiusura via smoke prod read-only è sufficiente per R-PROC-1?

**No, sufficiente al 70% — non al 100%**. Lo smoke read-only valida
`costruisci_lookup_durate` in isolamento ma NON il path produzione
end-to-end (cambio `builder_mode` + rebuild + verifica giri persistiti
con `vuoto_coda.durata_min` realistico). R-PROC-1 (`severo.md:173-198`)
chiede *"verifica e2e empirica al primo cambio strangler"* — la
definizione di "e2e" è "esecuzione runtime in produzione", non "stress
test del helper isolato". **Il cap voto MAX 6/10 R-PROC-1 NON è
chiuso al 100%, va portato al 70% di chiusura → cap voto MAX 7/10
con riserva**. Pattern entry 270 (KO operativo single-sede dopo
mock-only): smoke isolato non rivela bug di integrazione, esattamente
la classe di problema R-PROC-1. Per chiudere al 100% serve
`POST /programmi/17/build?modalita=esplorativo` + verifica giri
persistiti con delta operativo (= 1 giro G-FIO con `vuoto_coda.durata_min
> 60` post-MR-S2). Costo: 30-45 min onesti. NINO ha scelto di NON
farlo perché *"non toccare i 22 giri esistenti"* — scelta
conservativa ragionevole, MA non chiude R-PROC-1.

### 2. S1 INVALIDATO empiricamente: sufficiente o emergono nuove preoccupazioni?

**Sufficiente per il finding originale, MA emergono nuove preoccupazioni
per stazioni TILO/Malpensa Express non testate**. La docstring entry
298 dichiara onestamente il limite: *"per stazioni con attività
dominata da tratte brevi intra-direttrice (es. TILO, Malpensa
Express), la baseline può essere meno predittiva del costo long-haul
vuoto"*. Questo è onesto e corretto — pattern memoria
`project_etr524_tilo_linee` (TILO solo 4 linee corte) e
`project_dotazione_trenord` (ETR522 71 pezzi, Malpensa Express
dedicato). Per quei materiali, il fallback geometrico opzione
B-semplificata produrrà sotto-stime quando emergeranno coppie
distanti TILO o ETR522 vuoti per posizionamento.

**Decisione corretta**: rinviare a MR-D7 raffinerà con
`km_tratta + velocita_max_kmh`. **Decisione onesta**: dichiarare il
limite nella docstring (fatto). **Preoccupazione residua**: nessun
test mirato sui materiali TILO/Malpensa per validare che il fallback
60 hardcoded NON peggiori i casi (es. coppia LUGANO-CADENAZZO ETR524
breve). Costo aggiuntivo: 30-60 min per smoke prod su prog ETR524
attivo. NON necessario per chiudere il finding entry 298 (lo scope
era TIRANO-FIO), ma da segnare per MR-D7 o cleanup intercalato.

### 3. S2 fix range vs esatto: accettabile o ancora exact assertion fragile?

**Accettabile in spirito, NON letterale alla raccomandazione, declassato
da HIGH a LOW (vedi finding R1 sopra)**. Il fix entry 298 è sostanziale
— il calcolo `durata_min = (h_arr*60+m_arr) - (h_par*60+m_par)` è
robusto a refactor cross-mezzanotte e arrotondamento, mentre l'`==
_time(17, 25)` esatto pre-fix sarebbe saltato a future modifiche
dell'algoritmo `_costruisci_vuoto_rientro_target` su minuti.
**Tecnicamente "esatto" è ancora "esatto"**: `assert durata_min == 85`
salterà se MR-D7 introduce round-up dei min_tratta che produce 84 o 86.
Il rischio è basso (durata in test in-memory è deterministica) ma
non zero. Confronto con raccomandazione retro 1 letterale (`<= 5
differenza`): 5 min di sostituzione 1 a 1 chiuderebbe la lettera
senza costo. Pattern §7 "letteralmente sufficiente" (= il fix è
tecnicamente OK ma il claim "U adottata" è preserved, claim retro
1 era "U non adottata 4/5 volte"). Onestà ex-post NINO: dichiarare
"adottata in spirito non in lettera" è onestà, "U adottata" generico
è ottimismo.

### 4. S4 R-PROC-7 rinviato a cleanup futuro: scope onesto o scope-cutting silente §7?

**Scope-cutting silente §7 PIGRIZIA**, vedi finding S2 sopra in
dettaglio. NINO ha 3 risposte possibili a un finding HIGH:
1. ✅ chiuderlo (qui sarebbe 30-45 min onesti);
2. ✅ dichiarare residuo con motivazione oggettiva specifica (NON
   generica) + SLA (= "rinviato a Sprint 8.4 MR-Z perché [motivazione]";
3. ❌ rinviare con motivazione generica "scope diverso, MR cleanup
   futuro" senza SLA.

**Entry 298 sceglie l'opzione 3**. Il file `.claude/agents/severo.md`
non è "scope diverso" — è esattamente lo scope di SEVERO meta-processo,
modificato regolarmente da NINO (entry 270 ha aggiunto R-PROC-1, entry
285 ha aggiunto R-PROC-3 e R-PROC-4 e R-PROC-5, ecc.). Aggiungere
R-PROC-7 con format canonico (**verificato `wc -l severo.md = 436`,
3 R-PROC già presenti come template**) è copy-paste struttura + 30
min wording. Pattern test §7-1: "fix scrivibile in <2h? sì → CHIUDILO".
Risposta NINO: "scope diverso" — non scrivibile in <2h sì è, è solo
non urgente. Pigrizia mascherata.

**Pattern ricorrente terzo in 2 mesi**: retro 1 S6 (CI vs pre-commit
"scope separato"), retro 1 S3 (smoke prod "scope separato"), entry
298 S4 (R-PROC-7 "scope diverso"). 3 hash di "scope cutting con
giustificazione di processo".

### 5. Pattern §7 NIENTE PIGRIZIA: 3/4 chiusi, 1 rinviato — caso reale o ricorrenza?

**Misto: 60% caso reale di chiusura veloce + 40% ricorrenza pattern**.

Il **lato positivo** è reale e va segnato: 3 HIGH chiusi in 60 min
totali è disciplina di esecuzione, non bluff. Smoke prod read-only è
un metodo onesto, fix test è robusto, docstring aggiornata è
coerente. Pattern §3 ("un passo alla volta") + §4 ("ammettere
l'errore SEVERO ipotizzato") sono applicati.

Il **lato negativo** è ricorrenza:
- **3/4 HIGH chiusi** ma 1 rinviato con motivazione generica (S4, vedi
  finding S2 sopra): pattern "scope diverso" 3° in 2 mesi.
- **3/4 retro 1 livello MED/LOW silenziati** (S5/S6/S7 mai menzionati
  in entry 298, vedi finding S3 sopra): pattern "selective response
  ai HIGH only" identificato in retro 1 conclusione, ricorrenza
  confermata.
- **R-PROC-1 chiusa al 70% con claim implicito 100%** (TN-UPDATE
  entry 298 dice "S3 chiuso", non "S3 chiuso al 70%"): pattern
  "claim ottimistico in TN-UPDATE" identificato in retro 1 finding
  S2 (claim "U adottata" falso), ricorrenza marginale qui.

**Diagnosi onesta**: il MR è eseguito velocemente e bene per la parte
chiusa, ma la chiusura è **incompleta del 30-40%** rispetto al perimetro
totale dei finding retro 1. La sintesi NINO "3/4 HIGH chiusi" è
tecnicamente vera ma omissiva: di 7 finding retro 1 totali (4 HIGH
+ 2 MED + 1 LOW), 3 sono chiusi (S1+S2+S3 HIGH), 1 rinviato (S4 HIGH),
3 silenziati (S5 MED + S6 MED + S7 LOW). **Tasso di copertura reale:
3/7 = 43%, NON 75%**.

### 6. Voto finale

**6/10\*** provvisorio fallback V4 Flash (8° critica consecutiva
senza V4 Pro). **Delta vs retro 1: 0** (identico voto).

Calcolo:
- **+1 punto** per chiusura veloce 3/4 HIGH (60 min sotto target).
- **+1 punto** per smoke prod read-only effettivo (R-PROC-4 livello
  2 fatto sostanzialmente).
- **+1 punto** per onestà in docstring + ammettere ipotesi falsa
  S1 retro 1 (METODO §4 applicato in entrambe le direzioni).
- **-1 punto** per R-PROC-1 chiusa al 70% con claim implicito 100%
  (cap voto MAX 7/10 con riserva, non chiuso).
- **-1 punto** per S4 HIGH rinviato come "scope diverso" = pigrizia
  §7 silente (3° pattern ricorrente).
- **-1 punto** per S5+S6+S7 retro 1 silenziati senza menzione (4° pattern
  ricorrente "selective response to HIGH only").

**Saldo: base 6 + 3 - 3 = 6**.

**Target NINO ≥7/10 NON raggiunto**. La chiusura è veloce ma
incompleta del 30-40%. Per saltare a 7/10 sarebbero serviti:
- Smoke prod end-to-end runtime (+30-45 min) → R-PROC-1 chiusa al
  100% → +1 punto
- Chiusura S5 MED (15-20 min) + dichiarazione esplicita S6/S7 → +1
  punto

Totale aggiuntivo: 60-90 min. Pattern §7 ricorrente: i 60-90 min
mancanti sono esattamente la quantità di lavoro che NINO ha rinviato
classificando come "scope diverso".

Margine atteso V4 Pro: -0.5/-1 punto, voto effettivo V4 Pro
probabilmente **5/10\*** (V4 Pro è più severo sui pattern ricorrenti
+ scope-cutting).

---

## Confronto con voto retro 1 (= 6/10\*) → delta atteso

**Delta zero, voto identico 6/10\***. La traiettoria pattern Sprint
8.2 → 8.3 è:
- 4/10 → 5/10 → 6/10\* → 5/10\* → 5/10\* → 6/10\* (PIANO-S2) → 3/10
  (BACKLOG-CLEANUP) → 6/10\* (retro 1) → **6/10\* (questa retro 2)**

**Pattern stagnante al tetto strutturale 6/10\***. Dopo 9 critiche
in 3 settimane, voto medio 4.9/10, **sotto soglia "solido" 7/10**.
NINO sta migliorando marginalmente la velocità di chiusura (60 min
vs >2h pre-Sprint 8.2) ma:
- I finding HIGH chiusi vengono chiusi al 70-90%, non 100%.
- I finding MED/LOW vengono silenziati invece di chiusi.
- I pattern §7 PIGRIZIA si ripetono 3-4 volte consecutive con la
  stessa motivazione generica "scope diverso".

**La rottura del tetto a 7/10\* richiede**:
1. Chiudere R-PROC-1 al 100% per ogni MR strangler (smoke e2e
   runtime, NON read-only) → cap voto sale.
2. Rispondere a TUTTI i finding di una critica precedente, non solo
   ai HIGH (test §7 letterale). 3-30 min/finding MED/LOW, 5-20 min
   max per dichiarazione onesta.
3. Smettere di usare "scope diverso" come escape valve generica:
   sostituirla con "rinviato a Sprint X MR-Y perché [motivazione
   oggettiva specifica]" + SLA.

**Trend**: stagnante con margine velocità migliorato. La diagnosi
strutturale di retro 1 ("chiudo l'80% del finding e lascio il 20%
strutturale") è confermata in entry 298. **R-PROC-7 sarebbe stata
una vittoria simbolica significativa** perché chiudere il finding
"verifica superficiale `verificato ls`" come R-PROC formalizzata
avrebbe rotto il ciclo §7. NON è stata adottata, ciclo continua.

---

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione**: ✅ smoke prod read-only ha precedeto
   il fix docstring (= verifica empirica prima di documentare il
   limite). R-PROC-4 livello 2 finalmente applicato. Recupero netto
   vs retro 1.
2. **Numeri non ipotesi**: ✅ TIRANO=152 reale (non più "~190km
   memoria"), CERTOSA=73 reale, fallback=152 reale. Smoke prod ha
   sostituito stime qualitative con dati DB diretti. ✅
3. **Un passo alla volta**: ✅ smoke prima, fix test poi, docstring
   in fondo. 1 commit `b1ef309` con scope dichiarato esattamente.
4. **Ammettere l'errore**: ✅ doppio: NINO ammette ipotesi qualitativa
   "TIRANO 60-80" era sbagliata (entry 298 + commit message). SEVERO
   retro 1 ammesso falso positivo S1 (questa critica retro 2).
   Onestà ex-post applicata simmetricamente.
5. **Verifica prima del commit**: ⚠️ MIRATA. 58 test passed (32
   aggregazione + 26 durata_vuoto), NON full suite 600+ test.
   Mypy --strict solo `durata_vuoto.py`, NON `backend/src`. Ruff
   solo "su file modificati", NON full project. Per modifiche
   chirurgiche docstring + test il rischio è basso, MA il claim
   implicito "tutto verde" è incompleto. Vedi finding S4 sopra.
6. **Preservare non distruggere**: ✅ smoke read-only + rollback +
   nessuna toccata su 22 giri esistenti prog 17. Pattern conservativo
   appropriato.
7. **Costanza nel tempo**: ⚠️ MISTA. Velocità chiusura migliorata
   (60 min vs >2h Sprint 8.2). Pattern §7 PIGRIZIA confermato 3°
   in 2 mesi. Pattern "selective response HIGH only" confermato
   2° in 2 settimane. Pattern "claim ottimistico chiusura" marginale
   ma presente.

---

## R-PROC SEVERO esistenti applicate?

- **R-PROC-1 (verifica empirica E2E primo cambio strangler)**:
  ⚠️ **PARZIALE 70%**. Smoke prod read-only fatto ma NON e2e runtime.
  Cap voto MAX 6/10 → confermato voto 6/10\* (retro 1 era 6/10\* per
  smoke MAI fatto, ora è 6/10\* per smoke 70% — stesso cap, motivazione
  diversa). Per chiudere al 100% serve smoke runtime end-to-end.
  Vedi finding S1 sopra.
- **R-PROC-2 (assunzioni esplicite per constraint HARD)**: ✅ N/A,
  entry 298 non introduce constraint HARD nuovi.
- **R-PROC-3 (MED diventa HIGH BLOCKING al primo cambio in produzione)**:
  N/A direttamente. NB: se MR-D7 toccherà `durata_vuoto.py` o
  `aggregazione_linea_centrica.py`, S5 MED retro 1 (zombie placeholder
  riga 363-371) diventa HIGH BLOCKING per R-PROC-3. NINO ha 1 MR
  di "tempo libero" prima che il debito esploda.
- **R-PROC-4 (DB-first preventiva pre-impl fix architetturale)**:
  ✅ **livello 2 finalmente applicato**. Smoke prod ha popolato
  baseline empirica (TIRANO=152, CERTOSA=73, mediana globale=69).
  Recupero netto vs retro 1 finding 7 ("DB-first solo livello 1
  applicato superficialmente"). Lesson learned operativa.
- **R-PROC-5 (Test xfail strict deve esercitare codice corrente)**:
  ✅ N/A, entry 298 non introduce nuovi xfail.
- **R-PROC-7 proposta (verificato X = comando concreto)**:
  ❌ **NON ADOTTATA**, vedi finding S2 sopra. Costo onesto 30-45
  min, rinviata come "scope diverso, MR cleanup futuro" — pigrizia
  §7. Senza R-PROC-7 il pattern entry 287 "verificato `ls`" può
  ripetersi senza freno formale.

---

## Cosa NON ho controllato

- **AMILCARE V4 Pro indipendente**: 1 timeout `-32001` su
  `mcp__amilcare__reason`, brief ~3KB. Pattern entry 248 cronico
  confermato 8° volta in 4 giorni: critiche entry
  270/275/278/284/285/PIANO-S2/retro1 + questa retro 2. Server V4
  Pro saturo cronicamente.
- **AMILCARE V4 Flash 1° + 2° tentativo timeout**, riuscita al 3°
  con brief ~1.5KB. Output filtrato per 4 falsi positivi tecnici
  verificati (vedi sezione "Motore usato" all'inizio).
- **Smoke prod end-to-end runtime POST-MR-S2**: NON eseguito da NINO
  in entry 298 (finding S1 sopra), NON eseguito da SEVERO retro 2
  (sarebbe scope di NINO non del critico). Stato R-PROC-1 reale: 70%.
- **Verifica empirica baseline TILO/Malpensa Express**: la docstring
  entry 298 dichiara il limite onestamente ma non ha numeri concreti.
  Memoria progetto suggerisce ETR524 ha solo 4 linee TILO corte
  (= baseline corta, fallback potrebbe sotto-stimare per coppie
  distanti se mai esistessero, scenario edge). Non testato. Scope
  MR-D7.
- **Performance impact 1 query DB extra in produzione**: prog 17
  6536 corse, costo aggiuntivo atteso 100-300ms (caching prepared
  statement). Non misurato. Smoke read-only ha eseguito la query
  ma non ha cronometrato.
- **Test del wrapper `costruisci_lookup_durate` con corse `min_tratta=NULL`**:
  smoke prod ha mostrato 326 coppie popolate, ma non ha ispezionato
  il branch `_durata_min_da_orari` per corse con `min_tratta=NULL`.
  Se la maggioranza ha `min_tratta` popolato, il branch alternativo
  è poco esercitato. Non profilato.
- **Verifica full suite 600+ test backend**: SEVERO retro 2 non ha
  fatto girare i test (fuori scope critico). NINO ha eseguito solo
  58 mirati. Verifica completa non disponibile.
- **Working tree non committato Sprint 8.4 S2** (test_api_programmi_conferma.py
  + test_piano_alpha_integration.py): nuova fixture
  `_crea_giro_chiusura_diversa_dal_deposito` + test
  `test_piano_alpha_blocco_vettura` reso non-vacuo. Cambio sostanziale
  ma fuori scope critica retro 2 (= entry 298). Spawn task suggerito
  per critica separata Sprint 8.4 S2 se NINO committa.

---

## Tracciabilità

- **AMILCARE V4 Pro tentato 1× con `mcp__amilcare__reason`** (brief
  ~3KB) → timeout `-32001`. Pattern entry 248 confermato 8° volta
  consecutiva in 4 giorni. Server V4 Pro saturo cronicamente.
- **AMILCARE V4 Flash tentato 3× con `mcp__amilcare__code`**: 1° (brief
  ~3KB) timeout, 2° (brief ~2.5KB) timeout, 3° (brief ~1.5KB) riuscita
  in ~10s con reasoning trace + output ~600 parole strutturato.
- **Output V4 Flash filtrato** per 4 falsi positivi tecnici verificati:
  - F1 V4 Flash voto 7/10: troppo generoso vs analisi indipendente
    (motivo: V4 Flash sottovaluta il pattern §7 ricorrente). Adottato
    voto 6/10\* dopo verifica residui retro 1 + scope-cutting S4.
  - F2 V4 Flash "S2 esatto accettabile completo": parzialmente vero.
    Riformulato come finding R1 LOW residuo retro 1 (raccomandazione
    letterale ±5min non rispettata, fix è OK in spirito).
  - F3 V4 Flash "S6 file `.github/workflows/ci.yml` +
    `.pre-commit-config.yaml`": falso positivo tecnico verificato `ls`:
    workflow è `backend-ci.yml` (NON `ci.yml`), `.pre-commit-config.yaml`
    NON esiste (era proprio il finding S6 retro 1 che lamentava
    l'assenza). Riformulato come "S6 retro 1 stato invariato".
  - F4 V4 Flash stime fix "S5 15 min, S6 20 min": leggermente al
    ribasso. Verificato `wc -l severo.md = 436 righe`, R-PROC-7 in
    formato canonico è 30-45 min onesti, S6 dichiarazione parziale è
    5 min se solo TN-UPDATE.
- **Critiche precedenti citate**:
  - `docs/critiche/SPRINT-8.3-MR-S2-MR-S6-codice-committato.md` (retro
    1, voto 6/10\*)
  - `docs/critiche/SPRINT-8.3-PIANO-S2-durata-vuoto.md` (PIANO-S2,
    voto 6/10\*)
  - `docs/critiche/SPRINT-8.2-MR-D5e+bug-architetturale-single-sede.md`
    (entry 270, voto 4/10, origine R-PROC-1 + R-PROC-2)
- **Pattern di critica del ciclo Sprint 8.2 → 8.3**:
  4/10 → 5/10 → 6/10\* → 5/10\* → 5/10\* → 6/10\* (PIANO-S2) → 3/10
  (BACKLOG-CLEANUP) → 6/10\* (retro 1) → **6/10\* (retro 2 questa)**.
  Voto medio 4.9/10 dopo 9 critiche, sotto soglia "solido" 7/10.
- **Trend traiettoria**: **velocità migliorata (60 min vs >2h
  pre-Sprint 8.2)** ma **tetto strutturale 6/10\* stagnante**. Le
  modifiche raccomandate per saltare a 7/10\* sono note (smoke e2e
  runtime + chiusura S5+S6 retro 1 + S4 HIGH R-PROC-7) e scrivibili
  in <2h totali. Ricorrenza pattern §7: il tempo viene speso in
  velocità su 60-70% del lavoro invece che in completezza al 100%.
