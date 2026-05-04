"""
Filter Courses.csv: keep rows where at least one lecturer token matches an entry
in nexus names all.csv (exact match after whitespace normalization).

Default paths resolve to the parent folder of the NEXUS app (…/NEXUS/Courses.csv).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

SPLIT_PATTERN = re.compile(r"\s*&\s*|\s*;\s*", re.IGNORECASE)


def _norm(s: str) -> str:
    s = str(s).replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .")


def lecturer_tokens(cell: object) -> list[str]:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return []
    raw = _norm(cell)
    if not raw:
        return []
    parts = SPLIT_PATTERN.split(raw)
    tokens: list[str] = []
    for p in parts:
        t = _norm(p)
        if t:
            tokens.append(t)
    if not tokens:
        tokens = [raw]
    if raw not in tokens:
        tokens.insert(0, raw)
    return list(dict.fromkeys(tokens))


def row_matches(lecturer_cell: object, approved: set[str]) -> bool:
    for tok in lecturer_tokens(lecturer_cell):
        if tok in approved:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--courses",
        type=Path,
        help="Path to Courses CSV (header after optional blank rows).",
    )
    parser.add_argument(
        "--names",
        type=Path,
        help="Path to NEXUS names CSV (column Names).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for filtered CSV output.",
    )
    args = parser.parse_args()

    base_app = Path(__file__).resolve().parents[1]
    default_parent = base_app.parent
    courses_path = args.courses or (default_parent / "Courses.csv")
    names_path = args.names or (default_parent / "nexus names all.csv")
    output_path = args.output or (default_parent / "Courses_cleaned.csv")

    names_df = pd.read_csv(names_path, dtype=str, encoding="utf-8")
    if "Names" not in names_df.columns:
        raise SystemExit(f"Expected column 'Names' in {names_path}, got {list(names_df.columns)}")

    approved: set[str] = set()
    for val in names_df["Names"].tolist():
        t = _norm(val)
        if t and t.lower() != "names":
            approved.add(t)

    courses_df = pd.read_csv(courses_path, dtype=str, encoding="cp1252", skiprows=1)
    lec_col = "Lecturer"
    if lec_col not in courses_df.columns:
        raise SystemExit(f"Expected column '{lec_col}' in {courses_path}, got {list(courses_df.columns)}")

    before = len(courses_df)
    mask = courses_df[lec_col].map(lambda c: row_matches(c, approved))
    cleaned = courses_df.loc[mask].copy()
    sort_cols = [c for c in ("Lecturer", "Course ID", "Section") if c in cleaned.columns]
    if sort_cols:
        cleaned = cleaned.sort_values(by=sort_cols, na_position="last", kind="mergesort")
    after = len(cleaned)

    # Preserve leading blank row + header like the source file (optional consistency)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",,,,,\n")
        cleaned.to_csv(f, index=False)

    print(f"Approved names: {len(approved)}")
    print(f"Rows before: {before} | after: {after} | removed: {before - after}")
    print(f"Wrote: {output_path.name}")


if __name__ == "__main__":
    main()
