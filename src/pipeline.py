import argparse
import datetime as dt
import os
import re
from typing import Dict, List, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"


class ScopusClient:
    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search_by_orcid(self, orcid: str, min_year: int, count: int = 25) -> List[Dict]:
        entries: List[Dict] = []
        start = 0

        # Query journals only at source type level and enforce the year at API level.
        query = f"ORCID({orcid}) AND PUBYEAR > {min_year - 1} AND SRCTYPE(j)"

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


def normalize_orcid(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    match = re.search(r"(\d{4}-\d{4}-\d{4}-[\dXx]{4})", text)
    if not match:
        return ""
    return match.group(1).upper()


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


def build_rows(input_df: pd.DataFrame, client: ScopusClient, min_year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    publication_rows: List[Dict] = []
    summary_rows: List[Dict] = []

    for _, row in input_df.iterrows():
        name = str(row.get("Name", "")).strip()
        raw_orcid = str(row.get("ORCID", ""))
        orcid = normalize_orcid(raw_orcid)

        if not name:
            continue

        if not orcid:
            summary_rows.append(
                {
                    "name": name,
                    "orcid": raw_orcid,
                    "journal_publications_last_6_years": 0,
                    "recent_3_articles": "",
                    "status": "does not fulfill requirements",
                    "notes": "Invalid ORCID format",
                }
            )
            continue

        try:
            entries = client.search_by_orcid(orcid=orcid, min_year=min_year)
        except requests.HTTPError as exc:
            summary_rows.append(
                {
                    "name": name,
                    "orcid": orcid,
                    "journal_publications_last_6_years": 0,
                    "recent_3_articles": "",
                    "status": "does not fulfill requirements",
                    "notes": f"Scopus API error: {exc}",
                }
            )
            continue

        person_pubs: List[Dict] = []
        for entry in entries:
            year = parse_year(entry)
            if year < min_year:
                continue
            if not is_journal(entry):
                continue

            title = str(entry.get("dc:title", "")).strip()
            journal = str(entry.get("prism:publicationName", "")).strip()
            doi = str(entry.get("prism:doi", "")).strip()
            eid = str(entry.get("eid", "")).strip()
            cover_date = str(entry.get("prism:coverDate", "")).strip()

            pub_row = {
                "name": name,
                "orcid": orcid,
                "title": title,
                "journal": journal,
                "year": year,
                "cover_date": cover_date,
                "doi": doi,
                "eid": eid,
            }
            publication_rows.append(pub_row)
            person_pubs.append(pub_row)

        person_pubs.sort(key=lambda x: (x.get("year", 0), x.get("cover_date", "")), reverse=True)
        recent = person_pubs[:3]
        recent_display = " | ".join([
            f"{item.get('year', '')}: {item.get('title', '')}" for item in recent
        ])
        count = len(person_pubs)

        summary_rows.append(
            {
                "name": name,
                "orcid": orcid,
                "journal_publications_last_6_years": count,
                "recent_3_articles": recent_display,
                "status": "fulfills requirements" if count >= 3 else "does not fulfill requirements",
                "notes": "",
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

    input_df = pd.read_csv(input_path)
    client = ScopusClient(api_key=api_key)
    publications_df, summary_df = build_rows(input_df=input_df, client=client, min_year=min_year)

    os.makedirs(output_dir, exist_ok=True)

    publications_path = os.path.join(output_dir, "publications_raw.csv")
    summary_path = os.path.join(output_dir, "summary.csv")

    publications_df.to_csv(publications_path, index=False, encoding="utf-8")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser(description="Fetch Scopus publications and build summary tables.")
    parser.add_argument(
        "--input",
        default="Full timers ORCID.csv",
        help="Path to input CSV with Name and ORCID columns.",
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
