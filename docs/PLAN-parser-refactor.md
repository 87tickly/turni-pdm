# PLAN — Refactor parser turno materiale + affinamento parser PdC

Documento di handoff per sessione dedicata. Ordine: **prima materiale**, poi PdC.

Stato commit di partenza: `ce89bf6` su `master`.

---

## Regole di ingaggio (leggere PRIMA di iniziare)

1. **NON sovrascrivere** `turno_materiale_treni.json` finché il nuovo parser non
   produce un output **almeno equivalente** al JSON storico (2884 treni, 413 vuote,
   54 turni). Il JSON attuale è generato da un PDF storico (`Vuoto 50 (1).pdf`) e
   alimenta builder, Gantt e autocompletamento. Rompere quel file = rompere il
   sistema.
2. **Test manuale prima di committare**: ogni modifica al parser deve essere
   verificata su almeno 3 turni campione (es. 1100, 1110, 1192A) confrontando
   l'output con il JSON storico.
3. **Approccio incrementale**: un singolo commit per ogni step finito, non un
   big-bang.
4. **Flusso COLAZIONE standard**: leggere `LIVE-COLAZIONE.md`, fix, test,
   `git add` → `commit` → `push`, aggiornare `LIVE-COLAZIONE.md`.
5. **No regressioni sul parser PdC**: non modificare `src/importer/turno_pdc_parser.py`
   senza aver prima raccolto un baseline numerico (vedi sezione B).

---

## SEZIONE A — Parser turno materiale (priorità 1)

### A.1 Contesto

File principale: `parse_turno_materiale.py` (540 righe, script standalone al root).
Script secondario: `import_turno_materiale.py` (240 righe — importa il JSON in DB).
Skill: `.claude/skills/turno-materiale-reader.md` (letta: formato storico
con numeri treno orizzontali).

PDF attuale: `uploads/Turno Materiale Trenord dal 2_3_26.pdf` (353 pagine).
PDF storico (non in repo): `Vuoto 50 (1).pdf` (usato per generare il JSON in uso).

Test run con parser attuale (dopo fix regex del commit `ce89bf6`):
```bash
.venv/bin/python parse_turno_materiale.py \
  "uploads/Turno Materiale Trenord dal 2_3_26.pdf" \
  /tmp/turno_materiale_test.json
```
Risultato: 54 turni identificati ✓, ma solo **31/2884 (1%) dei numeri treno
estratti**.

### A.2 Root cause

Il PDF attuale ha un **formato diverso** da quello storico: i numeri treno sono
scritti **verticalmente** sopra le barre del Gantt, una cifra per riga Y.

Esempio turno 1100 (estrazione char-by-char bottom-to-top):

```
y=434  "1111"    ← 1a cifra dei 4 treni (tutti "1")
y=440  "0000"    ← 2a cifra (tutti "0")
y=445  "6666"    ← 3a cifra (tutti "6")
y=450  "0010"    ← 4a cifra (0,0,1,0)
y=456  "6309"    ← 5a cifra (6,3,0,9)
y=432  "CREMONAMI.P.GARIBALDICREMONA"   ← stazioni orizzontali (OK)
y=419  "3524281941323622"                ← minuti di partenza/arrivo
```

Leggendo per **COLONNA X** (top→bottom) si ricompongono i treni:
- Col 1: `1,0,6,0,3` = **10603** ✓
- Col 2: `1,0,6,0,6` = **10606** ✓
- Col 3: `1,0,6,0,9` = **10609** ✓
- Col 4: `1,0,6,1,0` = **10610** ✓

Il parser attuale invece legge per **RIGA Y** (aggrega char per y, sort bottom-to-top),
quindi vede `"1111"`, `"0000"` come stringhe separate. Il regex cerca numeri
di 4-5 cifre (`\d{4,5}`) ma non trova match perché le cifre non sono concatenate
in orizzontale.

### A.3 Fix proposto — Refactor a lettura per colonna X

Passi ordinati:

