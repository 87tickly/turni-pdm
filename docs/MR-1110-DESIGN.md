# MR-1110 — Design del nuovo modello "turno = giornate-tipo + varianti calendariali"

> **Stato**: 📐 specifica aperta (Step 0). Niente codice scritto su questo
> tema finché lo specchio del documento non è approvato dall'utente.
>
> **Apertura**: 2026-05-06, decisione utente in chat.
>
> **Modello target di riferimento**: PDF "Turno Materiale Trenord dal
> 2/3/26", turno 1110 (TSR 3pz, sede MILANO FIORENZA, composizione
> `2ALe711+1ALe710`). La pagina della giornata 6 di quel turno è
> l'esempio canonico del comportamento che il nuovo builder deve
> produrre. Vedi §6.1 per il dettaglio acceptance.
>
> ⚠️ **Greenfield**: il PDF Trenord è **riferimento concettuale**, non
> fonte di estrazione. Decisione utente 2026-05-06: *"NOI non dobbiamo
> estrarre niente, dobbiamo inventarlo noi il metodo, sulla base di e
> come esempio di ciò che avviene oggi"*. L'algoritmo nuovo deve
> produrre output **della stessa forma** del PDF, partendo dal PdE
> commerciale (corse + periodicità) e dai vincoli operativi del
> programma.

---

## 1. Premessa: perché questo MR

### 1.1 Cosa fa oggi il builder (sintesi onesta)

Pipeline attuale (`backend/src/colazione/domain/builder_giro/`):

1. **`multi_giornata.py:_costruisci_giri_per_data`** — per ogni data
   del periodo costruisce un *giro-tentativo* prendendo **giornate
   consecutive di calendario**: G1 = giorno X, G2 = X+1, …, GN = X+N−1.
   Marca le catene come `visitate` → mai sfasate.
2. **`multi_giornata.py:_cluster_giri_a1`** — fonde giri-tentativo
   con **sequenza di treni IDENTICA** (chiave A1 strict: numero treno
   + orari + origine/destinazione). Una micro-variazione genera un
   cluster nuovo.
3. **`fusione_cluster_a1.py:fonde_cluster_simili`** (MR 12) —
   riassorbe i cluster A1 simili (Jaccard ≥ 0.7 sui treni)
   **scartando** le micro-differenze di sequenza per evitare
   "giornate festive isolate con un treno".
4. **`aggregazione_a2.py:aggrega_a2`** — raggruppa i cluster A1
   sopravvissuti per `(materiale, sede, n_giornate)` e fa bin-packing
   per date disgiunte → varianti della stessa giornata-tipo se le
   date non si sovrappongono.

Risultato osservato sul giro 271 in produzione: turno con 7 giornate
"di calendario" ognuna con **1 sola variante**, etichetta
`Lv/Lv/Lv/Lv/Lv/P/F` mappata 1:1 sui giorni della settimana di
partenza. Le micro-varianti calendariali (festività rare, eccezioni
puntuali, periodi stagionali) sono **assorbite o disperse** in turni
separati.

### 1.2 Perché non basta più

Il modello operativo Trenord (PDF "Turno Materiale dal 2/3/26",
353 pagine, 54 turni 2026) usa una struttura diversa:

> **Un turno** = N giornate-tipo (G1, G2, …, GN) **concatenate
> ciclicamente**. Ogni G_K ha M varianti calendariali distinte. Il
> turno è applicato a N convogli paralleli sfasati di 1 giornata
> ciascuno: oggi convoglio A è in fase G1, B in G2, …, N-esimo in GN;
> domani A in G2, B in G3, …, N-esimo in G1.

Il vincolo della **minimizzazione materiali** è il punto chiave
(decisione utente 2026-05-06): se il turno ha N giornate-tipo
concatenate, bastano N convogli per coprire tutti i servizi. Senza
concatenazione esplicita servirebbero `n_treni_giornalieri` convogli
→ spreco di flotta.

Numeri reali dal dump `data/turni_materiale_2026_dump.json`:

| Turno | N giornate | N pezzi/componente | N treni coperti | Rapporto |
|---|---|---|---|---|
| 1104 (MDVE/MDVC stagionale) | 1 | 1 | 17 | 17×|
| 1115 (ATR803) | 7 | 7 | 44 | 6.3×|
| 1132 (ETR204 Donizetti) | 8 | 8 | 48 | 6×|
| 1125 (ETR421/522 Caravaggio) | 17 | 17 | 251 | 14.8×|

Il rapporto compressione = treni / pezzi è il guadagno operativo
della concatenazione. Il builder attuale non lo modella: produce un
turno per pattern di sequenza, ma non identifica le N giornate-tipo
come fasi rotanti del **ciclo** del convoglio.

### 1.3 Cosa apre questo MR

Una riscrittura strutturale della pipeline builder per produrre il
modello "turno = giornate-tipo concatenate + varianti calendariali
ricche per ogni giornata-tipo", coerente con il PDF Trenord e con
il vincolo operativo della minimizzazione materiali.

Niente fix di una riga. Niente patch. **Riscrittura della
specifica concettuale del builder**.

---

## 2. Modello target — definizioni formali

