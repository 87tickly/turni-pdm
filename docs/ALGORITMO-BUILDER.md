# Algoritmo Builder Turni PdC

> Specifica formale dell'algoritmo che trasforma **un turno materiale**
> (ciclo giornaliero di un convoglio) in **una lista di turni PdC**
> tutti in regola con la normativa.
>
> **Fonte delle regole**: [`NORMATIVA-PDC.md`](NORMATIVA-PDC.md).
> Questo documento non ri-definisce le regole, le **applica**.
>
> **Destinazione implementativa**: `src/turn_builder/auto_builder.py`
> (da riscrivere a partire da questo documento).

---

## 1. Input / Output

### Input

- `MATERIALE`: lista ordinata per orario di segmenti del ciclo
  giornaliero. Ogni segmento è:
  ```
  Segmento {
      numero: str           # es. "2812", "28335i", "U8335"
      tipo: enum            # COMMERCIALE | VUOTO_I | VUOTO_U
      da_stazione: str
      a_stazione: str
      partenza: time        # HH:MM
      arrivo: time
      durata_min: int
  }
  ```
  - `VUOTO_I` = treno con suffisso "i" (§1 NORMATIVA).
  - `VUOTO_U` = numero aziendale `U****` (§8.7). Inserito solo se
    il primo/ultimo segmento commerciale è a Mi.Certosa (§8.2).
- `DEPOSITI_DISPONIBILI`: set dei depositi PdC utilizzabili (§2.1).
- `API_ARTURO`: handle per query orari tratte commerciali (§12.1).

### Output

- `PDC_LIST`: lista di turni PdC. Ogni PdC è:
  ```
  PdC {
      deposito_sede: str
      segmenti: list<EventoPdC>   # cronologico
      prestazione_min: int
      condotta_min: int
      refez: ReferzInfo | null
      valido: bool
      violazioni: list<str>       # vuota se valido
  }
  ```
- `MATERIALE_RESIDUO`: segmenti rimasti scoperti (deve essere vuoto).

### Tipi di `EventoPdC`

```
EventoPdC = PresaServizio | AccP | Condotta | PK | CVa | CVp
          | Refez | Buco | Vettura | Taxi | MM | AccA | FineServizio
```

---

## 2. Algoritmo top-level — copertura del materiale

```
funzione copri_materiale(MATERIALE) -> list<PdC>:
    pool = MATERIALE.segmenti_ordinati_per_partenza()
    pdc_list = []

    while pool non vuota:
        primo_seg = pool.primo()
        pdc = costruisci_pdc_dal_segmento(primo_seg, pool)
        if pdc.valido:
            pool.rimuovi(pdc.segmenti_consumati)    # §15
            pdc_list.append(pdc)
        else:
            raise BuilderError(pdc.violazioni)      # pool scopribile
                                                     # in diag mode
    return pdc_list
```

**Regola §15 (no doppioni)**: `pool.rimuovi` toglie i segmenti
consumati. Un segmento "spezzato" da CV (§9.1) viene diviso in due
sotto-segmenti: la parte pre-CV esce dalla pool, la parte post-CV
resta come nuovo segmento disponibile per il PdC successivo.

---

## 3. Costruzione di un singolo PdC

