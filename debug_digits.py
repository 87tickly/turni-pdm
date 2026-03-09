"""
Diagnostic: extract raw digit characters from a specific PDF page
and show how they cluster into train IDs vs what the real train IDs should be.
"""
import pdfplumber
import sys
from collections import defaultdict

PDF_PATH = r"uploads/Turno Materiale Trenord dal 2_3_26.pdf"

# Constants from pdf_parser.py
DATA_AREA_LEFT_X = 135.0
PER_COLUMN_X = 655.0
VERT_DIGIT_SIZE_MIN = 4.0
VERT_DIGIT_SIZE_MAX = 6.5
X_CLUSTER_TOL = 1.5
VERT_DIGIT_MAX_Y_GAP = 8.0

def analyze_page(page_num: int):
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[page_num]
        chars = page.chars
        words = page.extract_words()

        print(f"\n{'='*80}")
        print(f"PAGE {page_num + 1} (0-indexed: {page_num})")
        print(f"Total chars: {len(chars)}, Total words: {len(words)}")
        print(f"{'='*80}")

        # Show all turno-related text in header
        print("\n--- HEADER TEXT (top < 110) ---")
        header_words = [w for w in words if w["top"] < 110]
        for w in header_words:
            print(f"  '{w['text']}' size={w.get('height',0):.1f} x={w['x0']:.1f} y={w['top']:.1f}")

        # Find all single digits in the data area
        all_digits = []
        for c in chars:
            if (c["text"].isdigit()
                and len(c["text"]) == 1
                and c["x0"] > DATA_AREA_LEFT_X
                and c["x0"] < PER_COLUMN_X
                and c["top"] > 110):
                all_digits.append(c)

        print(f"\n--- ALL SINGLE DIGITS IN DATA AREA ---")
        print(f"Total: {len(all_digits)}")

        # Show distribution of sizes
        sizes = [c["size"] for c in all_digits]
        if sizes:
            size_counts = defaultdict(int)
            for s in sizes:
                bucket = round(s, 1)
                size_counts[bucket] += 1
            print("\nSize distribution:")
            for size_val in sorted(size_counts.keys()):
                bar = "#" * min(size_counts[size_val], 50)
                print(f"  {size_val:5.1f} : {size_counts[size_val]:4d} {bar}")

        # Now filter with current params
        candidates = [
            c for c in all_digits
            if VERT_DIGIT_SIZE_MIN <= c["size"] <= VERT_DIGIT_SIZE_MAX
        ]
        print(f"\nFiltered by size [{VERT_DIGIT_SIZE_MIN}, {VERT_DIGIT_SIZE_MAX}]: {len(candidates)} candidates")

        # Show excluded digits and their sizes
        excluded = [c for c in all_digits if c not in candidates]
        excl_sizes = defaultdict(int)
        for c in excluded:
            excl_sizes[round(c["size"], 1)] += 1
        if excl_sizes:
            print(f"Excluded {len(excluded)} digits with sizes:")
            for s in sorted(excl_sizes.keys()):
                print(f"  {s:.1f}: {excl_sizes[s]}")

        # Cluster by x
        if not candidates:
            print("No candidates to cluster!")
            return

        sorted_items = sorted(candidates, key=lambda c: c["x0"])
        clusters = []
        current_cluster = [sorted_items[0]]
        for item in sorted_items[1:]:
            if abs(item["x0"] - current_cluster[-1]["x0"]) <= X_CLUSTER_TOL:
                current_cluster.append(item)
            else:
                clusters.append(current_cluster)
                current_cluster = [item]
        clusters.append(current_cluster)

        print(f"\n--- X CLUSTERS (tol={X_CLUSTER_TOL}) ---")
        print(f"Total clusters: {len(clusters)}")

        for ci, cluster in enumerate(clusters):
            cluster.sort(key=lambda c: c["top"])
            median_x = cluster[len(cluster) // 2]["x0"]

            # Split into runs by y-gap
            runs = []
            current_run = [cluster[0]]
            for c in cluster[1:]:
                gap = c["top"] - current_run[-1]["top"]
                if gap <= VERT_DIGIT_MAX_Y_GAP:
                    current_run.append(c)
                else:
                    runs.append(current_run)
                    current_run = [c]
            runs.append(current_run)

            valid_runs = [r for r in runs if 4 <= len(r) <= 6]

            if valid_runs:
                print(f"\n  Cluster at x={median_x:.1f} ({len(cluster)} digits, {len(runs)} runs)")
                for ri, run in enumerate(runs):
                    text = "".join(c["text"] for c in run)
                    y_range = f"y={run[0]['top']:.1f}..{run[-1]['top']:.1f}"
                    status = "VALID" if 4 <= len(run) <= 6 else f"skip ({len(run)} digits)"
                    gaps = [f"{run[i+1]['top']-run[i]['top']:.1f}" for i in range(len(run)-1)]
                    sizes_str = [f"{c['size']:.1f}" for c in run]
                    print(f"    Run {ri}: '{text}' len={len(run)} {y_range} {status}")
                    print(f"           gaps={gaps}")
                    print(f"           sizes={sizes_str}")
                    print(f"           x0s={[round(c['x0'],1) for c in run]}")

        # Also show ALL words/text in the data area that look like train numbers
        print(f"\n--- HORIZONTAL MULTI-DIGIT TEXT IN DATA AREA ---")
        for w in words:
            if (w["top"] > 110
                and w["x0"] > DATA_AREA_LEFT_X
                and w["x0"] < PER_COLUMN_X
                and w["text"].isdigit()
                and len(w["text"]) >= 4):
                print(f"  '{w['text']}' x={w['x0']:.1f} y={w['top']:.1f} size approx")


if __name__ == "__main__":
    # Try pages around turno 1106 (Cremona)
    # Let's first find what page has turno 1106
    pages_to_check = []

    if len(sys.argv) > 1:
        pages_to_check = [int(p) for p in sys.argv[1:]]
    else:
        # Scan for turno numbers to find the right pages
        print("Scanning for turno numbers containing '110'...")
        import pdfplumber as plb
        with plb.open(PDF_PATH) as pdf:
            for pi in range(min(len(pdf.pages), 353)):
                page = pdf.pages[pi]
                words = page.extract_words()
                for w in words:
                    if w["text"].isdigit() and len(w["text"]) == 4 and w["text"].startswith("110"):
                        if w.get("size", w.get("height", 0)) >= 15 or w["top"] < 60:
                            print(f"  Page {pi} (1-based: {pi+1}): turno {w['text']} at y={w['top']:.1f}")
                            if pi not in pages_to_check:
                                pages_to_check.append(pi)
                                if len(pages_to_check) >= 3:
                                    break
                if len(pages_to_check) >= 3:
                    break

    if not pages_to_check:
        print("No pages found, trying first 3 data pages...")
        pages_to_check = [2, 3, 4]

    for p in pages_to_check:
        analyze_page(p)
