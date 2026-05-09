# PIANO MR-PD7b — §11.4 riposo settimanale ≥ 62h con 2 giorni solari interi

> Piano scritto da NINO il 2026-05-09 prima del codice. Va criticato
> da SEVERO (motore AMILCARE V4 Pro) prima dell'implementazione,
> come da memoria `feedback_severo_sempre_su_piani.md`.

## Contesto

Ultimo MR del piano α Sprint 8.2 (post 3a entry 277 + 3b entry 279).
Implementa NORMATIVA-PDC §11.4 (regola RIGIDA, vedi §11.7):

> "Riposo settimanale ≥ 62 ore consecutive, dentro le quali devono
> ricadere almeno 2 giorni solari interi. I 2 giorni solari sono
> compresi nelle 62 ore, non aggiuntivi."

Esempio: ultimo turno termina sabato 14:00 → riposo deve durare almeno
62h (martedì ~04:00) E includere domenica + lunedì interi.

## Scope

### In scope MVP — opzione γ "validatore strutturale del turno"

- Il validatore opera sul `TurnoPdc` (= ciclo di N giornate ricorrenti)
  e verifica che la STRUTTURA del turno sia compatibile con §11.4.
- Per ogni coppia di giornate consecutive (1→2, ..., N-1→N, N→1
  wrap-around) calcola il gap fra `fine_prestazione` della prima e
  `inizio_prestazione` della seconda, sommando le notti intermedie.
- Identifica i "riposi settimanali" (gap ≥ 62h) nel ciclo.
- Verifica:
  1. Esiste almeno 1 riposo settimanale ogni 7 giornate del ciclo
     (ciclo 5+2: 1 riposo; ciclo 7gg: 1 riposo; ciclo 14gg: 2 riposi;
     ciclo 21gg: 3 riposi).
  2. Ogni riposo settimanale identificato include ≥ 2 giorni solari
     interi (= dura almeno 62h con 2 giorni "completi" 00:00-23:59
     dentro la finestra).
- Output: lista violazioni testuali, propagata come
  `violazioni_ciclo_extra` al persister + finisce in
  `generation_metadata_json.riposo_settimanale_violazioni`.

### Out of scope (residui legittimi)