```
funzione costruisci_pdc_dal_segmento(primo_seg, pool) -> PdC:
    # 3.1 Scelta deposito
    deposito = scegli_deposito(primo_seg, DEPOSITI_DISPONIBILI)

    # 3.2 Orario presa servizio
    t_presa = calcola_presa_servizio(deposito, primo_seg)

    # 3.3 Cap prestazione (§11.8)
    if t_presa in [01:00, 04:59]:
        cap_prest = 420    # 7h
    else:
        cap_prest = 510    # 8h30

    # 3.4 Posizionamento iniziale (se deposito ≠ stazione_partenza)
    eventi = [PresaServizio(t_presa)]
    t_cursore = t_presa

    if deposito != primo_seg.da_stazione:
        eventi += posizionamento(deposito, primo_seg.da_stazione, t_cursore)
        t_cursore = eventi.ultimo().arrivo

    # 3.5 ACCp sul primo segmento di condotta
    accp = calcola_accp(primo_seg, deposito)    # §3.3, §8.5
    eventi.append(accp)
    t_cursore = accp.fine

    # 3.6 Loop condotta (catena di segmenti consecutivi stesso materiale)
    condotta_min = 0
    segmento_corrente = primo_seg

    while True:
        eventi.append(Condotta(segmento_corrente))
        condotta_min += segmento_corrente.durata_min
        t_cursore = segmento_corrente.arrivo

        # Proiezione di uscita se fermo qui
        prest_proiettata = proietta_fine_turno(t_presa, t_cursore,
                                               deposito, segmento_corrente)

        # Stop se i vincoli ci spingono fuori
        if condotta_min > 330:             return scarta("condotta")
        if prest_proiettata > cap_prest:   return scarta("prestazione")

        # Prossimo segmento compatibile?
        next_seg = pool.successivo_stesso_materiale(segmento_corrente)
        if next_seg is None:
            break

        gap = next_seg.partenza - t_cursore
        if gap < 0:
            break    # non c'è continuità temporale

        # Gap handling (§6)
        gap_evento = scegli_gap(gap, segmento_corrente, next_seg, eventi)
        if gap_evento.supera_cap(cap_prest, condotta_min):
            break
        eventi.append(gap_evento)
        t_cursore = next_seg.partenza
        segmento_corrente = next_seg

    # 3.7 Chiusura turno
    eventi += chiudi_turno(segmento_corrente, deposito, t_cursore,
                           cap_prest, condotta_min)

    # 3.8 Validazione
    pdc = PdC(deposito, eventi, ...)
    pdc.valida()     # vedi §5
    return pdc
```

---

## 4. Sotto-procedure

### 4.1 `scegli_deposito(primo_seg, DEPOSITI)`

**Regola**: il deposito scelto deve essere **compatibile** con
`primo_seg.da_stazione` secondo la §2 (linea/impianti del deposito).

Candidati validi (in ordine di preferenza):
1. Deposito che **coincide** con la stazione di partenza (nessun
   posizionamento).
2. Deposito **geograficamente vicino** con tempo posizionamento ≤
   60'.
3. Fallback: deposito con posizionamento ≤ 90' (solo se nessun altro
   disponibile).

**Caso speciale Fiorenza**: se il materiale parte da Mi.Certosa con
un `VUOTO_U` o `VUOTO_I` a testa (§8.7, §13.1), il deposito è
**MI.PG** e il posizionamento è **TAXI a Fiorenza** (§8.5.1).

### 4.2 `calcola_presa_servizio(deposito, primo_seg)`

Dipende dal primo segmento di lavoro:

