"""
Estrae l'anagrafica delle località di manutenzione e la dotazione
materiale per deposito da un PDF "Turno Materiale Trenord".

Uso:
    python scripts/extract_depositi_manutenzione.py <path_pdf> [--out data/depositi_manutenzione_trenord_seed.json]

Default output: data/depositi_manutenzione_trenord_seed.json

Output JSON:
{
    "depositi": {
        "MILANO FIORENZA": {
            "turni": ["1100", "1101", ...],
            "pezzi_totali": {"ALe710": 74, "nBBW": 52, ...},
            "tipi_materiale_unici": ["1npBDL+5nBC-clim+1E464N", ...]
        },
        ...
    },
    "turni_dettaglio": [
        {
            "numero_turno": "1100",
            "validita_codice": "P",
            "tipo_materiale": "1npBDL+5nBC-clim+1E464N",
            "descrizione_materiale": "PR 270 - PPF 120 - m. 174 - MD",
            "numero_giornate": 2,
            "deposito": "MILANO FIORENZA",
            "pezzi": [["npBDL", 2], ["nBC-clim", 10], ["E464N", 2]],
            "cover_page": 1
        },
        ...
    ]
}

Vedi: docs/MODELLO-DATI.md §3 localita_manutenzione + dotazione.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("ERRORE: pdfplumber non installato. Esegui: pip3 install pdfplumber")


def parse_cover(text):
    """Estrae numero turno, tipo materiale, giornate, impegno pezzi da cover."""
    out = {"numero_turno": None, "pezzi": []}
    m = re.search(r"Turno\s+(\d+)", text)
    if m:
        out["numero_turno"] = m.group(1)
    m = re.search(r"Validità\s+(\S+)", text)
    if m:
        out["validita_codice"] = m.group(1).rstrip(")")
    m = re.search(
        r"Tipo Materiale\s+(\S+)\s*\n\s*(.+?)\s*\n\s*Numero Giornate", text, re.DOTALL
    )
    if m:
        out["tipo_materiale"] = m.group(1).strip()
        out["descrizione_materiale"] = m.group(2).strip()
    m = re.search(r"Numero Giornate\s+(\d+)", text)
    if m:
        out["numero_giornate"] = int(m.group(1))
    m = re.search(r"Media Giornaliera \(km\)\s+([\d\.,]+)", text)
    if m:
        out["km_media_giornaliera"] = float(
            m.group(1).replace(".", "").replace(",", ".")
        )
    m = re.search(r"Totale media ponderata Annua \(km\)\s+([\d\.,]+)", text)
    if m:
        out["km_media_annua"] = float(m.group(1).replace(".", "").replace(",", "."))
    pezzi_match = re.search(
        r"Pezzo\s+Numero\s*\n(.*?)(?:Stampato|$)", text, re.DOTALL
    )
    if pezzi_match:
        for line in pezzi_match.group(1).split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\S.*?)\s+(\d+)\s*$", line)
            if m:
                out["pezzi"].append((m.group(1).strip(), int(m.group(2))))
    return out


def parse_omv_from_gantt(text):
    """Estrae deposito manutentivo (canonicalizzato in maiuscolo)."""
    m = re.search(
        r"TRENORD\s+IMPMAN\s+([A-Za-z][A-Za-z\s\.]*?)(?:/|TRENORD|\s{2,}|Posti)",
        text,
        re.IGNORECASE,
    )
    if m:
        nome = m.group(1).strip().upper()
        if nome == "MILANO FIOREN":  # fix troncamento PDF
            nome = "MILANO FIORENZA"
        return nome
    if "Non assegnato/Non assegnato" in text:
        return "NON_ASSEGNATO"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf_path", help="Percorso PDF Turno Materiale Trenord")
    ap.add_argument(
        "--out",
        default="data/depositi_manutenzione_trenord_seed.json",
        help="Path JSON output",
    )
    args = ap.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        sys.exit(f"ERRORE: PDF non trovato: {pdf_path}")

    print(f"Apro {pdf_path}...")
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [p.extract_text() or "" for p in pdf.pages]
    print(f"Estratte {len(pages_text)} pagine.")

    # Identifica cover
    cover_indices = [
        i
        for i, t in enumerate(pages_text)
        if "Tipo Materiale" in t and "Impegno del materiale" in t
    ]
    print(f"Cover identificate: {len(cover_indices)}")

    # Parse + abbinamento al deposito
    turni = []
    for ci in cover_indices:
        cover = parse_cover(pages_text[ci])
        cover["cover_page"] = ci + 1  # 1-indexed
        deposito = None
        for j in range(ci + 1, min(ci + 10, len(pages_text))):
            if j in cover_indices:
                break
            d = parse_omv_from_gantt(pages_text[j])
            if d:
                deposito = d
                break
        cover["deposito"] = deposito
        turni.append(cover)

    senza = [t for t in turni if not t.get("deposito")]
    if senza:
        print(
            f"ATTENZIONE: {len(senza)} turni senza deposito: "
            f"{[t.get('numero_turno') for t in senza]}"
        )

    # Aggregazione
    deposito_pezzi = defaultdict(lambda: defaultdict(int))
    deposito_turni = defaultdict(list)
    deposito_materiali = defaultdict(set)
    for t in turni:
        dep = t.get("deposito") or "SCONOSCIUTO"
        deposito_turni[dep].append(t.get("numero_turno") or f"?{t['cover_page']}")
        if t.get("tipo_materiale"):
            deposito_materiali[dep].add(t["tipo_materiale"])
        for nome, qty in t.get("pezzi", []):
            deposito_pezzi[dep][nome] += qty

    out = {
        "depositi": {
            dep: {
                "turni": deposito_turni[dep],
                "pezzi_totali": dict(deposito_pezzi[dep]),
                "tipi_materiale_unici": sorted(deposito_materiali[dep]),
            }
            for dep in deposito_turni
        },
        "turni_dettaglio": turni,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nSalvato: {out_path} ({out_path.stat().st_size} bytes)")

    print("\nRiepilogo:")
    deps_sorted = sorted(deposito_turni.keys(), key=lambda d: -len(deposito_turni[d]))
    for dep in deps_sorted:
        n_turni = len(deposito_turni[dep])
        n_tipi = len(deposito_pezzi[dep])
        n_pezzi = sum(deposito_pezzi[dep].values())
        print(
            f"  {dep:25s}  turni={n_turni:3d}  tipi_pezzo={n_tipi:2d}  "
            f"pezzi_tot={n_pezzi:4d}"
        )


if __name__ == "__main__":
    main()
