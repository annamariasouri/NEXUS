"""
Extract tables (and fallback text) from lecturer / course schedule PDF reports.

Typical use after copying PDFs into the repo or passing full paths:

  python scripts/extract_lecturer_report_pdfs.py path/to/report1.pdf path/to/report2.pdf

Outputs under outputs/pdf_extract/<pdf_stem>_tables.csv and _pages.txt if needed.
Requires: pip install pdfplumber
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

try:
    import pdfplumber
except ImportError:
    print("Install pdfplumber: pip install pdfplumber", file=sys.stderr)
    raise


def slug_stem(p: Path) -> str:
    s = p.stem
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE)
    return s.strip("_") or "report"


def extract_tables(pdf_path: Path, out_dir: Path) -> tuple[Path | None, Path]:
    """Return (csv path if any tables, always text path)."""
    stem = slug_stem(pdf_path)
    all_rows: list[list[str | None]] = []
    text_chunks: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                text_chunks.append(f"--- Page {i + 1} ---\n{text}")

            tables = page.extract_tables() or []
            for t_idx, table in enumerate(tables):
                if not table or not any(any(c is not None and str(c).strip() for c in row) for row in table):
                    continue
                header = [str(c).strip() if c is not None else "" for c in table[0]]
                body = table[1:]
                for row in body:
                    cells = [str(c).strip() if c is not None else "" for c in row]
                    # pad / trim to header width
                    while len(cells) < len(header):
                        cells.append("")
                    cells = cells[: len(header)]
                    if not any(cells):
                        continue
                    all_rows.append(dict(zip(header, cells, strict=False)))

    txt_path = out_dir / f"{stem}_pages.txt"
    txt_path.write_text("\n\n".join(text_chunks), encoding="utf-8")

    if not all_rows:
        return None, txt_path

    df = pd.DataFrame(all_rows)
    csv_path = out_dir / f"{stem}_tables.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path, txt_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract tables from lecturer/course PDF reports.")
    ap.add_argument("pdfs", nargs="+", type=Path, help="One or more PDF file paths")
    ap.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: repo outputs/pdf_extract)",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = args.out_dir or (repo_root / "outputs" / "pdf_extract")
    out_dir.mkdir(parents=True, exist_ok=True)

    for pdf in args.pdfs:
        if not pdf.is_file():
            print(f"Skip (not a file): {pdf}", file=sys.stderr)
            continue
        if pdf.suffix.lower() != ".pdf":
            print(f"Skip (not .pdf): {pdf}", file=sys.stderr)
            continue
        csv_path, txt_path = extract_tables(pdf, out_dir)
        print(f"{pdf.name}:")
        print(f"  text: {txt_path}")
        if csv_path:
            print(f"  tables CSV: {csv_path} ({pd.read_csv(csv_path).shape[0]} rows)")
        else:
            print("  tables CSV: (none detected — use text file or adjust PDF / try camelot)")


if __name__ == "__main__":
    main()
