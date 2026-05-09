# SEVERO — Critica MR-B2 (backtracking esteso a giri lunghi + peso_chiude_sede 50→500)

**Data**: 2026-05-09
**Commit criticato**: `ba2e616` (entry 255 TN-UPDATE)
**Trigger invocazione**: utente esplicito, dopo verifica empirica del
trade-off (10 corse non coperte in più) e segnalazione "linee non
presenti sul filtro".
**Motore di SEVERO**: AMILCARE V4 Pro via `mcp__amilcare__reason`
(brief ~3KB, output ~500 parole, no timeout).
**Pattern**: verbatim AMILCARE + filtro NINO + verifica empirica DB
post-critica.

---

## TL;DR (3 righe)

MR-B2 introduce un **bug architetturale di cross-rule contamination**
nel backtracking esteso: `_trova_continuazioni_top_k` filtra solo
materiale + località, mai per regola. Catene di regole diverse con
stesso materiale possono mischiarsi nello stesso giro. **Voto: 2/10**.
Sul prog 17 attuale il bug NON si manifesta (0 giri same-material
cross-rule), ma il difetto è strutturale e va corretto.

---

## Voto: **2/10**

Aumento finto delle metriche numeriche (-13 giri non chiusi, +16
naturali) compensato da +10 corse non coperte (trade-off interno al
pool). Il fix è "buono per i numeri" ma introduce un debito
architetturale che si paga sui programmi reali multi-regola con
materiali condivisi.

---

## Finding

### HIGH-1 — Cross-rule contamination nel backtracking esteso

**Pattern verbatim AMILCARE**:

> Il commit ba2e616 agisce su:
> 1. `backtracking_esplorativo.py:448` – il filtro di eleggibilità
>    delle catene passa da `len < n_giornate_min` a `len < n_giornate_max`.
> 2. `_trova_continuazioni_top_k` seleziona le catene candidate
>    controllando **solo materiale e località di continuità**
>    (`c.localita_codice == localita_codice` e assenza di visite
>    duplicate). **Nessun filtro sulla regola di appartenenza** della
>    catena.
> 3. Il pool è `catene_per_data_per_materiale[mat_regola]`. Quando
>    più regole condividono lo stesso materiale (es. ETR522 in regola
>    48 ALES-MORTARA e regola 51 BERG-CARNATE), il pool è comune.
>    Pertanto un giro nato da regola 48 può pescare una catena di
>    regola 51 sfruttando Milano come punto di contatto.
>
> Per la pianificazione ferroviaria reale, un convoglio rispetta il
> contratto di linea (regola specifica). Un giro composto da tratti
> di regole diverse, pur appartenendo allo stesso materiale, viola
> il filtro operativo dell'utente ("linee non presenti sul filtro").

**Filtro NINO**: ✅ accettato HIGH. Verifica empirica fatta dopo:
prog 17 attuale ha **0 giri same-material cross-rule** (ETR522 di
regole 48+51 non si mischiano, ETR204 in regole 47+53 idem, perché
finestre orarie/continuità geografiche non si incastrano sui dati
reali). MA il rischio architetturale è reale: appena un programma
ha 2+ regole same-material con catene compatibili
geograficamente/temporalmente, il bug si manifesta.

**Azione correttiva richiesta**: aggiungere filtro per regola in
`_trova_continuazioni_top_k`. La catena candidata deve appartenere
alla **stessa regola dominante** del giro che si sta estendendo,
non solo allo stesso materiale.

### HIGH-2 — Trade-off mascherato da metriche favorevoli

**Filtro NINO** (auto-finding): MR-B2 trade -13 giri non chiusi per
+10 corse non coperte. La narrazione del commit message dice "+114%
chiusi, -57% non chiusi" ignorando che le **10 corse non coperte
sono navette intra-day** (S01860↔S01074), pattern operativo critico
per il pianificatore PdC.

Per il dominio ferroviario, una **corsa non assegnata** è peggiore
di un giro non chiuso: la corsa va a coprire un servizio
contrattualizzato col cliente; un giro non chiuso è solo un'unità
di pianificazione che richiede revisione manuale ma può comunque
essere assegnata a un PdC.

**Pattern di pigrizia**: NINO ha celebrato i numeri "vincenti"
(naturali +114%) senza confrontare il valore operativo dei due
errori. Bias green-light già osservato in entry 253-255.

**Azione correttiva**: prima di considerare MR-B2 "favorevole",
verificare che il trade-off sia operativamente neutro o positivo:
- Le 10 navette aggiunte alle non-coperte hanno copertura PdC
  alternativa nel programma?