**Step A.3.1 — Isolare le cifre verticali dei treni**
- pdfplumber espone `chars` con attributo `upright` (bool) o `matrix` (rotazione)
- Un char `upright=False` è ruotato a 90°: è una cifra del treno, NON una lettera
  orizzontale
- Filtro: `chars where upright == False` isola le cifre verticali

**Step A.3.2 — Clusterizzare per colonna X**
- Raggruppa le cifre verticali per X simile (tolleranza ~2pt)
- Per ogni cluster, ordinare per Y **decrescente** (top→bottom) e concatenare:
  questo ricompone il numero treno

**Step A.3.3 — Band Y corretta**
- I numeri treno stanno in una banda Y specifica sopra le barre del Gantt
- Determinare la band_top/band_bot dalla banda di ogni "riga turno" (stesso
  approccio usato in `turno_pdc_parser.py:_find_day_markers`)

**Step A.3.4 — Vuoti (suffisso "i")**
- I numeri vuoti hanno suffisso `i` (es. "28096i"). Il char `i` potrebbe essere
  verticale a fianco del numero. Ispezionare: `filter(chars, upright=False)` +
  cercare `i` vicino alle cifre del treno

**Step A.3.5 — Minuti partenza/arrivo**
- Sotto ogni barra ci sono 2 minuti (partenza, arrivo) — nel PDF storico erano
  su una riga Y compressa (es. `"3524281941323622"` = 8 valori di 2 cifre)
- Con 4 treni: 8 minuti = 2 per treno. Posizione X associa minuto a treno.
- Probabile che nel nuovo PDF siano anch'essi verticali; verificare prima.

**Step A.3.6 — Stazioni**
- Nel layout attuale sono ancora orizzontali (es. `CREMONAMI.P.GARIBALDICREMONA`).
- Parsing: split su stazioni conosciute (usare `fr_stations.txt` come lookup
  + lista abbreviazioni dalla skill).

### A.4 Script diagnostico pronto all'uso

Salvare come `/tmp/diag_materiale.py`:

```python
"""Diagnostica formato PDF turno materiale: cifre verticali vs orizzontali."""
import sys
sys.path.insert(0, '.')
import pdfplumber
from collections import defaultdict

PDF = "uploads/Turno Materiale Trenord dal 2_3_26.pdf"
pdf = pdfplumber.open(PDF)

# Pagina 2 = primo turno (1100)
pg = pdf.pages[1]

# 1. Conta char verticali vs orizzontali
up_chars = [c for c in pg.chars if c.get('upright', True)]
rot_chars = [c for c in pg.chars if not c.get('upright', True)]
print(f"Char upright (orizzontali): {len(up_chars)}")
print(f"Char NON upright (ruotati): {len(rot_chars)}")

# 2. Cifre ruotate raggruppate per X (colonne treno)
digit_cols = defaultdict(list)
for c in rot_chars:
    if c['text'].isdigit():
        x_key = round(float(c['x0']) / 2) * 2  # arrotonda a 2pt
        digit_cols[x_key].append(c)

print(f"\nColonne di cifre ruotate: {len(digit_cols)}")
for x, chars in sorted(digit_cols.items())[:20]:
    # Top to bottom (y decrescente)
    chars.sort(key=lambda c: -float(c['y0']))
    num = ''.join(c['text'] for c in chars)
    y_range = (round(chars[0]['y0']), round(chars[-1]['y0']))
    print(f"  x={x:<6.1f} y={y_range}  num={num!r}")

# 3. Confronta con atteso per turno 1100
print("\nATTESO turno 1100: ['10603', '10606', '10609', '10610']")
```

Esegui con:
```bash
.venv/bin/python /tmp/diag_materiale.py
```

### A.5 Validazione

Creare fixture con ground truth per 3 turni campione:

| Turno | Treni regolari attesi | Vuote attese |
|-------|-----------------------|--------------|
| 1100  | 10603, 10606, 10609, 10610 | — |
| 1110  | (72 treni — vedi JSON storico) | (da JSON storico) |
| 1192A | (da JSON storico) | (da JSON storico) |

