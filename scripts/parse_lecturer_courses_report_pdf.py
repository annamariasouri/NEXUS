"""
Parse UNIC-style Lecturer Teaching Load PDF → CSV (Spring 2025).

pdfplumber emits each row as space-separated tokens (not tabs), in order:
  Course Id, Title..., Section, Course Schedule, NTH, CR, TH

Output: Lecturer name, Rank, Course ID, Title, Section, Course schedule
Includes all lecturers (part-time and full-time); Rank is taken from the PDF.
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
    print("pip install pdfplumber", file=sys.stderr)
    raise


def extract_lines(pdf_path: Path) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                lines.append(line.rstrip())
    return lines


def _is_number(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def parse_course_row(line: str) -> tuple[str, str, str, str] | None:
    """Return (course_id, title, section, schedule) or None."""
    if "\t" in line:
        return _parse_course_row_tab(line)
    parts = line.split()
    if len(parts) < 6:
        return None
    if not all(_is_number(parts[i]) for i in (-3, -2, -1)):
        return None
    rest = parts[:-3]
    if not rest:
        return None
    cid = rest[0]
    if "-" not in cid or not cid[0].isalpha():
        return None
    if not re.match(r"^[A-Z][A-Z0-9-]+$", cid):
        return None

    sec_idx: int | None = None
    for i in range(1, len(rest)):
        tok = rest[i]
        if tok.isdigit() and 1 <= len(tok) <= 2:
            sec_idx = i
            break
    if sec_idx is None:
        return None

    title = " ".join(rest[1:sec_idx]).strip()
    schedule = " ".join(rest[sec_idx + 1 :]).strip()
    if not title or not schedule:
        return None
    return cid, title, rest[sec_idx], schedule


def _parse_course_row_tab(line: str) -> tuple[str, str, str, str] | None:
    """Fallback when PDF text still uses tabs (e.g. other extractors)."""
    m = re.match(
        r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s+(\d+)\t(.+?)\t(\S+)\t(.+)$",
        line,
    )
    if not m:
        return None
    course_id, section, mid, _nth, schedule = m.groups()
    tm = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$", mid.strip())
    if not tm:
        return None
    title = tm.group(1).strip()
    return course_id, title, section, schedule.strip()


def iter_lecturer_blocks(lines: list[str]):
    lecturer: str | None = None
    rank_raw: str | None = None
    in_block = False
    buf: list[str] = []

    def flush():
        nonlocal lecturer, rank_raw, buf, in_block
        if lecturer and rank_raw is not None:
            yield lecturer, rank_raw, buf
        buf = []
        in_block = False

    for line in lines:
        if line.startswith("Lecturer: "):
            yield from flush()
            lecturer = line[len("Lecturer: ") :].strip()
            rank_raw = None
            in_block = True
            continue
        if not in_block or lecturer is None:
            continue
        if line.startswith("Rank: "):
            rank_raw = line[len("Rank: ") :].strip()
            continue
        buf.append(line)

    yield from flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV path (default: spring_2025_lecturer_courses.csv next to PDF)",
    )
    args = ap.parse_args()

    if not args.pdf.is_file():
        print(f"Not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    lines = extract_lines(args.pdf)
    rows: list[dict[str, str]] = []

    for lecturer, rank_raw, block_lines in iter_lecturer_blocks(lines):
        for line in block_lines:
            if not line.strip():
                continue
            if any(
                line.startswith(p)
                for p in (
                    "TH:",
                    "COT:",
                    "Course Id",
                    "Criteria:",
                    "Lecturer Teaching",
                    "[Schools]",
                    "University of Nicosia",
                    "-- ",
                    "Semester:",
                    "User:",
                )
            ):
                continue
            if "Grant Total" in line:
                continue

            parsed = parse_course_row(line)
            if not parsed:
                continue
            cid, title, sec, sched = parsed
            if sched.strip().casefold() == "unscheduled":
                continue
            rows.append(
                {
                    "Lecturer name": lecturer,
                    "Rank": rank_raw,
                    "Course ID": cid,
                    "Title": title,
                    "Section": sec,
                    "Course schedule": sched,
                }
            )

    out = args.output or (args.pdf.parent / "spring_2025_lecturer_courses.csv")
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
