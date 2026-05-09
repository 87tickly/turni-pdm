# RE-CRITICA SEVERO — Sprint 8.2 MR-PD3 (motore AMILCARE V4 Pro)

**Data**: 2026-05-09
**Commit / range**: `053b1f2` (MR-PD3a vettura_resolver) + `90ed424`
(MR-PD3b+PD4 deposito_first + 9 test)
**Entry TN-UPDATE**: 264, 265
**Motore usato**: AMILCARE V4 Pro via `mcp__amilcare__reason` —
operativo, brief snello ~1.5KB (target dopo 2 timeout su brief più
grandi). Output filtrato da NINO. Vedi `docs/critiche/SPRINT-8.2-MR-PD3-deposito-first.md`
per la critica fallback FAUSTO che questa re-critica conferma e
sovverte parzialmente.
**Riserva metodologica precedente**: rimossa. Questa critica chiude
la riserva dichiarata nella fallback (voto 4.5/10 provvisorio).
**Bias auto-compiacenza NINO**: smascherato. AMILCARE peggiora il
voto, vede 3 finding strutturali HIGH-CRITICAL che né FAUSTO né
NINO avevano colto.

---

## Sintesi (3 righe max)

AMILCARE conferma il bug `is_notturno` come CRITICAL e individua **tre
finding strutturali profondi mancati dal fallback FAUSTO**: §15
unicità segmenti cross-PdC (illegalità output), idempotenza builder
non garantita (API live non-deterministica), zero gestione eccezioni
`httpx` (endpoint MR-PD5 vulnerabile a 500). Voto **3/10**, peggiore
di FAUSTO 4.5/10. Il MR è da rivedere in modo sostanziale prima di
collegare l'endpoint genera-turno-pdc.

## Cosa funziona

Confermato dal fallback FAUSTO, niente di nuovo:

- Decomposizione resolver/builder corretta (separazione testabile).
- HARD scarto su cap condotta (`deposito_first.py:245-249`) coerente
  con plan Strada B.
- Pipeline `replace(draft, blocchi=..., stazione_fine=...,
  fine_prestazione=..., prestazione_min=...)` immutabile e atomica.
- Caso degenere chiusura == deposito gestito sia nel resolver
  (`vettura_resolver.py:192-197`) sia nel builder
  (`deposito_first.py:252-254`) con short-circuit verificato dal
  test `test_chiusura_uguale_deposito_no_rientro_extra`.

## Cosa si poteva fare meglio (finding NUOVI di AMILCARE)

I finding S1-S11 della fallback FAUSTO sono confermati nel quadro
generale. Qui aggiungo solo i punti **profondi mancati dal fallback**.

### A1 — §15 unicità segmenti cross-PdC: nessun vincolo

- **Severità**: CRITICAL
- **Dove**: `backend/src/colazione/domain/builder_pdc/deposito_first.py`
  (assenza globale di pool/manager segmenti) +
  `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:204-211`
  (chiamata `trova_treno_vettura` senza prenotazione del treno scelto).
- **Cosa**: NORMATIVA-PDC §15.1 letterale: *"ogni segmento di treno
  (commerciale o U-numero) del turno materiale si assegna a un solo
  PdC. Nessun treno può apparire in due PdC distinti dello stesso
  giorno."* §15.2: *"il builder mantiene una pool di segmenti
  disponibili […] ogni volta che costruisce un PdC e gli assegna un
  segmento, lo rimuove dalla pool"*. Vale *"sempre, sia nella
  generazione manuale sia nel builder automatico"*.

  Il MR-PD3 non ha pool, non ha check di prenotazione, non ha
  contesto cross-PdC. Due chiamate indipendenti di
  `costruisci_giornata_deposito_first` su giri diversi possono
  selezionare la **stessa vettura** per il rientro (es. treno 2426
  TIRANO→MILANO_PG): l'API ritorna lo stesso treno ad entrambe le
  chiamate, entrambi i builder lo accettano, output finale =
  doppione di treno-vettura assegnato a 2 PdC distinti.
- **Perché è un problema**: violazione HARD della §15 — output
  illegale per definizione di normativa. Non è un edge case, è il
  caso normale: ogni programma reale Tirano-Mi.PG ha più PdC che
  finiscono il turno a TIRANO nelle stesse fasce orarie e la
  vettura disponibile per il rientro è la stessa.

  Il fallback FAUSTO ha **completamente mancato questo punto**.
  Era concentrato sui finding "interni" ai due moduli; non ha
  alzato lo sguardo al complesso normativa. È esattamente il tipo
  di blind spot che spiega perché SEVERO con motore secondario è
  inferiore: bias di prossimità sul codice toccato.
