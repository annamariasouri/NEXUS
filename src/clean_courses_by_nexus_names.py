"""
Filter Courses.csv: keep rows where at least one lecturer token matches an entry
in nexus names all.csv (exact match after whitespace normalization).

Optional: expand lecturer cells from "Surname I." to full roster names using
Full timers ORCID.csv and Part timers ORCID.csv (Name column: "Surname Givenname").

Default paths resolve to the parent folder of the NEXUS app (…/NEXUS/Courses.csv).
"""
from __future__ import annotations

import argparse
import re
import unicodedata
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


# --- Lecturer expansion: "Charitou M." -> "Charitou Melita" from roster Name ---

_ROSTER_SURNAME_INITIAL = re.compile(r"^(.+?)\s+([A-Za-z])\s*\.\s*$")


def _ascii_fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _parse_roster_name(name: object) -> tuple[str, str] | None:
    """Roster 'Surname Givenname' -> (surname, first_initial)."""
    name = str(name).strip() if name is not None and not (isinstance(name, float) and pd.isna(name)) else ""
    if not name or name.lower() == "nan":
        return None
    parts = name.split()
    if len(parts) < 2:
        return None
    given = parts[-1]
    surname = " ".join(parts[:-1])
    if not given:
        return None
    return surname, given[0].upper()


def build_roster_lecturer_map(full_timer_csv: Path, part_timer_csv: Path) -> dict[tuple[str, str], str]:
    """
    Map (ascii_folded_surname, first_initial) -> exact roster 'Name' string.
    Skips ambiguous duplicate keys.
    """
    buckets: dict[tuple[str, str], list[str]] = {}
    for path in (full_timer_csv, part_timer_csv):
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except OSError:
            df = pd.read_csv(path, dtype=str, encoding="utf-8")
        if "Name" not in df.columns:
            continue
        for val in df["Name"].tolist():
            parsed = _parse_roster_name(val)
            if not parsed:
                continue
            sur, ini = parsed
            key = (_ascii_fold(sur), ini)
            buckets.setdefault(key, []).append(str(val).strip())

    out: dict[tuple[str, str], str] = {}
    for key, names in buckets.items():
        uniq = list(dict.fromkeys(names))
        if len(uniq) == 1:
            out[key] = uniq[0]
    return out


def expand_lecturer_cell(cell: object, roster_map: dict[tuple[str, str], str]) -> str:
    """
    Replace a single 'Surname I.' token with roster full name when uniquely mappable.
    Leaves compound lecturers (&), non-matching, or already-expanded values unchanged.
    """
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    raw = str(cell).strip()
    if not raw or raw.lower() == "nan":
        return raw
    if "&" in raw:
        return raw
    m = _ROSTER_SURNAME_INITIAL.match(raw)
    if not m:
        return raw
    sur, ini = m.group(1).strip(), m.group(2).upper()
    key = (_ascii_fold(sur), ini)
    full = roster_map.get(key)
    return full if full is not None else raw


def apply_lecturer_roster_expansion(df: pd.DataFrame, lec_col: str, roster_map: dict[tuple[str, str], str]) -> None:
    if lec_col not in df.columns or not roster_map:
        return
    df[lec_col] = df[lec_col].map(lambda c: expand_lecturer_cell(c, roster_map))


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
    parser.add_argument(
        "--no-expand-lecturers",
        action="store_true",
        help="Do not replace 'Surname I.' with full names from Full/Part timer ORCID CSVs.",
    )
    parser.add_argument(
        "--enrich-only",
        type=Path,
        metavar="CSV",
        help="Skip filtering: load this CSV (same shape as Courses_cleaned), expand lecturers, write --output.",
    )
    args = parser.parse_args()

    base_app = Path(__file__).resolve().parents[1]
    default_parent = base_app.parent
    courses_path = args.courses or (default_parent / "Courses.csv")
    names_path = args.names or (default_parent / "nexus names all.csv")
    output_path = args.output or (default_parent / "Courses_cleaned.csv")

    if args.enrich_only:
        inp = args.enrich_only
        if not inp.exists():
            raise SystemExit(f"Not found: {inp}")
        df = pd.read_csv(inp, dtype=str, encoding="utf-8-sig", skiprows=1)
        lec_col = "Lecturer"
        if lec_col not in df.columns:
            raise SystemExit(f"Expected column '{lec_col}' in {inp}, got {list(df.columns)}")
        if not args.no_expand_lecturers:
            roster_map = build_roster_lecturer_map(
                base_app / "Full timers ORCID.csv",
                base_app / "Part timers ORCID.csv",
            )
            before_lec = df[lec_col].astype(str)
            apply_lecturer_roster_expansion(df, lec_col, roster_map)
            n_expanded = int((before_lec != df[lec_col].astype(str)).sum())
            print(f"Lecturer cells expanded from roster (where unique match): {n_expanded}")
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(",,,,,\n")
            df.to_csv(f, index=False)
        print(f"Wrote: {output_path.name}")
        return

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

    if not args.no_expand_lecturers:
        roster_map = build_roster_lecturer_map(
            base_app / "Full timers ORCID.csv",
            base_app / "Part timers ORCID.csv",
        )
        before_lec = cleaned[lec_col].astype(str)
        apply_lecturer_roster_expansion(cleaned, lec_col, roster_map)
        n_expanded = int((before_lec != cleaned[lec_col].astype(str)).sum())
        print(f"Lecturer cells expanded from roster (where unique match): {n_expanded}")

    # Preserve leading blank row + header like the source file (optional consistency)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",,,,,\n")
        cleaned.to_csv(f, index=False)

    print(f"Approved names: {len(approved)}")
    print(f"Rows before: {before} | after: {after} | removed: {before - after}")
    print(f"Wrote: {output_path.name}")


if __name__ == "__main__":
    main()