- I 13 giri "salvati" sono operativamente utili (perimetro singola
  regola) o sono "frankenstein" cross-rule che il pianificatore
  rifiuterà comunque?

### MED-1 — Test scritto prima del cambio default ma incompleto

**Filtro NINO** (auto-finding): la lezione entry 251 (test prima del
cambio default) è stata onorata formalmente: ho scritto
`test_b2_giro_lungo_non_chiuso_esteso_per_chiudere_in_sede` prima del
commit. **Ma il test non copre il caso multi-regola** (catene di
regole diverse stesso materiale): se l'avessi scritto col rigore
necessario, avrei intercettato il bug HIGH-1 prima di SEVERO.

**Azione correttiva**: aggiungere
`test_b2_no_cross_rule_contamination_when_extending`: 1 giro regola
A + catena regola B stesso materiale geo-compatibile → l'estensione
DEVE escludere la catena B.

### MED-2 — peso_chiude_sede 500 calibrato senza A/B test

**Filtro NINO**: il valore 500 viene da una regola di proporzione
(km_score 900 vs bonus chiusura 50 → 18:1 sproporzionato → 500 dà
ratio 0.55). Plausibile ma non validato empiricamente. Su programmi
con km_max_ciclo molto diverso (es. 5000 vs 25000), il bilanciamento
cambia. Il valore dovrebbe essere **proporzionale** a km_max_ciclo o
a km medi del giro, non assoluto.

**Azione correttiva** (scope futuro): rendere `peso_chiude_sede`
proporzionale a `km_max_ciclo` o calibrare via param per programma.

---

## Sintesi finding

| # | Sev | Titolo | Origine | Azione |
|---|---|---|---|---|
| 1 | HIGH | Cross-rule contamination | AMILCARE | Aggiungere filtro regola in `_trova_continuazioni_top_k` |
| 2 | HIGH | Trade-off mascherato | NINO auto | Verificare valore operativo navette vs giri lunghi |
| 3 | MED | Test cross-rule mancante | NINO auto | Test che dimostra il filtro regola |
| 4 | MED | peso_chiude_sede magic number | NINO | Proporzionare a km_max_ciclo (scope futuro) |

---

## Verifica empirica post-critica

Prog 17 attuale (78 giri, post-MR-B2):
- 54/78 giri toccano direttrici di "più regole" — ma quasi tutti
  false positive (la stessa direttrice come TIRANO-SONDRIO-LECCO-MILANO
  appare sia in regola 47 ETR526 che 53 ETR204; un giro ETR204 con
  TIRANO-SONDRIO non è cross-rule, è solo che la direttrice è
  condivisa).
- **Same-material cross-rule: 0 giri**. Il bug architetturale non si
  manifesta sui dati reali prog 17 perché le finestre orarie/posizioni
  geografiche delle regole same-material (ETR522 in 48+51, ETR204 in
  47+53) non producono catene incrociabili.

**Conclusione**: il fix architetturale (filtro regola) è necessario
per **principio di correttezza** e per programmi futuri/diversi, ma
sul prog 17 specifico l'effetto numerico atteso è **trascurabile**.
Il cambio invece può influire sul trade-off: potrebbe LIBERARE
catene navetta che ora vengono "bruciate" per estensioni cross-rule
di un altro materiale (da verificare empiricamente post-fix).

---

## Lezioni meta

1. **Verificare cross-rule prima di committare**, non dopo SEVERO.
   Pattern: prima di estendere un'esplorazione, listare tutte le
   discriminanti (materiale, regola, sede, periodicità) e verificare
   che il filtro le rispetti tutte.
2. **Diffidare di metriche miste**. -13 giri non chiusi vs +10 corse
   non coperte è un trade tecnico, non un miglioramento netto.
   Misurare il **valore operativo** prima di celebrare.
3. **Pattern AMILCARE V4 Pro funzionante con brief ~3KB**: questa
   chiamata è andata a buon fine dopo 3 timeout precedenti (~2-4KB).
   Conferma: V4 Pro accetta brief con codice ben strutturato e
   contesto ricco purché compatto.

---

## Riferimenti

- TN-UPDATE entry 255 — narrazione MR-B2
- Commit `ba2e616` — diff modificato
- `backend/src/colazione/domain/builder_giro/backtracking_esplorativo.py:170` — `_trova_continuazioni_top_k`
- `backend/src/colazione/domain/builder_giro/backtracking_esplorativo.py:448` — filtro eligibilità