### 2.1 Giornata-tipo (G_K)

Una **giornata-tipo** del turno è una *fase del ciclo* attraversata
da un convoglio durante il turno. È identificata univocamente da:

- `posizione_ciclo` (intero 1-based, K ∈ {1, …, N}): la sua posizione
  nel ciclo concatenato.
- `materiale_tipo_codice`: il tipo di rotabile (ETR421, ETR522,
  ETR204, …).
- `localita_codice`: la sede di manutenzione del turno (FIO, NOV,
  CRE, …).
- **Identità di fase**: una coppia `(staz_inizio, staz_fine)` che il
  convoglio attraversa quando è in fase G_K. Più precisamente, la
  giornata-tipo "vive" tra una stazione di aggancio in entrata
  (uscita di G_(K-1) o sede manutenzione se K=1) e una stazione di
  aggancio in uscita (entrata di G_(K+1) o sede manutenzione se
  K=N).

Una giornata-tipo **non è** una giornata di calendario. Non ha una
data fissa. Ha invece M varianti calendariali, ciascuna con la
propria `dates_apply`.

### 2.2 Variante calendariale (V_K_j)

Una **variante calendariale** della giornata-tipo G_K è un'istanza
concreta della fase, applicata a un sottoinsieme delle date del
periodo. È identificata da:

- `giornata_tipo`: riferimento al G_K di appartenenza.
- `sequenza_treni`: la sequenza ordinata di corse + vuoti tecnici
  (testa/coda) che il convoglio percorre quando in fase G_K **in
  quelle specifiche date**.
- `dates_apply`: insieme di date in cui questa variante si applica.
  Disgiunto dalle dates_apply delle altre varianti dello stesso G_K.
- `etichetta_calendariale`: stringa parlante che descrive le date
  (es. `"LV 1:5"`, `"F escluso FpF ed escl. 22/3, 12/4"`,
  `"Si eff. 1/5 e 2/6"`, `"Circola Sabato Festivo"`, `"Solo
  21/3"`). Vedi §5 per il formato.