- **Fix proposto**: introdurre `RegistroSegmentiAssegnati` (o
  rinominare `PdcPool` se già esiste) condiviso a livello di "run
  builder programma": una sessione di costruzione PdC sull'intero
  programma popola la pool col turno materiale (corse commerciali
  + U-numero §8); ogni `costruisci_giornata_deposito_first` riceve
  la pool come dipendenza, prenota il treno-vettura scelto, verifica
  che NON sia già prenotato. Se è già prenotato → fallback al
  prossimo treno utile (richiede modifica anche a
  `trova_treno_vettura` per accettare un set di "esclusi" o per
  ritornare lista candidati invece del primo).

  Scope realistico: refactor tra MR-PD3 e MR-PD5 di mezza giornata.
  **Non rimandabile a Sprint successivo**: il primo run reale
  dell'endpoint MR-PD5 produrrà subito turni con doppioni.
- **Costo del fix**: 4-6h (definizione `RegistroSegmenti`,
  signature `risolvi_rientro` aggiornata, fallback "vettura
  successiva", 4-5 test integration su scenario doppione).

### A2 — Idempotenza builder non garantita (API live non-deterministica)

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py:204-211`
  (`await trova_treno_vettura(...)`) — il PartenzeCache è opzionale
  (`cache: PartenzeCache | None = None`).
- **Cosa**: l'API `live.arturo.travel/api/partenze/{stazione}`
  ritorna *"stato real-time"* dei treni passeggero. Tra due
  chiamate consecutive sulla stessa stazione la response può
  cambiare per:
  - Aggiornamento orari di esercizio (treni cancellati,
    sostituzioni, ritardi reportati).
  - Retry con backoff su 429: chiamata 1 fallisce → log →
    chiamata 2 va → response diversa per timing.
  - PartenzeCache è in-memory per-request; tra 2 invocazioni
    `costruisci_giornata_deposito_first` separate (stesso giro,
    momenti diversi) la cache è vuota → 2 fetch, 2 risultati
    potenzialmente diversi.
- **Perché è un problema**: il builder PdC dev'essere **idempotente**
  per una versione fissa di input (giro materiale + depot +
  variante). Senza idempotenza:
  - Il rigenerare un programma cambia silenziosamente i turni
    PdC anche senza modifica di dati → utente vede diff
    inspiegabili.
  - I test integration MR-PD5 con `MockTransport` sono affidabili
    ma il run prod non lo è.
  - Diff tra "preview" e "salva definitivo" può divergere.
- **Fix proposto**: due opzioni:
  1. **Snapshot orari**: al primo build di un programma, salvare
     in DB lo snapshot delle response API per le stazioni rilevanti
     (`PartenzeSnapshot`). Builder successivi (rigenerazione,
     anteprima, definitivo) leggono dallo snapshot.
  2. **Cache shared cross-build**: PartenzeCache promossa a
     dependency obbligatoria, popolata una volta dal manager-
     builder per programma e passata a tutte le chiamate
     `costruisci_giornata_deposito_first`. La cache è valida per
     un "ciclo di build programma" (es. 1h o 1 sessione).

  Opzione 1 è la corretta semanticamente (riproducibilità anche
  giorni dopo). Opzione 2 è pragmatica per il MVP MR-PD5.
- **Costo del fix**: opzione 2 = 2h (refactor signature + manager
  builder); opzione 1 = 1-2 giorni (migration + persistenza +
  invalidazione).

### A3 — Zero gestione eccezioni `httpx`: endpoint MR-PD5 vulnerabile a 500

- **Severità**: HIGH
- **Dove**: `backend/src/colazione/domain/builder_pdc/vettura_resolver.py`
  (intera funzione `risolvi_rientro`, no try/except) +
  `backend/src/colazione/domain/builder_pdc/deposito_first.py:268-277`
  (`await risolvi_rientro(...)` no try/except).
- **Cosa**: verificato a `grep -E "try|except|raise"` su entrambi
  i moduli originali del MR — **0 risultati**.
  `await trova_treno_vettura(...)` può sollevare:
  - `httpx.HTTPError` (5xx upstream live.arturo.travel)
  - `httpx.TimeoutException` (network slow)
  - `httpx.ConnectError` (DNS / refused)
  - `ValueError` / `KeyError` su parsing risposta malformata

  Nessuna è catturata. Si propaga al chiamante.
- **Perché è un problema**: quando MR-PD5 collega all'endpoint
  `POST /api/giri/{id}/genera-turno-pdc`, qualsiasi flake di rete
  → traceback Python → FastAPI 500 al pianificatore frontend. Non
  c'è fallback graceful (es. "API live non disponibile, marca la
  giornata come VOCTAXI con warning"). L'endpoint diventa fragile.

  La fallback FAUSTO ha mancato anche questo: il finding più simile
  era S5 "zero integration test" che però copriva un sintomo
  diverso.
- **Fix proposto**:
  ```python
  # vettura_resolver.py — wrap step 1
  try:
      treno = await trova_treno_vettura(...)
  except (httpx.HTTPError, httpx.TimeoutException) as e:
      logger.warning(
          "vettura_resolver: API live unavailable (%s), "
          "fallback diretto a MM/VOCTAXI", e
      )
      treno = None
  ```
  Più: definire un retry policy (es. 1 retry con backoff 500ms);
  se ancora fail, `treno = None` e si scende a MM/VOCTAXI.

  Per `deposito_first` + endpoint MR-PD5: try/except catch-all
  attorno a `risolvi_rientro` con violazione tipizzata
  (`"giornata1: rientro non risolto: api_live_error"`) che il
  persister può marcare come `bozza` con warning UI.
- **Costo del fix**: 1-1.5h (try/except + 2 test scenario error +
  retry policy).

## Conferma dei finding fallback FAUSTO (S1-S11)

I 11 finding S1-S11 sono **confermati** dall'analisi AMILCARE-driven.
In particolare:

- **S1** (cap notturno superinclusivo): CRITICAL confermato
  matematicamente con il check delle linee 331+335 di builder.py al
  commit 90ed424. Bug attivo non latente. **AMILCARE concorda con
  FAUSTO**.
- **S4** (test cap-eccede ambivalente): rilettura del file mostra
  branch `if draft is None: assert violazione; else: assert
  stazione_fine == CREMONA` → confermato test inutile.
- **S5** (zero integration): confermato. Aggiungo che nel suo blind
  spot menziona `arrivo_min=None` come edge case ma il codice di
  `trova_treno_vettura` ha già guard `if arrivo_min is None: return
  None` (live_arturo.py:359). Quel sub-finding di FAUSTO è **falso
  positivo** — annotato.
- **S2/S6/S7/S8/S9/S10/S11**: confermati nei termini di FAUSTO.
- **S3** (§7.3 condotta produttiva): AMILCARE concorda che è
  HIGH-LATENT, scope-cutting **legittimo** perché richiede ranking
  multi-blocco che è proprio il MR-C7 dichiarato.

## Voto complessivo

**3 / 10** — peggiore di FAUSTO 4.5/10.

Motivazione AMILCARE: *"il bug notturno confermato corrompe i draft,
§15 e idempotenza assenti, zero gestione errori"*.

Espansione NINO: il MR-PD3 ha il cuore architetturale corretto (è
l'unico aspetto che salva il voto dal 2/10 vero), ma l'esecuzione
ha un bug attivo (S1) e tre falle strutturali (A1+A2+A3) che si
sommano a 4 falle interne (S2/S4/S5/S8). Sono troppe per un MR che
dovrebbe essere il "cuore architetturale" Strada B.

Scala:
- 9-10: lavoro da senior, finding solo cosmetici
- 7-8: solido, qualche miglioramento sostanziale possibile
- 5-6: funziona ma con debito o blind spot non secondari
- 3-4: problemi strutturali, da rivedere ← **siamo qui**
- 1-2: bocciato, riaprire prima di proseguire

## Cosa fixare PRIMA di MR-PD5 (ordine AMILCARE-driven)

**P0 (obbligatori, ~10-12h)** — senza questi MR-PD5 produce output
illegale o crash:

1. **S1** `is_notturno` → `is_cap_notturno` property allineata a
   §11.8 (presa 01:00-04:59). ~2h.
2. **A3** try/except `httpx.HTTPError` in `risolvi_rientro` +
   fallback graceful + 2 test scenario error. ~1.5h.
3. **A1** `RegistroSegmentiAssegnati` cross-PdC: pool + signature
   `risolvi_rientro` con `esclusi: set[str]` + 4-5 test integration
   doppione. **~4-6h**. Il fix più sostanziale, non rimandabile.
4. **A2** PartenzeCache promossa a obbligatoria + manager-builder
   shared (opzione 2). ~2h. La snapshot persistente (opzione 1)
   può aspettare MR-PD7+.

**P1 (raccomandati, ~3-5h)** — senza questi MR-PD5 funziona ma
porta debito:

5. **S2** estrarre `giornata_base.py` modulo helper condiviso
   (chiude API privata cross-module). ~2-3h.
6. **S4** test cap-eccede senza branch ambivalente. ~30 min.
7. **S5** 3 test integration sentinel pre-endpoint. ~2h.
8. **S7** replace_all `Scelza → Scelta` (5 min, ora prima che si
   propaghi).

**P2 (decisione utente)**:

9. **S6** `Depot.is_servito_da_mm` migration + seed (~1.5h).
10. **S11** `+15` post MM/VOCTAXI: aggiornare NORMATIVA o rimuovere.
11. **S10** semantica gap ATTESA vs PK degenere.

**P3 (legittimi rimandi a MR successivi)**:

12. **S3** §7.3 condotta produttiva → MR-C7 (legittimo, scope
    grande con ranking multi-blocco).
13. §9 split CV → MR-C7 (legittimo).
14. §10.3 FR g1+g2 multi-day → MR-C8 (legittimo, modifica modello
    dati).
15. §11.2-§11.4 ciclo settimanale → MR-PD7 (legittimo).

## Aderenza al METODO-DI-LAVORO

1. **Diagnosi prima di azione** — sì, MR-PD3 splittato a/b
   correttamente da audit MR-PD1.
2. **Numeri non ipotesi** — parzialmente. Cap 510/420/330 da
   NORMATIVA. MM/VOCTAXI 30 min senza fonte normativa esplicita
   (annotato anche da FAUSTO).
3. **Un passo alla volta** — sì, split MR-PD3a/b ridotto rischio.
4. **Ammettere l'errore** — N/A.
5. **Verifica prima del commit** — parzialmente. Test verde su
   17 mockati. Zero integration. Nessuno ha catturato A1+A2+A3
   prima di SEVERO retrospettivo.
6. **Preservare non distruggere** — sì, builder MVP intatto.
7. **Costanza nel tempo** — N/A.

## Cosa NON ho controllato

- **Build/deploy reale**: non ho eseguito pytest/mypy/ruff sui
  commit originali pre-fix. Mi sono basato sul commit message che
  dichiara green.
- **`PartenzeCache` implementazione interna**: ho letto la
  signature ma non l'invalidazione, TTL, threadsafety. L'analisi
  A2 può essere ricalibrata se la cache ha già garanzie più forti
  di quanto suppongo.
- **`live.arturo.travel` SLA reale**: l'analisi A3 assume che
  l'API può fallire; non ho il dato empirico (uptime, latenza
  p99) ma è prudente assumere fallibilità per qualsiasi API esterna.
- **Esistenza `RegistroSegmentiAssegnati` (o equivalente) nel
  builder giro**: non ho controllato se Plan-D builder giro (entry
  263+) ha già una pool segmenti che si potrebbe estendere ai PdC.
  Se sì, A1 si riduce ad "estensione pool esistente" e il costo
  scende a 2-3h.
- **Entry 269/271/273 di follow-up post-MR-PD3**: non sono parte
  della critica MR-PD3 originale per istruzione esplicita
  ("RE-CRITICA del MR-PD3 ORIGINALE pre-fix"). Sono materiale di
  validazione retrospettiva che conferma che il fallback FAUSTO
  aveva ragione su S1, S4, S7 (chiusi da entry 269), S2 (chiuso
  da entry 273), S5 (chiuso da entry 271 che ha scoperto bug DB
  CHECK constraint MM/VOCTAXI). Restano aperti S3, S6, S8, S9,
  S10, S11 + i 3 nuovi A1, A2, A3 di questa re-critica.
- **NORMATIVA-PDC §15.4** sui materiali vuoti (U****): ho letto
  fino a §15.3 ma non §15.4-§15.8 in profondità. Ulteriori vincoli
  unicità su U-numero possono rafforzare il finding A1.

## Tracciabilità

- **Brief AMILCARE inviato**: dopo 2 timeout su brief 5KB e 3KB
  → terzo tentativo brief 1.5KB con 3 domande secche → risposta
  in pochi secondi. Pattern entry 248 confermato: brief snello
  vince. Voto AMILCARE 3/10, finding strutturali A1/A2/A3.
- **Filtro NINO applicato**: confermato A1+A3 verificando file
  `_PD3a.py`, `_PD3b.py` con `grep try|except|raise` (0 risultati).
  A2 confermato leggendo `live_arturo.py` PartenzeCache è in-memory
  per-request. Falso positivo FAUSTO S5 sub-punto `arrivo_min=None`
  smascherato verificando guard in `live_arturo.py:359`.
- **Confronto col fallback FAUSTO**: 11 finding S1-S11 confermati
  in linea generale. AMILCARE aggiunge A1+A2+A3 come HIGH-CRITICAL
  che spostano il voto da 4.5/10 a 3/10. Conferma in particolare
  che S1 è effettivamente CRITICAL (matematica del flag vs §11.8).
- **Smascheramento bias**: il fallback NINO post-fix avrebbe
  probabilmente dato 6-7/10 ("tutti gli HIGH+CRITICAL chiusi");
  AMILCARE su PRE-FIX dà 3/10 → conferma quanto detto in entry 248
  che il bias di auto-compiacenza è ineliminabile senza motore
  esterno indipendente.