Comando verifica:
```bash
.venv/bin/python -c "
import json
hist = json.load(open('turno_materiale_treni.json'))
new  = json.load(open('/tmp/turno_materiale_test.json'))
for code in ['1100','1110','1192A']:
    h = set(t for v in hist['turni'][code]['variants'] for t in v['treni'])
    n = set(t for v in new['turni'].get(code,{}).get('variants',[]) for t in v['treni'])
    print(f'{code}: storico={len(h)} nuovo={len(n)} overlap={len(h&n)} missing={sorted(h-n)[:5]}')
"
```

**Target**: per ogni turno, `overlap / storico >= 95%`.

### A.6 Quando fermarsi

- Dopo ogni step, misurare la % di treni recuperati: se supera il **90%** del
  JSON storico, considerare done e committare. Non inseguire il 100% se richiede
  trucchi fragili.
- Il suffisso "i" delle vuote è un dettaglio: se lo step A.3.4 costa troppo,
  lasciarlo come follow-up e committare senza.

---

## SEZIONE B — Parser PdC (priorità 2)

### B.1 Contesto

File: `src/importer/turno_pdc_parser.py` (981 righe).
Skill: `.claude/skills/turno-pdc-reader.md`.
PDF: `uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf` (26 turni nell'indice).

Baseline commit: `bbb8fec` — aggiunto campo `minuti_accessori: str` a
`ParsedPdcBlock`. Il resto del parser è **identico** al baseline pre-sessione.

### B.2 Numeri baseline (NON regredire)

Eseguire prima di modificare:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from src.importer.turno_pdc_parser import parse_pdc_pdf
from collections import Counter

turns = parse_pdc_pdf('uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf')
print(f'Turni: {len(turns)}')  # atteso 26

by_t = Counter()
ms = Counter()
me = Counter()
for t in turns:
    for d in t.days:
        for b in d.blocks:
            by_t[b.block_type] += 1
            if b.block_type in ('train','coach_transfer','meal'):
                if not b.start_time: ms[b.block_type] += 1
                if not b.end_time: me[b.block_type] += 1
for k in sorted(by_t):
    v = by_t[k]
    print(f'  {k:<18s} tot={v:>4d}  miss_s={ms.get(k,0):>3d}  miss_e={me.get(k,0):>3d}')
"
```

Valori baseline attesi:
```
train           tot=4237  miss_s=393  miss_e=611
coach_transfer  tot= 860  miss_s=105  miss_e=137
meal            tot= 682  miss_s= 91  miss_e=124
```

Qualsiasi modifica deve mantenere questi numeri ≤ baseline.

### B.3 Problemi da risolvere (in ordine)

**B.3.1 — Popolamento `minuti_accessori`** (facile, alto valore)

Il campo è presente nel dataclass ma vuoto. Il valore è una stringa tipo `"5/5"`
scritta nel PDF come testo ausiliario sotto il minuto principale del primo/ultimo
blocco treno della giornata.

Approccio:
1. Ispezionare il PDF e trovare dove viene renderizzato "5/5" (probabilmente
   size piccolo, sotto l'asse orario, vicino all'inizio/fine della giornata)
2. Estrarre questo testo in `_extract_day_from_band` e associarlo al primo
   e/o ultimo blocco `train`
3. Test: verificare su AROR_C giorno 1 (dovrebbe avere 5/5 default)

Nessun rischio di regressione sugli orari.

**B.3.2 — Ratio label↔blocco logico (architetturale)**

Hypothesis da validare visualmente sul PDF: label come `10205ARON` + `10205MIpg`
potrebbero essere **due label dello stesso treno** (partenza + arrivo), non
due treni separati.

Come validare:
1. Aprire `uploads/Turni PdC rete RFI dal 23 Febbraio 2026.pdf` a pag 2
2. Guardare visualmente il giorno 4 di AROR_C (periodicità LMXGV)
3. Contare quanti blocchi treno effettivi ci sono nella banda del Gantt
4. Confrontare con le 8 label train che il parser vede

Se l'ipotesi è confermata: serve un'euristica per fondere label adiacenti con
lo stesso `train_id` in un unico blocco (partenza = stazione del label sx,
arrivo = stazione del label dx).

**B.3.3 — Orari mancanti 9-18%**

Dopo aver risolto B.3.2, rimisurare. Probabile che i miss calino da soli
(meno blocchi train da riempire, minuti meglio allocati).

Se i miss restano alti, solo allora valutare:
- Ampliare `_extract_upper_minutes` (già tentato, da validare con ground truth)
- Cambiare `_assign_minutes_to_blocks` in window-based (già tentato, peggio —
  vedi diff reverted in sessione precedente)

### B.4 Ground truth consigliata (prima di B.3.2 e B.3.3)

Annotare manualmente 5 giornate del PDF PdC in un file `tests/fixtures/pdc_ground_truth.json`:

```json
{
  "AROR_C": {
    "day_1_LMXGVSD": {
      "blocks": [
        {"type": "coach_transfer", "vettura": "2434", "from": "ARON", "to": "DOMO", "start": "17:25", "end": "18:04"},
        {"type": "meal", "to": "DOMO", "start": "18:40", "end": "19:07"},
        ...
      ]
    }
  }
}
```

Creare un test pytest che confronta `parse_pdc_pdf()` con questo fixture.
Solo con ground truth si possono fare fix chirurgici senza regredire.

### B.5 Quando fermarsi

- B.3.1 (minuti_accessori) è standalone e safe → commit indipendente
- B.3.2 e B.3.3 richiedono ground truth. Se il tempo non basta, fermarsi a
  B.3.1 e documentare B.3.2/B.3.3 come TODO.

---

## PROMPT PRONTO per nuova sessione

Copia/incolla il testo tra le linee nella nuova chat:

---

```
Sono in /Users/spant87/Library/Mobile Documents/com~apple~CloudDocs/----ARTURO----/ECOSISTEMA-ARTURO/COLAZIONE.

Leggi subito:
1. CLAUDE.md (istruzioni progetto)
2. LIVE-COLAZIONE.md (ultimi commit, prime 100 righe)
3. docs/PLAN-parser-refactor.md (piano completo di questa sessione)

Poi parti dalla SEZIONE A del plan: refactor parser turno materiale.

Vincoli critici:
- Venv: .venv/bin/python (Python 3.12, pdfplumber 0.11.9)
- NON sovrascrivere turno_materiale_treni.json finche' il nuovo parser non
  produce output >= 90% del JSON storico (2884 treni, 413 vuote, 54 turni)
- Output di test in /tmp/, non nel repo
- PDF target: uploads/Turno Materiale Trenord dal 2_3_26.pdf
- Root cause: nel nuovo PDF i numeri treno sono VERTICALI (una cifra per riga
  Y), il parser legge per riga invece che per colonna. Refactor necessario.

Procedi passo-passo seguendo gli step A.3.1 → A.3.6 del plan. Dopo ogni step,
committa con messaggio descrittivo e pusha su master. Aggiorna LIVE-COLAZIONE.md
a fine sessione.

Se arrivi al 90% di copertura treni sul turno materiale, passa alla SEZIONE B
(parser PdC) partendo da B.3.1 (popolamento minuti_accessori).

NON toccare:
- src/importer/turno_pdc_parser.py senza prima raccogliere baseline B.2
- Il file turno_materiale_treni.json

Primo comando utile per orientarti:
  .venv/bin/python parse_turno_materiale.py "uploads/Turno Materiale Trenord dal 2_3_26.pdf" /tmp/turno_materiale_test.json
  (output atteso: 54 turni ma solo ~1% dei treni)

Poi esegui lo script diagnostico in A.4 per confermare il formato verticale.
```

---