- `prestazione_minuti`: durata totale del servizio in minuti
  (l'attuale "Per" del PDF Trenord, in ore o minuti).
- `km_giornaliera`: km percorsi nella variante.

**Invariante 1**: tutte le varianti V_K_j di una stessa G_K
condividono `(staz_inizio, staz_fine)` di fase, anche se la
sequenza interna è molto diversa. Questa è la regola che
identifica "appartenenza alla stessa fase".

**Invariante 2**: la sequenza-treni può essere arbitrariamente
diversa fra varianti (esempio reale dal turno 1110 / G6: variante
`Si eff. 22/3, 12/4` ha km=0 e fa solo manovra interna MCPTC,
mentre `LV 1:5` fa VARESE↔MI.CERT con 4 treni). Il criterio di
appartenenza alla giornata-tipo **non è la similarità di
sequenza**.

### 2.3 Concatenazione ciclica

Le giornate-tipo del turno formano una **catena ciclica**:

```
G1 → G2 → G3 → … → GN → G1 → …
```

Vincolo di concatenazione: per ogni K, la stazione di fine di
G_K deve coincidere con la stazione di inizio di G_(K+1)
(modulo N). Per K=N, la stazione di fine deve essere la stazione
di inizio di G1 — il convoglio dopo GN ricomincia il ciclo.

**Caso degenere (N=1)**: il turno ha 1 sola giornata-tipo che si
auto-concatena (staz_fine_G1 = staz_inizio_G1). Esempio reale:
turno 1104 stagionale.

**Convogli paralleli**: il turno è applicato a N convogli sfasati.
Convoglio i ∈ {0, …, N−1} è in fase G_((d + i) mod N + 1) dove d è
l'offset della prima data di applicazione. Questa rotazione **non è
materializzata nel builder** (è gestita dal ruolo Manutenzione e dal
ruolo Personale): il builder produce solo il *modello* del turno,
con N giornate-tipo concatenate e le varianti calendariali per
ognuna.

### 2.4 Turno materiale (T)

Un **turno materiale** è quindi:

```
T = {
  materiale_tipo_codice,
  localita_codice,
  giornate_tipo: (G1, G2, …, GN),  // ordinate ciclicamente
}
```

con N ≥ 1 e tutte le G_K che soddisfano l'invariante di
concatenazione (§2.3).

L'output del builder è una **lista di turni** per il programma
materiale.

---

## 3. Cambia rispetto al modello attuale

### 3.1 Cosa rimane

| Componente | Stato |
|---|---|
| `corse_e_catene.py` (costruzione catene giornaliere da PdE) | ✅ invariato |
| `posizionamento.py` (vuoti testa/coda, whitelist sede) | ✅ invariato |
| `composizione.py` (assegnazione composizioni a blocchi corsa) | ✅ invariato |
| Schema DB `giro_materiale + giro_giornata + giro_blocco` con `dates_apply` | ✅ invariato (già supporta multi-varianti) |
| `aggregazione_a2.py` (raggruppamento per chiave + bin-packing) | ⚠️ revisione parziale (§4.4) |
| `etichetta.py` (calcolo etichetta variante) | 🔄 upgrade per etichette parlanti (§5) |
| UI Gantt frontend | 🔄 upgrade per mostrare etichette parlanti + Per/Km per variante (§7) |

### 3.2 Cosa va riscritto

| Componente | Cosa cambia |
|---|---|
| `multi_giornata.py:_costruisci_giri_per_data` | Sostituire la "concatenazione di giornate consecutive di calendario" con la "identificazione di giornate-tipo del ciclo" |
| `multi_giornata.py:_cluster_giri_a1` | Sostituire il chiavaggio "identità sequenza" con il chiavaggio "identità di fase (staz_inizio, staz_fine)" |
| `fusione_cluster_a1.py` (MR 12 Jaccard 0.7) | **Deprecare**: la fusione Jaccard scarta le micro-varianti che ora vogliamo tenere come varianti calendariali distinte (§4.5) |
| `etichetta.py:calcola_etichetta_variante` | Riscrivere per produrre etichette parlanti stile PDF Trenord (`LV 1:5`, `F escl. ...`, `Si eff. ...`, `Circola Sabato Festivo`) |

### 3.3 Cosa va aggiunto

| Componente | Funzione |
|---|---|
| `domain/builder_giro/giornata_tipo.py` (nuovo) | Identificazione delle giornate-tipo del ciclo dalle catene |
| `domain/builder_giro/concatenazione_ciclica.py` (nuovo) | Costruzione dell'ordine ciclico G1 → G2 → … → GN → G1 |

---

## 4. Algoritmo proposto (alto livello)

### 4.1 Pipeline a 5 step

```
PdE (corse commerciali)                                   [INPUT]
        │
        ▼
[Step 1] catene_giornaliere.py                          [INVARIATO]
        │  CatenaPosizionata × data
        ▼
[Step 2] giornata_tipo.py (NUOVO)
        │  GiornataTipo  ← cluster di catene per identità di fase
        ▼
[Step 3] varianti_calendariali.py (NUOVO o accorpato in §2)
        │  GiornataTipo × M VarianteCalendariale
        ▼
[Step 4] concatenazione_ciclica.py (NUOVO)
        │  Turno = (GiornataTipo, …) ciclicamente ordinati
        ▼
[Step 5] aggregazione_finale.py (≈ aggregazione_a2 rivisto)
        │  Turno × N_pezzi (un turno = un pattern di flotta)
        ▼
TurnoMateriale persistito                                [OUTPUT]
```

### 4.2 Step 2 — Identificazione giornate-tipo

**Input**: lista di `CatenaPosizionata` × data (output dello Step 1
esistente).

**Output**: lista di `GiornataTipo`, ognuna con:
- `staz_inizio`, `staz_fine` (l'identità di fase)
- `materiale_tipo_codice`, `localita_codice`
- lista delle catene-istanza che vi appartengono, ognuna con la sua
  data di applicazione

**Algoritmo**:

1. Per ogni catena C, estrai la sua coppia di fase
   `(C.staz_inizio, C.staz_fine)` (= origine prima corsa, destinazione
   ultima corsa).
2. Raggruppa le catene per chiave `(materiale_tipo_codice,
   localita_codice, staz_inizio, staz_fine)`.
3. Ogni gruppo non-vuoto è una **giornata-tipo candidata**.
4. **Filtro di significatività** (per evitare giornate-tipo "rumore"
   da catene rare/orfane): scarta i gruppi con
   `len(catene) < soglia_min_istanze`. Default: 2 (almeno 2 date di
   applicazione per essere considerata una giornata-tipo del ciclo).
   Le catene scartate finiscono nelle "corse residue" del programma.

**Decisione aperta D1**: la chiave di fase è solo
`(staz_inizio, staz_fine)` o include anche un proxy della "famiglia
di servizio" (es. linea, codice servizio commerciale)? Vedi §8.

### 4.3 Step 3 — Varianti calendariali per giornata-tipo

**Input**: una `GiornataTipo` con la sua lista di catene-istanza × data.

**Output**: la `GiornataTipo` arricchita con M `VarianteCalendariale`,
dove M è il numero di sequenze-treni distinte trovate.

**Algoritmo**:

1. Per ogni catena-istanza, calcola la chiave-sequenza:
   `tuple((corsa.numero_treno, corsa.ora_partenza_min,
   corsa.ora_arrivo_min) for corsa in catena)`.
2. Raggruppa le istanze per chiave-sequenza.
3. Ogni gruppo è una **variante calendariale**:
   - `sequenza_treni` = la chiave-sequenza
   - `dates_apply` = unione delle date delle istanze del gruppo
   - `prestazione_minuti` = derivato dalla sequenza
   - `km_giornaliera` = somma dei km della sequenza
4. **Etichetta calendariale**: chiama `etichetta.py:genera_etichetta_parlante`
   passando `dates_apply` + `periodo_completo` + `festivita` (vedi §5).

**Nota**: niente fusione Jaccard. Le sequenze diverse restano varianti
distinte. Se due varianti hanno sequenza identica si fondono per
costruzione (stesso gruppo allo step 2).

### 4.4 Step 4 — Concatenazione ciclica

**Input**: lista di `GiornataTipo` candidate (output Step 2-3).

**Output**: lista di `Turno`, ognuno una sequenza ordinata di
giornate-tipo concatenate ciclicamente.

**Algoritmo (greedy con backtracking)**:

1. Raggruppa le `GiornataTipo` per `(materiale_tipo_codice,
   localita_codice)`. Ogni gruppo è candidato a formare uno o più
   turni.
2. Per ogni gruppo, costruisci un grafo orientato:
   - nodi = giornate-tipo del gruppo
   - archi: G_a → G_b se `G_a.staz_fine == G_b.staz_inizio`
3. Trova **cicli hamiltoniani** (= cicli che attraversano tutte le
   giornate-tipo esattamente una volta). Per gruppi piccoli (≤ 17
   giornate, vedi turno 1125) il problema è trattabile con una
   ricerca esaustiva o branch-and-bound.
4. Se nessun ciclo hamiltoniano esiste, scomponi in cicli più piccoli
   (più turni dello stesso materiale/sede).
5. Ogni ciclo è un `Turno` con `giornate_tipo` ordinati.

**Caso degenere (N=1)**: un turno con 1 sola giornata-tipo dove
`staz_fine == staz_inizio` (il convoglio "si chiude su se stesso"
ogni notte tornando dove era partito al mattino). Esempio: turno
1104 con 1 giornata-tipo Albenga↔Bergamo↔Milano stagionale.

**Decisione aperta D2**: cosa fare se non c'è ciclo hamiltoniano e
la decomposizione produce più cicli piccoli? Sono "più turni" o
"un turno con sotto-cicli"? Vedi §8.

### 4.5 Deprecazione fusione MR 12

`fusione_cluster_a1.py:fonde_cluster_simili` (Jaccard ≥ 0.7) era
stato introdotto per risolvere il problema "il cluster perde treni
nelle varie varianti, crea giornate festive con un treno isolato"
(decisione utente 2026-05-03 entry 114).

Con il nuovo modello quel problema **non esiste più**: le micro-
varianti sono **tenute come varianti calendariali distinte** della
stessa giornata-tipo, e l'utente le vede tutte nella UI Gantt sotto
G_K (esattamente come la pagina G6 del turno 1110 mostra 6 varianti).

**Azione**: deprecare il modulo. Tenerlo per backward compatibility
del clustering legacy, ma non chiamarlo dalla nuova pipeline.
Documentare in `TN-UPDATE.md` che la decisione 2026-05-03 entry 114
è stata superata dal modello MR-1110.

**Sostituto**: il filtro di significatività dello Step 2
(`soglia_min_istanze`) rimuove le giornate-tipo "rumore" da catene
sporadiche prima ancora che diventino varianti.

---

## 5. Etichette calendariali parlanti

### 5.1 Stato attuale

`etichetta.py:calcola_etichetta_variante` produce 5 categorie:
`Lavorativo` / `Prefestivo` / `Festivo` / `Solo DD/M/YY` / `Misto:
Lv+F (N date)`. Sufficiente per il modello attuale, **insufficiente**
per replicare il PDF Trenord.

### 5.2 Etichette target (dal turno 1110 G6)

| Etichetta PDF | Significato semantico |
|---|---|
| `LV 1:5` | Lavorativo dal 1° al 5° giorno settimana (lun-ven) |
| `LV 6` | Lavorativo del 6° giorno settimana (sabato lavorativo) |
| `F escluso FpF ed escl. 22/3, 12/4, 1/5 e 2/6` | Festivo escluso "primo/ultimo del periodo" (FpF) ed escluso 4 date specifiche |
| `Circola Sabato Festivo` | Si applica nei sabati festivi (sabato + festività ufficiale) |
| `Si eff. 22/3, 12/4` | Si effettua solo le 2 date elencate |
| `Si eff. 1/5 e 2/6` | Si effettua solo le 2 date elencate |

### 5.3 Algoritmo `genera_etichetta_parlante`

**Input**:
- `dates_apply: frozenset[date]` (le date della variante)
- `periodo_completo: tuple[date, date]` (validità del programma)
- `festivita: frozenset[date]` (festività azienda)
- `categoria_per_data: dict[date, "lavorativo" | "prefestivo" |
  "festivo"]` (precomputato)

**Output**: stringa parlante.

**Logica decisionale** (priorità top-down):

1. **N=0** → `"(nessuna data)"`.
2. **N=1** → `"Solo DD/M/YY"` (come oggi).
3. **N piccolo (≤ soglia, default 5)** e dates non spiegabili come
   pattern → `"Si eff. DD/M, DD/M, …"`.
4. **Tutte le date ∈ lavorativi 1-5** del periodo (lun-ven escluso
   sabato lavorativo) → `"LV 1:5"` (eventualmente con esclusioni:
   `"LV 1:5 escl. DD/M"` se mancano N≤soglia date).
5. **Tutte le date ∈ sabati lavorativi** del periodo → `"LV 6"`.
6. **Tutte le date ∈ sabati festivi** (sabato che cade festività) →
   `"Circola Sabato Festivo"`.
7. **Tutte le date ∈ festivi** del periodo escluse N≤soglia →
   `"F esclusi <date>"`. Se le date escluse coincidono con i **FpF
   del periodo** (`Festivo precedente Festivo` = festivo che precede
   un altro festivo consecutivo, es. Pasqua → Pasquetta, Natale →
   S.Stefano), esprimila come `"F escluso FpF"`. Se ci sono
   *entrambe* esclusioni FpF e date specifiche, joinare:
   `"F escluso FpF ed escl. <date>"`. Calcolo FpF: vedi §8.2 D4.
8. **Tutte le date in una finestra continua [d_inizio, d_fine]**
   → `"Dal DD/M al DD/M"`.
9. **Mix di categorie** → fallback: `"Misto: <sigle> (N date)"`.

Tutti i formati data usano la convenzione Trenord: `D/M` (no zero
leading, no anno a meno che N=1).

### 5.4 Test acceptance per il modulo etichetta

Riprodurre **esattamente** le 6 etichette del turno 1110 G6 dato un
input di `dates_apply` corrispondenti. È un test concettuale: i
valori reali di `dates_apply` saranno determinati dal periodo del
PdE 2026 (validità 2/3/26 → fine PdE).

---

## 6. Esempi acceptance

### 6.1 Turno 1110 / Giornata 6 (riferimento canonico)

**Specifica del PDF**:

- Turno 1110, sede MILANO FIORENZA, materiale `2ALe711+1ALe710`
  (TSR 3pz - m.79).
- Validità "P" (periodica = tutto il PdE).
- Numero giornate ≥ 6 (la pagina G6 esiste).
- G6 ha **6 varianti calendariali** distinte (vedi tabella §1.2 chat
  precedente).

**Forma di output attesa dal nuovo builder**:

```python
Turno(
    materiale_tipo_codice="2ALe711+1ALe710",
    localita_codice="FIO",
    giornate_tipo=(
        GiornataTipo(
            posizione_ciclo=1,
            staz_inizio=...,
            staz_fine=...,
            varianti=(...),
        ),
        # ... G2, G3, G4, G5
        GiornataTipo(
            posizione_ciclo=6,
            staz_inizio="VARESE",   # ipotesi dal PDF
            staz_fine="VARESE",     # ipotesi dal PDF — torna a Varese
            varianti=(
                VarianteCalendariale(
                    etichetta="LV 1:5",
                    sequenza_treni=("24519", "28140i", ..., "MCPTC loop"),
                    dates_apply=frozenset(<lavorativi lun-ven del periodo>),
                    prestazione_minuti=360,  # 6h
                    km_giornaliera=131.57,
                ),
                VarianteCalendariale(
                    etichetta="F escluso FpF ed escl. 22/3, 12/4, 1/5 e 2/6",
                    sequenza_treni=("MCPTC loop", "28129i", "24576", ...),
                    dates_apply=frozenset(<festivi del periodo escl. 22/3, 12/4, 1/5, 2/6, primo, ultimo>),
                    prestazione_minuti=360,
                    km_giornaliera=131.57,
                ),
                VarianteCalendariale(
                    etichetta="LV 6",
                    sequenza_treni=("24519", "28140i", ..., "MCPTC loop"),
                    dates_apply=frozenset(<sabati lavorativi del periodo>),
                    prestazione_minuti=360,
                    km_giornaliera=131.57,
                ),
                VarianteCalendariale(
                    etichetta="Circola Sabato Festivo",
                    sequenza_treni=(...),  # stessa di LV 6 nel PDF
                    dates_apply=frozenset(<sabati festivi del periodo>),
                    prestazione_minuti=360,
                    km_giornaliera=131.57,
                ),
                VarianteCalendariale(
                    etichetta="Si eff. 22/3, 12/4",
                    sequenza_treni=("MCPTC loop",),  # variante minima
                    dates_apply=frozenset({date(2026,3,22), date(2026,4,12)}),
                    prestazione_minuti=120,  # 2h
                    km_giornaliera=0.0,
                ),
                VarianteCalendariale(
                    etichetta="Si eff. 1/5 e 2/6",
                    sequenza_treni=("24519", "28140i", "24576", ...),
                    dates_apply=frozenset({date(2026,5,1), date(2026,6,2)}),
                    prestazione_minuti=360,
                    km_giornaliera=263.14,  # variante "doppia"
                ),
            ),
        ),
        # ... G7, G8, ... fino a GN
    ),
)
```

### 6.2 Turno 1104 (caso degenere N=1, stagionale)

- Turno 1104, MDVE/MDVC, 1 giornata-tipo, 1 pezzo per componente.
- Validità "Valido dal 28/3 al 28/9" → variante con etichetta
  `"Dal 28/3 al 28/9"`.
- 17 treni coperti, capolinea ALBENGA / BERGAMO / MI.CERT / VENT.
- Output: `Turno(N=1)` con 1 sola `GiornataTipo` con N varianti
  (probabilmente Lv, F, eccezioni FpF dentro la finestra stagionale).

### 6.3 Turno 1125 (caso N=17, lungo)

- Turno 1125, Caravaggio (ETR421/522), 17 giornate-tipo concatenate.
- 251 treni coperti — il più grande del PdE 2026.
- 17 pezzi per componente (un convoglio per fase).
- Linee multiple (Mi-Brescia, Mi-Voghera, Mi-Como, …) → ogni
  giornata-tipo è una "fase" specifica del ciclo settimanale-bi-
  settimanale dei convogli.

Acceptance: il builder deve produrre 17 giornate-tipo con sequenza
ciclica `G1 → G2 → … → G17 → G1` rispettando il vincolo di
concatenazione `staz_fine_K == staz_inizio_(K+1)`.

---

## 7. Impatti UI Gantt

### 7.1 Cosa cambia in dashboard Pianificatore Giro Materiale

Oggi (`frontend/src/routes/pianificatore-giro/giri/...`) il Gantt
mostra 1 riga per giornata, 1 sola variante visibile. Il nuovo
modello richiede:

1. **Nesting visivo**: per ogni G_K, mostrare tutte le M varianti
   come sotto-righe collassabili (default: collassate, mostra solo
   la variante "principale" = quella con più date_apply).
2. **Etichetta parlante**: rimpiazzare i badge `Lv/P/F` con la
   stringa parlante completa (`LV 1:5`, `F escluso FpF ed escl.
   ...`, ecc.). Per stringhe lunghe, troncare con tooltip.
3. **Per/Km per variante**: mostrare i due valori a destra di ogni
   variante (oggi sono per giornata, nel PDF sono per variante —
   coerente perché nel modello attuale c'è 1 variante = 1 giornata).
4. **Indicatore di concatenazione**: piccola freccia/ponte tra G_K
   e G_(K+1) che mostri staz_fine_K = staz_inizio_(K+1). Visualizza
   il ciclo.
5. **Banner "ciclo chiuso"**: tra GN e G1, una linea di chiusura
   visibile che dica "il convoglio dopo GN ricomincia con G1".

### 7.2 Cosa NON cambia

Lo schema dati `giro_materiale + giro_giornata + giro_blocco` con
`dates_apply` ce l'abbiamo già. Niente migration richiesta in
questa fase iniziale — solo nuova logica di popolamento.

---

## 8. Decisioni chiuse

### 8.1 Stato

Tutte le 8 decisioni del MR-1110 sono chiuse al 2026-05-06.

| ID | Decisione | Chiusura |
|---|---|---|
| **D1** | Chiave di fase con `codice_servizio_dominante` + fallback morbido | entry 193 |
| **D2** | Ciclo rotto → multi-turno (anche 1 giornata) | entry 198 |
| **D3** | Soglia `min_istanze = 2` (default) | entry 198 |
| **D4** | FpF (Festivo precedente Festivo) calcolato auto dal calendario | entry 198 |
| **D5** | Periodo riferimento etichette = validità programma | entry 198 |
| **D6** | Concatenazione `staz_fine_K == staz_inizio_(K+1)` rigida | entry 193 |
| **D7** | Backward compat opt-in (`builder_version` per programma) | entry 193 |
| **D8** | Test misti: unit sintetici + 1-2 integration con PdE 2026 reale | entry 198 |

### 8.2 Decisioni chiuse

#### D1 — Chiave di fase con `codice_servizio_dominante`

**Risposta utente** (2026-05-06): *"sono solo informazioni in più
se non compromettono la logica va bene."*

**Decisione**: chiave di fase **estesa** =
`(materiale_tipo_codice, localita_codice, staz_inizio, staz_fine,
codice_servizio_dominante)`.

`codice_servizio_dominante` definito come:

- Il `codice_servizio_commerciale` più frequente fra le corse della
  catena (es. `S5`, `R-Mi-Brescia`, `Reg-Tirano`).
- In caso di parità, lessicograficamente minimo (deterministico).
- Se nessuna corsa della catena ha `codice_servizio_commerciale`
  popolato → `None`.

**Comportamento del clustering Step 2** (raggruppamento catene per
chiave):

- Catene con `codice_servizio_dominante` **valorizzato** vengono
  raggruppate in giornate-tipo distinte se il codice è diverso, anche
  a parità degli altri 4 campi della chiave.
- Catene con `codice_servizio_dominante = None` vengono **mescolate**
  con catene di qualsiasi servizio se gli altri 4 campi coincidono
  (fallback morbido — non frammenta in giornate-tipo "orfane senza
  servizio identificabile").

**Razionale**: l'arricchimento informativo non genera frammentazione
se il dato non è disponibile, e separa correttamente i casi reali in
cui un Reg e un RegEx insistono sullo stesso aggancio fisico ma con
differente significato commerciale.

**Rivisitazione**: se in pratica vediamo giornate-tipo eccessivamente
frammentate per via di `codice_servizio_dominante`, valutiamo un
upgrade a "match per **insieme di servizi**" (tolleranza di 1 servizio
diverso). Aperto come decisione futura, NON parte di questo MVP.

#### D6 — Concatenazione: vincolo rigido

**Risposta utente** (2026-05-06): *"assolutamente no, mai materiali
vuoti senza un senso logico."*

**Decisione**: il vincolo
`staz_fine_K == staz_inizio_(K+1)` è **RIGIDO**. Niente vuoti
notturni "di posizionamento ad hoc" inseriti dal builder fra
giornate-tipo.

**Conseguenze sull'algoritmo Step 4** (concatenazione ciclica):

- Il grafo orientato delle giornate-tipo (§4.4) ha archi
  `G_a → G_b` solo se `G_a.staz_fine == G_b.staz_inizio`. Niente
  archi "fittizi" con costo penalty.
- Se due giornate-tipo del gruppo non si concatenano per nessuna
  permutazione → finiscono in **turni distinti** (pattern di flotta
  separati). Il pianificatore vede 2+ turni invece di 1.
- I "vuoti che hanno un senso logico" già modellati DENTRO una
  giornata-tipo (es. vuoto testa/coda di una catena per
  posizionamento sede ↔ stazione di partenza commerciale) **restano
  ammessi** — sono parte della catena, non sono vuoti tra
  giornate-tipo.

**Distinzione operativa importante**:

| Tipo di vuoto | Ammesso? | Dove |
|---|---|---|
| Vuoto testa di catena (sede → prima stazione commerciale) | ✅ sì | Dentro la giornata-tipo |
| Vuoto coda di catena (ultima stazione commerciale → sede) | ✅ sì | Dentro la giornata-tipo |
| Vuoto intra-giornata (cambio area Milano fra due corse) | ✅ sì | Dentro la catena, già esistente |
| **Vuoto notturno fra G_K e G_(K+1) per agganciarle** | ❌ NO | Decisione D6 |

#### D7 — Backward compat: opt-in caso per caso

**Risposta utente** (2026-05-06): *"dipende, va valutata ogni
situazione."*

**Decisione**: niente migrazione automatica dei programmi materiali
esistenti al nuovo modello. Ogni programma resta sul suo "builder
storico" finché l'utente non chiede esplicitamente di re-runnarlo.

**Implementazione**:

- Aggiungiamo al `ProgrammaMateriale` un campo
  `builder_version: str` (default `"v1"` per i programmi esistenti).
- Nuovi programmi creati DOPO il merge di MR-1110 hanno
  `builder_version = "v2"` di default.
- L'utente può cambiare la versione di un programma esistente da UI
  tramite un'azione esplicita "Aggiorna a builder v2 (rebuild)" che
  re-runna l'intera pipeline e sovrascrive i giri persistiti. Mostra
  diff prima/dopo + warning su impatto turni PdC eventualmente
  costruiti.
- I programmi v1 continuano a essere serviti dalla pipeline storica
  (`multi_giornata` + `fusione_cluster_a1` + `aggregazione_a2` v1).
  Niente cancellazione del codice v1 finché tutti i programmi non
  sono migrati o archiviati.

**Implicazione per il sotto-MR 5** (rewrite multi_giornata):
mantenere il vecchio modulo invariato, creare il nuovo
`multi_giornata_v2.py` parallelo. Lo schema dati è uguale per
entrambe le versioni — cambia solo cosa viene popolato.

**Pulizia debito tecnico v1**: aperta come MR futuro quando l'utente
darà OK alla rimozione. Tracciato in `TN-UPDATE` come "non si
distrugge finché non è esplicito".

#### D2 — Ciclo rotto: multi-turno

**Decisione**: se le giornate-tipo di un gruppo `(materiale, sede)`
non si concatenano in un unico ciclo hamiltoniano, ogni componente
ciclica diventa un **turno separato** (anche da 1 sola giornata-tipo
auto-concatenata). Niente "sotto-cicli dentro un turno": un turno =
un ciclo coerente. Coerente con D6 rigida (niente vuoti di
posizionamento ad hoc per agganciare giornate-tipo lontane).

**Conseguenza Step 4**: l'algoritmo di concatenazione produce 1+
turni per gruppo, non un turno con sotto-strutture. Il pianificatore
vede ogni turno come unità autonoma.

#### D3 — Soglia `min_istanze = 2`

**Decisione**: default 2. Catene con 1 sola data di applicazione
finiscono nelle "corse residue" del programma — sono troppo
eccezionali per essere giornate-tipo del ciclo. Soglia 3 sarebbe più
aggressiva e perderemmo varianti calendariali legittime tipo
`"Si eff. 22/3, 12/4"` del turno 1110 G6 (esattamente 2 date).

**Configurabile** via `ParamGiornataTipo.min_istanze` per i casi
rari in cui serve ritarare.

#### D4 — FpF auto

**Definizione utente** (2026-05-06): FpF = **Festivo precedente
Festivo** = festivo che cade **immediatamente prima** di un altro
festivo. Esempi:

- **Pasqua** (domenica) → **Pasquetta** (lunedì): la domenica di
  Pasqua è FpF.
- **Natale** (25/12) → **S.Stefano** (26/12): il 25/12 è FpF.

**Decisione**: calcolato in automatico da `calendario.py` data la
lista delle festività azienda. Algoritmo:

```python
def festivi_precedenti_festivo(festivita: frozenset[date]) -> frozenset[date]:
    return frozenset(d for d in festivita if (d + timedelta(days=1)) in festivita)
```

Niente configurazione manuale per ora. Se in pratica vediamo bisogno
di forzare FpF su date "speciali" non festive (es. ponte), aprire
override esplicito come campo opzionale del `ProgrammaMateriale`.

#### D5 — Periodo riferimento = validità programma

**Decisione**: per ogni etichetta calendariale di una variante, il
periodo di confronto (= "tutti i lavorativi del periodo", "tutti i
festivi del periodo", ecc.) è la validità del **programma materiale**
(`valido_da`/`valido_a`), vincolata dalla validità del PdE base.
Stesso periodo per tutte le varianti del programma → coerenza UI.

#### D8 — Test misti

**Decisione**:

- **Unit test** (per ogni sotto-MR: `giornata_tipo`,
  `concatenazione_ciclica`, `etichetta`, `multi_giornata_v2`) con
  **fixture sintetiche** in-memory. Feedback loop veloce, niente DB,
  deterministico. Stile attuale (`test_giornata_tipo.py` 18 test).
- **Integration test** end-to-end (sotto-MR 8): 1-2 test che
  caricano il **PdE 2026 reale** in un DB di test e verificano
  proprietà strutturali dell'output (es. il giro 271 dopo rebuild
  v2 produce N giornate-tipo, almeno una con M ≥ 2 varianti
  calendariali, etichette stile `LV`/`F`/`Si eff.`).

Niente snapshot test del PDF Trenord — il PDF è riferimento
concettuale, non oracolo (decisione utente 2026-05-06).

---

## 9. Piano di implementazione (sotto-MR)

| Sotto-MR | Scope | Stima | Priorità |
|---|---|---|---|
| **0** | Questo documento (`docs/MR-1110-DESIGN.md`) + entry TN-UPDATE | 2h | ✅ in corso |
| **1** | Risoluzione decisioni aperte D1-D8 in chat con utente | 30-60min | 🔄 prossimo step |
| **2** | Nuovo modulo `giornata_tipo.py` (Step 2 algoritmo) + test puri | 4-6h | dopo 1 |
| **3** | Nuovo modulo `concatenazione_ciclica.py` (Step 4 algoritmo) + test puri | 4-6h | dopo 2 |
| **4** | Riscrittura `etichetta.py` per etichette parlanti + test acceptance turno 1110 G6 | 3-5h | parallelo a 2-3 |
| **5** | Riscrittura `multi_giornata.py` per usare i nuovi step | 4-6h | dopo 2-4 |
| **6** | Aggiornamento `aggregazione_a2.py` per il nuovo modello | 2-3h | dopo 5 |
| **7** | Deprecazione (opt-out) di `fusione_cluster_a1.py` MR 12 | 1h | dopo 5 |
| **8** | Test integration end-to-end: PdE 2026 reale → turno con N giornate concatenate + varianti ricche | 4-6h | dopo 7 |
| **9** | Aggiornamento UI Gantt frontend per etichette parlanti + nesting varianti + indicatore ciclo | 6-8h | dopo 8 |
| **10** | Migrazione/re-run dei programmi esistenti (D7) + verifica regressioni | 2-3h | dopo 9 |

Stima totale: ~30-50h di lavoro distribuito su 4-6 sotto-MR
incrementali. Ogni sotto-MR ha test e commit indipendenti
(`docs/METODO-DI-LAVORO.md` regola 3).

---

## 10. Tracciabilità

- **TN-UPDATE entry di apertura**: 2026-05-06 (179) — apertura
  MR-1110 con riferimento a questo documento.
- **TN-UPDATE entry di chiusura sotto-MR**: una entry per ciascuno
  dei sotto-MR 2-10.
- **Memoria persistente** (a chiusura MR completo): aggiungere
  `feedback_modello_giornata_tipo_concatenata.md` con sintesi del
  modello finale.
- **Decisioni utente da preservare**:
  - 2026-05-06: "voglio G1-Lun, G1 Variazione Festiva, G1 Solo Quel
    Giorno, G1 Dal/Al, G1 Solo Sabato e così via. Così deve girare
    il turno. E poi si concatenano l'una con l'altra. Se no si
    usano troppi materiali."
  - 2026-05-06: "NOI non dobbiamo estrarre niente, dobbiamo
    inventarlo noi il metodo, sulla base di e come esempio di ciò
    che avviene oggi tutto qui. Lo screen è un esempio."

---

## 11. Riferimenti

- Modello target visivo: PDF "Turno Materiale Trenord dal 2/3/26",
  pagina 29 (turno 1110, giornata 6).
- Dump turni 2026: `data/turni_materiale_2026_dump.json`.
- Codice attuale builder:
  `backend/src/colazione/domain/builder_giro/`.
- Storia decisioni MR 12 fusione Jaccard: TN-UPDATE entry 114
  (2026-05-03).
- Storia decisioni varianti per giornata MR 7.7.5: TN-UPDATE entry
  56-59 (2026-04-30).
- Schema concettuale piramide: `docs/MODELLO-DATI.md` v0.5.
- Algoritmo di base (storico): `docs/ALGORITMO-BUILDER.md`,
  `docs/ARCHITETTURA-BUILDER-V4.md`.

---

**Autore**: Claude (sessione 2026-05-06).
**Approvazione modello**: in attesa utente.
**Prossimo step**: risoluzione decisioni aperte D1-D8 (§8) in chat,
poi apertura sotto-MR 2.
