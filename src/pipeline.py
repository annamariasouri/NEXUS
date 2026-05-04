import argparse
import datetime as dt
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"


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


def build_rows(input_df: pd.DataFrame, client: ScopusClient, min_year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
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
                        "total_publications_last_6_years": 0,
                        "journal_publications_last_6_years": 0,
                        "recent_3_articles": "",
                        "status": "does not fulfill requirements",
                        "notes": f"Scopus API error (Scopus ID): {exc}",
                    }
                )
                continue

        normalized_orcid_for_output = orcid

        person_pubs: List[Dict] = []
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
            }
            person_pubs.append(pub_row)

        person_pubs = list({
            (item.get("eid") or f"{item.get('title')}|{item.get('year')}|{item.get('source_title')}"): item
            for item in person_pubs
        }.values())
        publication_rows.extend(person_pubs)
        person_pubs.sort(key=lambda x: (x.get("year", 0), x.get("cover_date", "")), reverse=True)
        recent = person_pubs[:3]
        recent_display = " | ".join([
            f"{item.get('year', '')}: {item.get('title', '')}" for item in recent
        ])
        journal_count = sum(1 for item in person_pubs if item.get("is_journal", False))

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
                "total_publications_last_6_years": len(person_pubs),
                "journal_publications_last_6_years": journal_count,
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
    publications_df, summary_df = build_rows(input_df=input_df, client=client, min_year=min_year)

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