| Primo segmento | Regola |
|----------------|--------|
| Taxi verso impianto (es. MI.PG→FIOz) | presa_servizio = taxi_partenza − 15' (§3.2) |
| Vettura su treno passeggeri | presa_servizio = vettura_partenza − 15' (§3.2) |
| Condotta diretta da deposito | presa_servizio = ACCp_inizio (nessun 15' pre) |

### 4.3 `posizionamento(da, a, t)`

Ritorna la lista di eventi per spostare il PdC da `da` a `a`.
**Priorità §7.2**:
1. **Vettura** (treno passeggeri) — query `API_ARTURO`.
2. **MM** (metropolitana) — solo se sforerebbe altrimenti e il
   deposito è servito da MM.
3. **Taxi** — ultima spiaggia o caso `MI.PG ↔ FIOz` (§8.5.1).

### 4.4 `calcola_accp(segmento, stazione)`

Valori §3.3 e §8.5:

| Stazione / contesto | Valore |
|---------------------|--------|
| Condotta standard | ACCp = 40' |
| Preriscaldo ● (dic-feb) | ACCp = 80' |
| FIOz (impianto manutenzione) | ACCp = 40' (no preriscaldo, §8.5) — include 7' trasferimento FIOz→MiCertosa (§8.5, §8.7) |

### 4.5 `scegli_gap(gap, seg_prev, seg_next, eventi)`

Applica la tabella §6:

| Gap | Modalità ammesse |
|-----|------------------|
| < 65' | CV (richiede incontro 2 PdC) · PK (più flessibile) |
| 65–300' | ACC (40'+40') · PK |
| > 300' | ACC (default) · PK (opt-in) |

**Scelta algoritmica** (più efficiente in tempo):
- Se stesso PdC continua su stesso materiale → **PK** (no CV, non
  serve incontro).
- Se PdC deve cambiare → **CV** se gap < 65' e stazione §9.2;
  altrimenti **ACC** o **PK**.

**REFEZ (§4.1)**: se durante un gap si è dentro una finestra
pranzo/cena **e** la prestazione proiettata > 360', inserisci un
REFEZ 30' dentro il gap.

### 4.6 `chiudi_turno(ultimo_seg, deposito, t, cap_prest, condotta)`

Opzioni (in ordine di preferenza):

1. **CV + rientro passivo** (se `ultimo_seg.arrivo` è stazione §9.2
   e c'è PdC successivo compatibile):
   - Aggiungi CVa.
   - Aggiungi Vettura passiva `ultimo_seg.arrivo → deposito` via §4.3.
   - Fine servizio = arrivo_vettura + 15' (§3.2).

2. **ACCa + rientro passivo** (se §9.2 non applicabile):
   - Aggiungi ACCa 40'.
   - Rientro §4.3.
   - Fine servizio = arrivo_rientro + 15'.

3. **FR** (fuori residenza, §10):
   - Se `arrivo_fuori_sede` e nessun rientro possibile senza sforare.
   - Verifica limiti §10 (1/settimana, 3/28gg).
   - Fine servizio = arrivo + ACCa 40' (il PdC dorme fuori).

Scelta guidata da minimizzazione della prestazione proiettata,
sempre `≤ cap_prest`.

---

## 5. Validazione finale `pdc.valida()`

Applicare §14.2 in ordine:

### 5.1 Vincoli rigidi singolo turno

1. `prestazione ≤ cap_prest` (§11.8) — altrimenti **scarta**.
2. `condotta ≤ 330` (§14.2) — altrimenti **scarta**.
3. Se `prestazione > 360`: **REFEZ obbligatoria** (§4.1), deve
   esistere un evento REFEZ 30' dentro 11:30–15:30 o 18:30–22:30 —
   altrimenti **scarta**.
4. Accessori coerenti (§3): ACCp solo su condotta iniziale, ACCa
   solo su condotta finale, non su vetture.
5. Gap gestiti (§6): ogni gap tra segmenti condotta ha un evento
   coerente col range.

### 5.2 Vincoli rigidi di ciclo (valutazione cross-giornaliera)

Questi non si applicano al singolo PdC ma al ciclo settimanale
completo:

- Riposo intraturno 11h/14h/16h (§11.5).
- Riposo settimanale ≥ 62h con 2 giorni solari (§11.4).

Il builder singolo-giornata **segna** il PdC come "candidato", la
validazione ciclo avviene in un **secondo pass**.

### 5.3 Vincoli di sede / deroghe

- CV solo in stazioni ammesse (§9.2).
- FR entro limiti (§10).
- Deposito coerente con linea (§2).

### 5.4 Preferenze (non scartano, abbassano score)

- Primo giorno post-riposo non mattino (§11.2).
- Ultimo pre-riposo entro 15:00 (§11.3).

---

## 6. Strategia di ricerca

L'algoritmo top-level (§2) è **greedy**: prende il primo segmento
della pool e costruisce un PdC attorno ad esso, poi ripete.

**Miglioramento proposto** (fase 2, non obbligatoria per prima
implementazione):

```
funzione copri_materiale_ottimo(MATERIALE, max_tentativi=25):
    migliore_soluzione = null
    for i in 1..max_tentativi:
        pool = shuffle_pool_entro_vincoli_temporali()
        soluzione = copri_materiale_greedy(pool)
        if soluzione è valida AND (migliore_soluzione is null
                                    OR soluzione.score > migliore.score):
            migliore_soluzione = soluzione
    return migliore_soluzione
```

Lo `score` di una soluzione penalizza:
- Numero di PdC (meno è meglio — massima copertura per turno).
- Prestazioni sotto-sfruttate (PdC molto corti sprecano risorse).
- Violazioni preferenziali §5.4.

---

## 7. Edge case noti da gestire esplicitamente

1. **Materiale che pernotta fuori deposito** (es. P1 → Sondrio).
   L'ultimo segmento è un `VUOTO_I` che termina in stazione non
   deposito. Nessun `VUOTO_U` di coda.
2. **Materiale che parte senza U-numero** (es. da Sondrio al
   mattino dopo pernotto). Nessun `VUOTO_U` di testa, nessun taxi
   FIOz, ACCp al deposito stesso.
3. **CV a Tirano** (§9.2 capolinea inversione): il 2° PdC prende
   il materiale per il ritorno. Ammesso ma richiede PdC
   disponibile con deposito in linea (Sondrio, Lecco, Milano).
4. **Prestazione cap 7h (§11.8)** su presa servizio notturna:
   forza PdC corti. Se la catena condotta naturale eccede, spezzare
   con CV anche se sub-ottimale.
5. **MI.PG → FIOz = TAXI** (§8.5.1) senza API. Tempo fisso
   parametrizzato (default proposto: 20').

---

## 8. Mapping implementazione

### 8.1 Moduli Python

Il builder nuovo **NON** tocca `src/turn_builder/auto_builder.py` (2982
righe, algoritmo genetico legacy che resta per retrocompatibilità).
Sarà aggiunto un modulo separato:

| Funzione algoritmo | Modulo target | Nota |
|--------------------|---------------|------|
| `copri_materiale` | `src/turn_builder/material_to_pdc.py::cover_material()` | NUOVO |
| `costruisci_pdc_dal_segmento` | `src/turn_builder/material_to_pdc.py::build_single_pdc()` | NUOVO |
| `scegli_deposito` | `src/turn_builder/material_to_pdc.py::pick_deposito()` | NUOVO |
| `calcola_presa_servizio` | `src/turn_builder/material_to_pdc.py::presa_servizio()` | NUOVO |
| `posizionamento` | `services/arturo_client.py::find_vettura()` + helpers | estendere |
| `scegli_gap` | `src/validator/rules.py::gap_rule()` | estendere |
| `pdc.valida()` | `src/validator/rules.py::validate_pdc()` | estendere |

### 8.2 Costanti disponibili in `src/constants.py`

Popolate via `config/schema.py` + `config/trenord.py`:

| Costante | Valore Trenord | Riferimento |
|----------|----------------|-------------|
| `MAX_PRESTAZIONE_MIN` | 510 | §11.8 (standard 8h30) |
| `MAX_CONDOTTA_MIN` | 330 | §14.2 (5h30) |
| `CAP_7H_WINDOW_START_MIN` | 60 (01:00) | §11.8 |
| `CAP_7H_WINDOW_END_MIN` | 299 (04:59) | §11.8 |
| `CAP_7H_PRESTAZIONE_MIN` | 420 | §11.8 (7h notte) |
| `REFEZ_REQUIRED_ABOVE_MIN` | 360 | §4.1 |
| `MEAL_WINDOW_1_START/END` | 690/930 (11:30-15:30) | §4.1 |
| `MEAL_WINDOW_2_START/END` | 1110/1350 (18:30-22:30) | §4.1 |
| `MEAL_MIN` | 30 | §4.1 |
| `ACCP_STANDARD_MIN` | 40 | §3.3 |
| `ACCA_STANDARD_MIN` | 40 | §3.3 |
| `ACCP_PRERISCALDO_MIN` | 80 | §3.3 (dic-feb ●) |
| `IMPIANTO_TO_RFI_TRANSFER_MIN` | 7 | §8.5 / §8.7 (FIOz ↔ MiCertosa) |
| `DEPOT_TO_IMPIANTO_TAXI_MIN` | 20 | §8.5.1 (stima MI.PG ↔ FIOz) |
| `PRE_VETTURA_MIN` | 15 | §3.2 |
| `POST_VETTURA_MIN` | 15 | §3.2 |

Per aggiungere costanti: aggiornare `config/schema.py` (campo + default),
opzionalmente override in `config/trenord.py`, riesportare in
`src/constants.py`.

---

## 9. Stato implementazione

- [x] Normativa formalizzata (§1–§15 in `NORMATIVA-PDC.md`)
- [x] Algoritmo formalizzato (questo documento)
- [x] Costanti di normativa in `config/schema.py` + `src/constants.py`
- [ ] Creare `src/turn_builder/material_to_pdc.py` con tipi (step 1)
- [ ] Implementazione `build_single_pdc` (step 2)
- [ ] Implementazione `scegli_gap` + `validate_pdc` (step 3)
- [ ] Implementazione `copri_materiale` greedy (step 4)
- [ ] Test end-to-end su turno materiale 1130 P1 (step 5)
- [ ] Ottimizzazione multi-tentativo §6 (step 6, opzionale)
