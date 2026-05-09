# AUDIT NORMATIVA PIANIFICATORE TURNO PdC — 2026-05-09

> **Output di MR-D1** dello Sprint 8.2 (Strada B TDD from-scratch
> deposito-first). Audit del builder PdC esistente vs
> `docs/NORMATIVA-PDC.md`, con focus sulle **4 violazioni dichiarate
> dall'utente** + verifica delle altre regole §3-§11.

## Scope

L'utente ha dichiarato 4 violazioni concrete (2026-05-09):

> "non inserisci il vincolo della condotta, non inserisci le vetture
> di rientro in deposito non associ i turni ai depositi e soprattutto
> non chiudi mai i turni nella località di deposito."

A queste si aggiungono regole §3-§11 della NORMATIVA non implementate
dal builder MVP corrente. Lo Sprint 8.2 (Strada B) le copre tutte.

## File esaminati

- `backend/src/colazione/domain/builder_pdc/builder.py` (1242 LOC) —
  builder monolitico, entry point `genera_turno_pdc`
- `backend/src/colazione/domain/builder_pdc/multi_turno.py` (1274 LOC)
  — builder DP multi-turno, entry point `genera_turni_pdc_multi`
- `backend/src/colazione/domain/builder_pdc/split_cv.py` — split CV
  intermedio (Sprint 7.4 aperto MR 2)
- `backend/src/colazione/domain/builder_pdc/simulazione.py` — preview
  senza persist
- `backend/src/colazione/integrations/live_arturo.py` — client API
  `live.arturo.travel` per vetture
- `backend/src/colazione/models/turni_pdc.py` — modello SQLAlchemy

## Le 4 violazioni dichiarate dall'utente

### Violazione A — Cap condotta 5h30 (330 min) non rispettato

**Regola** (NORMATIVA §3 + §6): condotta totale per giornata ≤ 330 min.

**Stato builder monolitico** (`builder._build_giornata_pdc:172-361`):
- Costruisce 1 giornata con TUTTI i blocchi del giro materiale.
- **NON spezza** la giornata se condotta totale > 330 min.
- `builder.py:343-344` segnala violazione `condotta_max:>330` ma è
  **annotazione testuale**, non vincolo HARD.
- Risultato: turno persistito con condotta > 330 → violazione attiva
  su DB.

**Stato builder multi-turno** (`multi_turno._dp_segmenta_giornata:167-244`):
- DP che cerca di spezzare la giornata ai punti `stazioni_cv`.
- `_segmento_valido` esclude segmenti con condotta > 330.
- **MA**: se nessuna segmentazione valida → fallback a 1 turno
  monolitico fuori cap (`multi_turno.py:629-630`).
- → violazione comunque possibile.

**Severità**: HIGH. Soluzione di costruzione mancante (HARD constraint
vs annotazione).

### Violazione B — Turno non associato al deposito (`deposito_pdc_id NULL`)

**Regola** (NORMATIVA §2.3): ogni PdC appartiene a uno dei 25 depositi.
Il turno PdC è generato per un deposito specifico.

**Stato modello** (`models/turni_pdc.py:51-53`):
- `deposito_pdc_id: Mapped[int | None]` → **NULLABLE**.
- Sprint 7.9 MR η ha aggiunto il campo come opzionale per backward
  compat.

**Stato builder** (`builder.genera_turno_pdc:543-552`):
- Parametro `deposito_pdc_id: int | None = None` → **opzionale**.
- Se chiamato senza, persiste turno con `deposito_pdc_id=NULL`.

**Severità**: HIGH. Vincolo NOT NULL mancante a livello modello +
builder.

### Violazione C — Turno non chiude in stazione deposito

**Regola** (NORMATIVA §2.3): "il PdC rientra sempre al proprio
deposito di appartenenza" (eccezione: FR g1, ma g2 chiude al
deposito).

**Stato builder monolitico** (`builder._build_giornata_pdc:352-353`):
- `stazione_fine=ultimo.stazione_a_codice` — è la stazione dell'ULTIMO
  BLOCCO CONDOTTA del giro materiale, NON del deposito.
- Esempio: giro Mi.Centrale → Tirano. Builder PdC monolitico →
  `stazione_fine=TIRANO` invece di `=MILANO_PG` (deposito).

**Stato builder multi-turno** (`multi_turno._scegli_deposito_per_segmento:271-371`):
- Sceglie depot in base ad apertura/chiusura segmento.
- Aggiunge vettura RIENTRO se chiusura ≠ depot
  (`multi_turno._valuta_candidato:464-479`).
- Se vettura non disponibile → DORMITA flag (= FR forzato).
- `stazione_fine` resta la stazione del lavoro produttivo, NON del
  deposito. La chiusura "casa" è solo la heuristic del depot, non un
  invariante del modello.