- **Validazione persona-specifica** ("PdC X dal 15 al 21 marzo rispetta
  §11.4?"): richiede modello `AssegnazionePersonaTurnoData` che non
  esiste ancora (vedi MODELLO-DATI.md, lo Sprint 8.x non lo ha
  introdotto). Scope MR-PD7+ con il ruolo "Gestione Personale".
- **Validazione aggregata cross-turno per PdC** ("PdC X ha 2 turni
  back-to-back nelle stesse settimane, sommiamo i loro riposi?"):
  stesso modello mancante.
- **§11.2 primo giorno post-riposo non mattino**: regola
  preferenziale (§11.7), scope futuro.
- **§11.3 ultimo giorno pre-riposo finisce ≤ 15:00**: regola
  preferenziale (§11.7), scope futuro.

### Decisione utente da prendere

Per il "wrap-around" (gap fine_giornata_N → inizio_giornata_1 settimana
dopo): assumiamo cicli "perfettamente settimanali" (N divide 7 o
multiplo)? O accettiamo cicli arbitrari con wrap fittizio? Decisione
NINO conservativa: wrap-around assume che dopo `numero_giornate` giorni
il ciclo si ripeta, calcolato come "passa il numero di notti = ciclo_giorni"
+ il gap viene confrontato con §11.4. Sovra-strict per cicli irregolari.

## Architettura proposta

### File nuovo

- `backend/src/colazione/domain/builder_pdc/riposo_settimanale.py` (~150 righe)
  - Helper `_minuti_to_data_relativa(minuto_dall_inizio_giornata, giorno_relativo)
    -> tuple[int, int]` (giorno relativo, minuto-dall-inizio-giorno)
  - Helper `_giorni_solari_interi_in_finestra(start_giorno, start_min, durata_min)
    -> int` conta i giorni solari interi 00:00-23:59 dentro la finestra
  - Funzione principale `valida_riposo_settimanale(drafts: list[GiornataPdcDraft],
    ciclo_giorni: int) -> list[str]`:
    - Itera coppie consecutive con wrap (compreso N→1 wrap-around)
    - Calcola gap minuti fra fine_prestazione[i] e inizio_prestazione[i+1]
      (con wrap-day se inizio_prestazione[i+1] < fine_prestazione[i])
    - Identifica riposi settimanali (gap ≥ 62*60)
    - Per ognuno verifica numero giorni solari interi
    - Conta riposi vs `expected = max(1, ciclo_giorni // 7)`
    - Costruisce violazioni testuali

### File modificati

- `backend/src/colazione/domain/builder_pdc/deposito_first.py`:
  - `genera_turni_pdc_deposito_first` chiama `valida_riposo_settimanale`
    DOPO `_verifica_unicita_intra_turno` (riga 579), prepende a
    `violazioni_extra`
- `backend/src/colazione/domain/builder_pdc/giornata_base.py`:
  - facade re-esporta `valida_riposo_settimanale` per accesso pubblico

### Test

`backend/tests/test_riposo_settimanale.py` (nuovo, ~200 righe):
1. `test_helper_giorni_solari_finestra_62h_da_sabato_14_include_dom_lun`:
   start sabato 14:00, durata 62h → conta 2 giorni solari (dom + lun).
2. `test_helper_giorni_solari_finestra_62h_da_dom_10_include_lun_mar`:
   start domenica 10:00, durata 62h → 2 giorni interi (lun + mar).
3. `test_helper_giorni_solari_finestra_50h_no_include`: 50h < 62 → 1
   solo giorno intero.
4. `test_validatore_ciclo_5gg_riposo_62h_2gg_interi_ok`: ciclo 5
   giornate (LMXGV), wrap dom-mar 64h con dom+lun interi → no violazione.
5. `test_validatore_ciclo_5gg_riposo_60h_solo_1_giorno_intero_ko`:
   wrap 60h con solo dom intero → violazione "2 gg solari interi".
6. `test_validatore_ciclo_5gg_riposo_30h_ko_no_settimanale`: wrap 30h →
   violazione "no riposo settimanale".
7. `test_validatore_ciclo_7gg_richiede_1_riposo_settimanale`: 7
   giornate consecutive con 1 riposo settimanale ammesso (gap dopo
   giornata 7 = wrap).
8. `test_validatore_ciclo_14gg_richiede_2_riposi_settimanali_ok`: 14
   giornate con 2 riposi (uno dopo G7 e uno dopo G14 wrap) → ok.
9. `test_validatore_ciclo_14gg_solo_1_riposo_ko`: 14 giornate ma solo
   1 gap ≥ 62h → violazione.
10. `test_validatore_drafts_vuoti_no_crash`: edge case lista vuota.

## Cose verificate

1. ✅ NORMATIVA-PDC §11.4 testo letterale letto e capito.
2. ✅ `GiornataPdcDraft` ha `inizio_prestazione: time` e
   `fine_prestazione: time` (verificato builder.py:160-161).
3. ✅ `numero_giornata: int` (1-based) presente in `GiornataPdcDraft`.
4. ✅ Per il wrap-around il calcolo gap usa modulo 24h e somma
   `(ciclo_giorni - giornate_lavorative_nella_settimana_corrente)*24*60`.
5. ✅ Compatibilità con `MR-PD7a §15 intra-turno` (entry 274) e MR-PD-FIX-SEVERO
   3b §15 cross-PdC (entry 279): §11.4 è ortogonale (riguarda gap
   temporali, non assegnazione segmenti).

## Cose da decidere prima del codice

1. **Wrap-around ciclo arbitrario**: per ciclo 5gg, dopo G5 il PdC
   riposa fino a G1 settimana dopo. Quanto dura? Assumiamo "fino a G1
   stessa fascia oraria 7 giorni dopo l'inizio G1 della settimana
   precedente"? O "fino a G1 settimana dopo, con stessa ora di presa"?
   Decisione NINO conservativa: il wrap calcola
   `gap_min = (24*(ciclo_giorni - n_giornate_attive_nella_settimana))
   - fine_prestazione_G_N + inizio_prestazione_G_1 (settimana dopo)`.
   Per ciclo 5gg con LMXGV: 5 giornate lavorative + 2 di riposo (S+D) →
   wrap = 2*24*60 + (24*60 - to_min(fine_G5)) + to_min(inizio_G1).
2. **Cicli ≥ 7gg multi-settimana**: validatore deve identificare i
   "punti di riposo" interni. Heuristic MVP: ogni gap ≥ 62h è un
   candidato, conteggia tutti i candidati, deve essere ≥
   `ciclo_giorni // 7`.
3. **Edge case solo 1 giornata**: ciclo 1gg = wrap su sé stesso = gap
   = 24h - prestazione. Probabilmente sempre violato (24h < 62h):
   genera 1 violazione. Ok intenzionale.

## Costo stimato

- `riposo_settimanale.py` modulo nuovo: 1.5h (helper + funzione + edge case)
- Test 10 scenari: 1.5h
- Modifiche `deposito_first.py` + `giornata_base.py` (1 chiamata + 1
  re-export): 30 min
- Build/mypy/ruff/commit/deploy/TN-UPDATE: 30 min

**Totale: 4h netti**. In linea con stima α 4-6h.

## Domande per SEVERO

1. **Opzione γ "validatore strutturale del turno"** vs validatore
   persona-specifico: scope MVP legittimo o pigrizia mascherata?
   Modello assegnazione persona è davvero out-of-scope o è scrivibile
   in <2h?
2. **Calcolo wrap-around**: l'assunzione "ciclo 5+2 = wrap S+D dopo
   G5" è realistica per Trenord? O i cicli sono più variabili (es.
   alcuni turni 5+2, altri 6+1, altri irregolari)?
3. **Conteggio giorni solari interi**: definizione "giorno solare
   intero" = 24h consecutive 00:00-23:59 dentro la finestra di riposo.
   È la lettura corretta di §11.4 o c'è ambiguità (es. tolleranza ±N
   minuti, mezzogiorno-mezzogiorno, ecc.)?
4. **Cicli > 7gg multi-settimana**: heuristic "≥ ciclo // 7 riposi
   settimanali" vs algoritmo più sofisticato (es. "il riposo deve
   cadere ogni 7 giornate non più tardi"). Il primo è semplice ma
   sovra-permissivo (può accumulare 2 riposi vicini e lasciare
   un gap di 14gg senza riposo). Il secondo è più rigoroso.
5. **Compatibilità con varianti calendariali**: il validatore lavora
   su `drafts: list[GiornataPdcDraft]` che non ha date concrete.
   Per validare "include 2 giorni solari interi" servono date concrete
   (es. "domenica" e "lunedì") oppure è sufficiente "≥ 48h interi
   dentro la finestra"? Decisione NINO conservativa: usiamo "≥ 48h
   interi" come proxy (evita helper `enumera_date_giornata` ancora
   mancante S4 entry 279).

## Output atteso da SEVERO

Critica preventiva su questo piano. Se voto ≥ 7/10 procediamo
all'implementazione. Se voto < 7/10 modifichiamo il piano (iterazione
1-2 max). Format canonico SEVERO + file in `docs/critiche/`.
