import argparse
import datetime as dt
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
ORCID_PUBLIC_WORKS_URL = "https://pub.orcid.org/v3.0/{orcid}/works"

ORCID_JOURNAL_TYPES = frozenset({"journal-article", "review"})


class ScopusClient:
    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, count: int = 25) -> List[Dict]:
        entries: List[Dict] = []
        start = 0

        while True:
            params = {
                "query": query,
                "count": count,
                "start": start,
                "view": "STANDARD",
            }
            headers = {
                "X-ELS-APIKey": self.api_key,
                "Accept": "application/json",
            }
            response = requests.get(
                SCOPUS_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()

            search_results = payload.get("search-results", {})
            batch = search_results.get("entry", [])
            if not batch:
                break

            entries.extend(batch)

            items_per_page = int(search_results.get("opensearch:itemsPerPage", len(batch)))
            total_results = int(search_results.get("opensearch:totalResults", len(entries)))
            start += items_per_page
            if start >= total_results:
                break

        return entries

    def search_by_orcid(self, orcid: str, min_year: int, count: int = 25) -> List[Dict]:
        # Fetch all publication types and enforce year filter at API level.
        query = f"ORCID({orcid}) AND PUBYEAR > {min_year - 1}"
        return self.search(query=query, count=count)

    def search_by_scopus_id(self, scopus_id: str, min_year: int, count: int = 25) -> List[Dict]:
        # AU-ID is the Scopus Author ID query field.
        query = f"AU-ID({scopus_id}) AND PUBYEAR > {min_year - 1}"
        return self.search(query=query, count=count)


def normalize_orcid(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    match = re.search(r"(\d{4}-\d{4}-\d{4}-[\dXx]{4})", text)
    if not match:
        return ""
    return match.group(1).upper()


def normalize_scopus_id(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    # Guard against CSV numeric parsing artifacts like "35490355500.0".
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    digits = re.sub(r"\D", "", text)
    return digits


def normalize_research_field(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    # Remove trailing markers like "Management*".
    text = re.sub(r"\*+$", "", text).strip()
    return text


def _row_str(row: pd.Series, *column_names: str) -> str:
    """First non-empty match among possible CSV header spellings (e.g. 'Department' vs 'Department ')."""
    for key in column_names:
        if key not in row.index:
            continue
        raw = row.get(key, "")
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        text = str(raw).strip().replace("\u00a0", " ")
        if text and text.lower() != "nan":
            return text
    return ""


def has_recent_results(entries: List[Dict], min_year: int) -> bool:
    return any(parse_year(entry) >= min_year for entry in entries)


def parse_year(entry: Dict) -> int:
    date_value = entry.get("prism:coverDate", "")
    if date_value:
        try:
            return int(str(date_value)[:4])
        except ValueError:
            return 0

    year_value = entry.get("prism:coverDisplayDate", "")
    year_match = re.search(r"(19|20)\d{2}", str(year_value))
    if year_match:
        return int(year_match.group(0))

    return 0


def is_journal(entry: Dict) -> bool:
    aggregation_type = str(entry.get("prism:aggregationType", "")).strip().lower()
    return aggregation_type == "journal"


def normalize_publication_type(entry: Dict) -> str:
    value = str(entry.get("prism:aggregationType", "")).strip().lower()
    mapping = {
        "journal": "Journal",
        "conference proceeding": "Conference",
        "book": "Book",
        "book series": "Book Series",
        "trade journal": "Trade Journal",
    }
    return mapping.get(value, value.title() if value else "Unknown")


def normalize_doi_for_match(value: str) -> str:
    if not value:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = s.split("?", 1)[0].strip()
    return s


def normalize_title_for_match(value: str) -> str:
    if not value:
        return ""
    s = str(value).lower()
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def orcid_work_type_label(orcid_type: str) -> Tuple[str, bool]:
    raw = str(orcid_type or "").strip().lower().replace("_", "-")
    if raw in ORCID_JOURNAL_TYPES:
        return "Journal", True
    if "conference" in raw or raw in {"proceedings-article"}:
        return "Conference", False
    if "book" in raw:
        if "chapter" in raw:
            return "Book Series", False
        return "Book", False
    if raw in {"dissertation-thesis", "dissertation"}:
        return "Dissertation", False
    if raw in {"report", "technical-report", "working-paper"}:
        return "Report", False
    if raw:
        return raw.replace("-", " ").title(), False
    return "Unknown", False


def _orcid_title(ws: Dict) -> str:
    title_block = ws.get("title") or {}
    inner = title_block.get("title") or {}
    return str(inner.get("value", "") or "").strip()


def _orcid_journal_title(ws: Dict) -> str:
    jt = ws.get("journal-title") or {}
    return str(jt.get("value", "") or "").strip()


def _first_orcid_doi(ws: Dict) -> str:
    ext_root = ws.get("external-ids") or {}
    items = ext_root.get("external-id") or []
    if isinstance(items, dict):
        items = [items]
    for item in items:
        if str(item.get("external-id-type", "")).strip().lower() != "doi":
            continue
        val = item.get("external-id-value")
        if val:
            return str(val).strip()
    return ""


def parse_orcid_publication_year(ws: Dict) -> int:
    pd_obj = ws.get("publication-date") or {}
    year_obj = pd_obj.get("year")
    if isinstance(year_obj, dict):
        val = year_obj.get("value")
        if val is not None and str(val).strip():
            try:
                return int(str(val).strip()[:4])
            except ValueError:
                pass
    return 0


def fetch_orcid_work_summaries(orcid_id: str, session: requests.Session, timeout: int = 45) -> List[Dict]:
    """Public ORCID read API — no OAuth needed for public record visibility."""
    url = ORCID_PUBLIC_WORKS_URL.format(orcid=orcid_id)
    headers = {
        "Accept": "application/json",
        "User-Agent": "NEXUS-publications-pipeline/1.0 (https://github.com)",
    }
    response = session.get(url, headers=headers, timeout=timeout)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    payload = response.json()
    summaries: List[Dict] = []
    for group in payload.get("group", []) or []:
        for ws in group.get("work-summary", []) or []:
            summaries.append(ws)
    return summaries


def build_scopus_match_sets(person_scopus_pubs: List[Dict]) -> Tuple[Set[str], Set[Tuple[str, int]]]:
    dois: Set[str] = set()
    title_years: Set[Tuple[str, int]] = set()
    for pub in person_scopus_pubs:
        dn = normalize_doi_for_match(str(pub.get("doi", "") or ""))
        if dn:
            dois.add(dn)
        tn = normalize_title_for_match(str(pub.get("title", "") or ""))
        y = int(pub.get("year", 0) or 0)
        if tn and y > 0:
            title_years.add((tn, y))
    return dois, title_years


def orcid_work_matches_scopus(
    doi_norm: str, title_norm: str, year: int, scopus_dois: Set[str], scopus_title_years: Set[Tuple[str, int]]
) -> bool:
    if doi_norm and doi_norm in scopus_dois:
        return True
    if not title_norm or year <= 0:
        return False
    for dy in (year - 1, year, year + 1):
        if (title_norm, dy) in scopus_title_years:
            return True
    return False


def merge_orcid_only_rows(
    orcid_id: str,
    min_year: int,
    meta: Dict,
    person_scopus_pubs: List[Dict],
    session: requests.Session,
    orcid_delay_sec: float = 0.2,
) -> Tuple[List[Dict], str]:
    """Returns ORCID-sourced rows that do not match existing Scopus rows."""
    try:
        if orcid_delay_sec > 0:
            time.sleep(orcid_delay_sec)
        summaries = fetch_orcid_work_summaries(orcid_id=orcid_id, session=session)
    except requests.RequestException as exc:
        return [], f"ORCID API error: {exc}"

    scopus_dois, scopus_title_years = build_scopus_match_sets(person_scopus_pubs)
    seen_put_codes: Set = set()
    rows: List[Dict] = []

    for ws in summaries:
        put_code = ws.get("put-code")
        if put_code is not None:
            if put_code in seen_put_codes:
                continue
            seen_put_codes.add(put_code)

        year = parse_orcid_publication_year(ws)
        if year < min_year:
            continue

        title = _orcid_title(ws)
        doi_raw = _first_orcid_doi(ws)
        doi_norm = normalize_doi_for_match(doi_raw)
        title_norm = normalize_title_for_match(title)

        if orcid_work_matches_scopus(doi_norm, title_norm, year, scopus_dois, scopus_title_years):
            continue

        pub_label, is_j = orcid_work_type_label(str(ws.get("type", "") or ""))
        journal_display = _orcid_journal_title(ws)
        cover_date = f"{year}-01-01" if year else ""

        rows.append(
            {
                "name": meta["name"],
                "department": meta["department"],
                "email": meta["email"],
                "telephone": meta["telephone"],
                "rank": meta["rank"],
                "research_field": meta["research_field"],
                "unic_entity": meta["unic_entity"],
                "orcid": meta["orcid"],
                "scopus_id": meta["scopus_id"],
                "identifier_source": meta["identifier_source"],
                "title": title,
                "publication_type": pub_label,
                "is_journal": is_j,
                "source_title": journal_display,
                "year": year,
                "cover_date": cover_date,
                "doi": doi_raw,
                "eid": "",
                "record_source": "ORCID",
                "indexed_in_scopus": "No",
                "orcid_put_code": str(put_code) if put_code is not None else "",
            }
        )

    return rows, ""


def build_rows(
    input_df: pd.DataFrame, client: ScopusClient, min_year: int, http_session: requests.Session
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    publication_rows: List[Dict] = []
    summary_rows: List[Dict] = []

    for _, row in input_df.iterrows():
        name = _row_str(row, "Name")
        department = _row_str(row, "Department ", "Department")
        email = _row_str(row, "Email")
        telephone = _row_str(row, "Telephone")
        rank = _row_str(row, "Rank ", "Rank")
        research_field = normalize_research_field(_row_str(row, "Research Field"))
        raw_orcid = _row_str(row, "ORCID")
        raw_scopus_id = _row_str(row, "Scopus ID")
        orcid = normalize_orcid(raw_orcid)
        scopus_id = normalize_scopus_id(raw_scopus_id)
        unic_entity = _row_str(row, "UNIC Entity")

        if not name:
            continue

        if not orcid and not scopus_id:
            summary_rows.append(
                {
                    "name": name,
                    "department": department,
                    "email": email,
                    "telephone": telephone,
                    "rank": rank,
                    "research_field": research_field,
                    "unic_entity": unic_entity,
                    "orcid": raw_orcid,
                    "scopus_id": raw_scopus_id,
                    "identifier_source": "",
                    "scopus_publications_last_6_years": 0,
                    "non_scopus_publications_last_6_years": 0,
                    "non_scopus_journal_publications_last_6_years": 0,
                    "total_publications_last_6_years": 0,
                    "journal_publications_last_6_years": 0,
                    "recent_3_articles": "",
                    "status": "does not fulfill requirements",
                    "notes": "Missing/invalid ORCID and Scopus ID",
                }
            )
            continue

        entries: List[Dict] = []
        identifier_source = ""
        notes = ""

        if orcid:
            try:
                entries = client.search_by_orcid(orcid=orcid, min_year=min_year)
                identifier_source = "orcid"
            except requests.HTTPError as exc:
                summary_rows.append(
                    {
                        "name": name,
                        "department": department,
                        "email": email,
                        "telephone": telephone,
                        "rank": rank,
                        "research_field": research_field,
                        "unic_entity": unic_entity,
                        "orcid": orcid,
                        "scopus_id": scopus_id,
                        "identifier_source": "",
                        "scopus_publications_last_6_years": 0,
                        "non_scopus_publications_last_6_years": 0,
                        "non_scopus_journal_publications_last_6_years": 0,
                        "total_publications_last_6_years": 0,
                        "journal_publications_last_6_years": 0,
                        "recent_3_articles": "",
                        "status": "does not fulfill requirements",
                        "notes": f"Scopus API error (ORCID): {exc}",
                    }
                )
                continue

            # If ORCID has no recent matches, fallback to Scopus ID when available.
            if not has_recent_results(entries, min_year=min_year) and scopus_id:
                try:
                    entries = client.search_by_scopus_id(scopus_id=scopus_id, min_year=min_year)
                    identifier_source = "scopus_id_fallback_no_orcid_results"
                    notes = "No ORCID results; used Scopus ID fallback"
                except requests.HTTPError as exc:
                    summary_rows.append(
                        {
                            "name": name,
                            "department": department,
                            "email": email,
                            "telephone": telephone,
                            "rank": rank,
                            "research_field": research_field,
                            "unic_entity": unic_entity,
                            "orcid": orcid,
                            "scopus_id": scopus_id,
                            "identifier_source": "",
                            "scopus_publications_last_6_years": 0,
                            "non_scopus_publications_last_6_years": 0,
                            "non_scopus_journal_publications_last_6_years": 0,
                            "total_publications_last_6_years": 0,
                            "journal_publications_last_6_years": 0,
                            "recent_3_articles": "",
                            "status": "does not fulfill requirements",
                            "notes": f"Scopus API error (Scopus ID fallback): {exc}",
                        }
                    )
                    continue
        else:
            try:
                entries = client.search_by_scopus_id(scopus_id=scopus_id, min_year=min_year)
                identifier_source = "scopus_id"
            except requests.HTTPError as exc:
                summary_rows.append(
                    {
                        "name": name,
                        "department": department,
                        "email": email,
                        "telephone": telephone,
                        "rank": rank,
                        "research_field": research_field,
                        "unic_entity": unic_entity,
                        "orcid": orcid,
                        "scopus_id": scopus_id,
                        "identifier_source": "",
                        "scopus_publications_last_6_years": 0,
                        "non_scopus_publications_last_6_years": 0,
                        "non_scopus_journal_publications_last_6_years": 0,
                        "total_publications_last_6_years": 0,
                        "journal_publications_last_6_years": 0,
                        "recent_3_articles": "",
                        "status": "does not fulfill requirements",
                        "notes": f"Scopus API error (Scopus ID): {exc}",
                    }
                )
                continue

        normalized_orcid_for_output = orcid

        person_pubs_scopus: List[Dict] = []
        for entry in entries:
            year = parse_year(entry)
            if year < min_year:
                continue

            title = str(entry.get("dc:title", "")).strip()
            publication_type = normalize_publication_type(entry)
            source_title = str(entry.get("prism:publicationName", "")).strip()
            doi = str(entry.get("prism:doi", "")).strip()
            eid = str(entry.get("eid", "")).strip()
            cover_date = str(entry.get("prism:coverDate", "")).strip()
            is_journal_pub = is_journal(entry)

            pub_row = {
                "name": name,
                "department": department,
                "email": email,
                "telephone": telephone,
                "rank": rank,
                "research_field": research_field,
                "unic_entity": unic_entity,
                "orcid": normalized_orcid_for_output,
                "scopus_id": scopus_id,
                "identifier_source": identifier_source,
                "title": title,
                "publication_type": publication_type,
                "is_journal": is_journal_pub,
                "source_title": source_title,
                "year": year,
                "cover_date": cover_date,
                "doi": doi,
                "eid": eid,
                "record_source": "Scopus",
                "indexed_in_scopus": "Yes",
                "orcid_put_code": "",
            }
            person_pubs_scopus.append(pub_row)

        person_pubs_scopus = list(
            {
                (
                    item.get("eid")
                    or f"{item.get('title')}|{item.get('year')}|{item.get('source_title')}"
                ): item
                for item in person_pubs_scopus
            }.values()
        )

        orcid_notes = ""
        orcid_extra: List[Dict] = []
        if normalized_orcid_for_output:
            meta = {
                "name": name,
                "department": department,
                "email": email,
                "telephone": telephone,
                "rank": rank,
                "research_field": research_field,
                "unic_entity": unic_entity,
                "orcid": normalized_orcid_for_output,
                "scopus_id": scopus_id,
                "identifier_source": identifier_source,
            }
            orcid_extra, orcid_notes = merge_orcid_only_rows(
                orcid_id=normalized_orcid_for_output,
                min_year=min_year,
                meta=meta,
                person_scopus_pubs=person_pubs_scopus,
                session=http_session,
            )

        if orcid_notes:
            notes = f"{notes}; {orcid_notes}".strip("; ").strip() if notes else orcid_notes

        person_pubs = person_pubs_scopus + orcid_extra
        publication_rows.extend(person_pubs)
        person_pubs.sort(key=lambda x: (x.get("year", 0), x.get("cover_date", "")), reverse=True)
        recent = person_pubs[:3]
        recent_display = " | ".join([
            f"{item.get('year', '')}: {item.get('title', '')}" for item in recent
        ])
        journal_count = sum(1 for item in person_pubs if item.get("is_journal", False))
        non_scopus_total = len(orcid_extra)
        non_scopus_journal = sum(1 for item in orcid_extra if item.get("is_journal", False))

        if journal_count <= 1:
            status = "HOD Consideration"
        elif journal_count >= 3:
            status = "fulfills requirements"
        else:
            status = "does not fulfill requirements"

        summary_rows.append(
            {
                "name": name,
                "department": department,
                "email": email,
                "telephone": telephone,
                "rank": rank,
                "research_field": research_field,
                "unic_entity": unic_entity,
                "orcid": normalized_orcid_for_output,
                "scopus_id": scopus_id,
                "identifier_source": identifier_source,
                "scopus_publications_last_6_years": len(person_pubs_scopus),
                "non_scopus_publications_last_6_years": non_scopus_total,
                "total_publications_last_6_years": len(person_pubs),
                "journal_publications_last_6_years": journal_count,
                "non_scopus_journal_publications_last_6_years": non_scopus_journal,
                "recent_3_articles": recent_display,
                "status": status,
                "notes": notes,
            }
        )

    publications_df = pd.DataFrame(publication_rows)
    summary_df = pd.DataFrame(summary_rows)
    return publications_df, summary_df


def run_pipeline(input_path: str, output_dir: str, api_key: str) -> None:
    if not api_key:
        raise ValueError("Missing SCOPUS_API_KEY. Set it in environment variables or .env.")

    now_year = dt.datetime.now().year
    # Last 6 years including current year, e.g. 2021-2026 when current year is 2026.
    min_year = now_year - 5

    input_df = pd.read_csv(input_path, dtype=str).fillna("")
    client = ScopusClient(api_key=api_key)
    with requests.Session() as http_session:
        publications_df, summary_df = build_rows(
            input_df=input_df, client=client, min_year=min_year, http_session=http_session
        )

    os.makedirs(output_dir, exist_ok=True)

    publications_path = os.path.join(output_dir, "publications_raw.csv")
    summary_path = os.path.join(output_dir, "summary.csv")

    publications_df.to_csv(publications_path, index=False, encoding="utf-8")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path)

    parser = argparse.ArgumentParser(description="Fetch Scopus publications and build summary tables.")
    parser.add_argument(
        "--input",
        default="Full timers ORCID.csv",
        help="Path to input CSV with Name and ORCID columns; optional Telephone, Rank, Scopus ID (full-time); "
        "part-time may omit rank/telephone/scopus if only ORCID is present.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for generated output CSV files.",
    )
    args = parser.parse_args()

    run_pipeline(
        input_path=args.input,
        output_dir=args.output_dir,
        api_key=os.getenv("SCOPUS_API_KEY", ""),
    )