**Severità**: HIGH. Builder costruisce su modello "tagliare il giro
materiale", non "ciclo casa-casa".

### Violazione D — Vetture rientro mancanti

**Regola** (NORMATIVA §7.2): priorità rientro = vettura → MM
(Milano se sfora 8h30) → VOCTAXI.

**Stato builder monolitico** (`builder._build_giornata_pdc:269-295`):
- Ultimo blocco generato: ACCa + FINE.
- **NESSUN blocco VETTURA in coda** — anche se la giornata termina
  lontano dal deposito.

**Stato builder multi-turno** (`multi_turno._valuta_candidato:464-479`):
- Aggiunge VETTURA solo se `live.arturo.travel` restituisce un treno
  utile.
- **Niente fallback MM (Milano) o VOCTAXI** quando l'API non risponde
  o nessun treno è in finestra.
- Conseguenza: turni che terminano lontano dal deposito senza vettura
  → blocco FINE generato a stazione X (non deposito), DORMITA flag
  impostato, nessun MM/VOCTAXI generato.

**Severità**: HIGH. Manca la priorità §7.2 completa (solo step 1
vettura, niente step 2 MM e step 3 VOCTAXI).

## Altre regole NORMATIVA §3-§11 — stato

| Regola | Stato | Implementazione attuale | Note |
|---|---|---|---|
| §3.2 15' pre/post vettura ai bordi | ❌ | non esistente | bordo turno con vettura → presa servizio = vettura.partenza − 15min |
| §3.3 ACCp 80' preriscaldo dic-feb | ❌ | costante fissa 40 | branch stagionale necessario |
| §3.4 ACC vs CV vs PK in base a gap | ⚠️ parziale | builder MVP usa SOLO PK in mezzo | manca scelta CV/ACC/PK §6 |
| §6 PK opt-in operatore >300' | ❌ | non esistente | flag UI + builder branch |
| §7.2 vettura → MM → VOCTAXI | ❌ | solo vettura, no MM/VOCTAXI | violazione D |
| §7.3 condotta come rientro produttivo | ❌ | non esistente | ranking score: prima condotta possibile, poi vettura |
| §9 CV intermedi efficiency | ⚠️ aperto Sprint 7.4 | `split_cv.py:27-28` "Limitazione MVP" | **Sprint 8.3** |
| §10 FR struttura g1+g2 unica unità | ❌ | turno = 1 giornata indipendente | **Sprint 8.3** (refactor modello multi-giornata) |
| §10.6 FR cap 1/sett + 3/28gg | ✅ | `_calcola_violazioni_cap_fr` (Sprint 7.9 MR η) | OK |
| §11.2 primo giorno post-riposo non mattino | ❌ | non esistente | builder ignora context ciclo |
| §11.3 ultimo giorno pre-riposo ≤15:00 | ❌ | non esistente | idem |
| §11.4 riposo settimanale ≥62h+2gg solari | ❌ | non esistente | idem |
| §15 unicità no doppioni | ❌ | non verificato | constraint DB / validazione |

## Mappa MR Strada B → copertura violazioni

- **MR-D1** *(questo)*: audit + fixture E2E red-phase TDD (3 test
  xfail su Violazioni A/C/D)
- **MR-D2**: schema esteso (blocchi MM/VOCTAXI + `deposito_pdc_id NOT NULL`
  via migration alembic) — copre B
- **MR-D3**: builder `deposito_first.py` con modello "ciclo casa-casa"
  per costruzione (cap condotta HARD + chiusura deposito GARANTITA +
  vettura_resolver §7.2 + §3.2 + §3.3 + §6 + §7.3) — copre A, C, D +
  metà delle altre regole
- **MR-D4**: i test red di MR-D1 diventano green sul nuovo builder
- **MR-D5**: migrazione endpoint `genera-turno-pdc` al nuovo builder,
  vecchio deprecato
- **MR-D6**: Gantt PdC riscritto stile giro + palette per tipo
- **MR-D7**: §11.2/§11.3/§11.4/§15 + altri da audit

## Sprint 8.3 dichiarato (residui con motivazione oggettiva)

- **§9 CV intermedi efficiency** — Sprint 7.4 dichiarato aperto in
  `split_cv.py:27-28`. Refactor split_cv autonomo, fuori scope 8.2.
- **§10 FR struttura g1+g2 unica unità** — richiede refactor modello
  dati turno multi-giornata (oggi `TurnoPdcGiornata` è 1 giornata
  indipendente). Fuori scope 8.2 per disaccoppiare il refactor
  modello dal refactor builder.

## Riferimenti

- Test red-phase: `backend/tests/test_violazioni_normative_pdc.py`
- Critica preventiva plan: `docs/critiche/SPRINT-8.2-PLAN-PIANIFICATORE-PDC-revisione.md`
- Normativa fonte: `docs/NORMATIVA-PDC.md`
