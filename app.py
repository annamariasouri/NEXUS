from html import escape
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import altair as alt
import pandas as pd
import streamlit as st
import re

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = BASE_DIR / "outputs" / "summary.csv"
PUBLICATIONS_PATH = BASE_DIR / "outputs" / "publications_raw.csv"
PART_SUMMARY_PATH = BASE_DIR / "outputs" / "part_timers" / "summary.csv"
PART_PUBLICATIONS_PATH = BASE_DIR / "outputs" / "part_timers" / "publications_raw.csv"
FULL_TIMER_ROSTER_PATH = BASE_DIR / "Full timers ORCID.csv"
PART_TIMER_ROSTER_PATH = BASE_DIR / "Part timers ORCID.csv"

st.set_page_config(page_title="NEXUS Dashboard", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        :root {
          --bg-1: #eef7ff;
          --bg-2: #fff6e8;
          --bg-3: #e9fff6;
          --ink: #112031;
          --muted: #4d6277;
          --accent: #0b8a78;
          --accent-2: #d66a2b;
          --card: rgba(255, 255, 255, 0.88);
          --border: #d4e2ef;
          --ok: #0b8a5d;
          --no: #ba3d1f;
        }

        .stApp {
          background:
            radial-gradient(1300px 700px at -15% -15%, rgba(11, 138, 120, 0.2), transparent 60%),
            radial-gradient(1000px 560px at 112% -10%, rgba(214, 106, 43, 0.18), transparent 55%),
            radial-gradient(900px 520px at 50% 120%, rgba(0, 123, 101, 0.1), transparent 50%),
            linear-gradient(145deg, var(--bg-1), var(--bg-2) 55%, var(--bg-3));
        }

        h1, h2, h3 {
          font-family: 'Space Grotesk', sans-serif;
          color: var(--ink);
          letter-spacing: -0.02em;
        }

        p, div, label, span, button {
          font-family: 'IBM Plex Sans', sans-serif;
        }

        .kpi-wrap {
          display: grid;
          grid-template-columns: repeat(4, minmax(170px, 1fr));
          gap: 8px;
          margin-bottom: 10px;
        }

        .kpi-card {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 10px 12px;
          backdrop-filter: blur(6px);
          box-shadow: 0 12px 30px rgba(20, 31, 51, 0.09);
          transition: transform 0.16s ease, box-shadow 0.16s ease;
        }

        .kpi-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 14px 34px rgba(14, 41, 73, 0.13);
        }

        .kpi-label { color: var(--muted); font-size: 0.86rem; }
        .kpi-value { color: var(--ink); font-size: 1.35rem; font-weight: 700; }

        .profile-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(190px, 1fr));
          gap: 8px;
          margin-top: 4px;
          margin-bottom: 10px;
        }

        .profile-card {
          background: rgba(255, 255, 255, 0.9);
          border: 1px solid var(--border);
          border-radius: 14px;
          padding: 12px 14px;
        }

        .profile-label { color: var(--muted); font-size: 0.84rem; margin-bottom: 4px; }
        .profile-value { color: var(--ink); font-weight: 600; word-break: break-word; }

        .table-shell {
          background: rgba(255, 255, 255, 0.9);
          border: 1px solid var(--border);
          border-radius: 18px;
          overflow: auto;
          box-shadow: 0 12px 30px rgba(15, 36, 64, 0.1);
          margin-top: 6px;
        }

        .nexus-table {
          width: 100%;
          border-collapse: collapse;
          min-width: 1040px;
        }

        .nexus-table thead th {
          position: sticky;
          top: 0;
          z-index: 1;
          text-align: left;
          background: linear-gradient(90deg, #12253a, #1f3d5a);
          color: #f8fbff;
          padding: 12px 14px;
          font-size: 0.9rem;
        }

        .nexus-table thead th.split-header {
          min-width: 126px;
        }

        .nexus-table thead th.split-header .main {
          display: block;
        }

        .nexus-table thead th.split-header .sub {
          display: block;
          white-space: nowrap;
          font-size: 0.95em;
        }

        .nexus-table tbody td {
          border-top: 1px solid #e5edf5;
          padding: 11px 14px;
          color: #1b2c3e;
          vertical-align: top;
          font-size: 0.92rem;
        }

        .nexus-table tbody tr:nth-child(even) { background: #f7fbff; }
        .nexus-table tbody tr:hover { background: #eef7ff; }

        .name-link {
          color: #0a5da8;
          text-decoration: none;
          font-weight: 700;
        }

        .name-link:hover { text-decoration: underline; }

        .data-freshness {
          background: rgba(255, 255, 255, 0.86);
          border: 1px solid var(--border);
          border-left: 4px solid var(--accent);
          border-radius: 12px;
          padding: 8px 10px;
          margin-bottom: 8px;
          color: var(--ink);
          box-shadow: 0 8px 22px rgba(24, 42, 70, 0.08);
        }

        .freshness-meta {
          color: var(--muted);
          font-size: 0.9rem;
        }

        .status-pill {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 999px;
          font-weight: 600;
          font-size: 0.8rem;
          border: 1px solid transparent;
          white-space: nowrap;
        }

        .status-ok {
          color: var(--ok);
          background: #e8f8f0;
          border-color: #b7e8d4;
        }

        .status-no {
          color: #a85a12;
          background: #fff4e8;
          border-color: #f2c89a;
        }

        .status-hod {
          color: #d32f2f;
          background: #ffebee;
          border-color: #ef5350;
        }

        .entity-pill {
          display: inline-block;
          padding: 3px 10px;
          border-radius: 10px;
          font-size: 0.82rem;
          font-weight: 600;
          white-space: nowrap;
          border: 1px solid #c5d6f0;
          background: #f2f6fb;
          color: #1b2c3e;
        }

        .entity-nicosia {
          background: #e8f4ff;
          border-color: #9ec5eb;
        }

        .entity-athens {
          background: #fff6ed;
          border-color: #e8b88a;
        }

        .articles-cell, .title-cell {
          line-height: 1.45;
          white-space: normal;
        }

        /* Keep full text visible inside Streamlit multiselect selected tags. */
        .stMultiSelect [data-baseweb="tag"] {
          max-width: none !important;
        }

        .stMultiSelect [data-baseweb="tag"] span {
          max-width: none !important;
          overflow: visible !important;
          text-overflow: clip !important;
          white-space: nowrap !important;
        }

        .nexus-dashboard-subtitle {
          font-size: 0.92rem;
          color: var(--muted);
          font-weight: 500;
          margin: -0.2rem 0 0.65rem 0;
          line-height: 1.35;
        }

        section[data-testid="stExpander"] {
          border: 1px solid var(--border);
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.55);
          margin-bottom: 10px;
          box-shadow: 0 4px 14px rgba(20, 31, 51, 0.06);
        }

        section[data-testid="stExpander"] details summary {
          font-size: 1.2rem !important;
          font-weight: 700 !important;
          color: var(--ink) !important;
          letter-spacing: 0.02em;
        }

        section[data-testid="stExpander"] details summary span {
          font-size: 1.2rem !important;
          font-weight: 700 !important;
        }

        /* —— Executive landing (light SaaS / glass) —— */
        .nexus-nav-shell {
          font-family: 'Inter', system-ui, sans-serif;
          margin: 0 0 1.5rem 0;
          padding: 0.5rem 0 0.75rem 0;
          background: rgba(255, 255, 255, 0.72);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid rgba(212, 226, 239, 0.85);
          border-radius: 14px;
        }
        .nexus-nav {
          max-width: 1120px;
          margin: 0 auto;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.25rem 1.25rem;
          font-size: 0.8125rem;
          font-weight: 500;
        }
        .nexus-nav a {
          color: #5c6d82;
          text-decoration: none;
          padding: 0.35rem 0.15rem;
          border-radius: 6px;
          transition: color 0.15s ease, background 0.15s ease;
        }
        .nexus-nav a:hover { color: #0b6b5e; background: rgba(11, 138, 120, 0.06); }
        .nexus-nav a.nexus-nav-active { color: #0b6b5e; font-weight: 600; }
        .nexus-nav-sep { color: #c5d2e2; user-select: none; }

        .nexus-hero-v2 {
          position: relative;
          font-family: 'Inter', system-ui, sans-serif;
          text-align: center;
          padding: 2.5rem 1.5rem 2.25rem;
          margin: 0 auto 2rem;
          max-width: 920px;
          border-radius: 24px;
          background: linear-gradient(165deg, #ffffff 0%, #f4f8fc 38%, #faf8f5 100%);
          box-shadow: 0 1px 0 rgba(255,255,255,0.9) inset, 0 24px 48px rgba(17, 32, 49, 0.06);
          overflow: hidden;
        }
        .nexus-hero-pattern {
          position: absolute;
          inset: 0;
          opacity: 0.45;
          background-image: radial-gradient(circle at 1px 1px, rgba(11, 90, 168, 0.07) 1px, transparent 0);
          background-size: 28px 28px;
          pointer-events: none;
        }
        .nexus-hero-v2::before {
          content: "";
          position: absolute;
          top: -40%;
          right: -20%;
          width: 55%;
          height: 120%;
          background: radial-gradient(ellipse, rgba(11, 138, 120, 0.08) 0%, transparent 70%);
          pointer-events: none;
        }
        .nexus-hero-inner { position: relative; z-index: 1; }
        .nexus-pill {
          display: inline-block;
          font-size: 0.6875rem;
          font-weight: 600;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: #3d5a6e;
          background: rgba(255, 255, 255, 0.85);
          border: 1px solid rgba(212, 226, 239, 0.95);
          padding: 0.4rem 0.9rem;
          border-radius: 999px;
          margin-bottom: 1rem;
          box-shadow: 0 2px 8px rgba(17, 32, 49, 0.04);
        }
        .nexus-hero-brand {
          font-family: 'Inter', system-ui, sans-serif;
          font-size: clamp(2.75rem, 6vw, 3.75rem);
          font-weight: 700;
          letter-spacing: -0.045em;
          color: #0f1f2e;
          margin: 0 0 0.75rem 0;
          line-height: 1.05;
        }
        .nexus-hero-sub {
          font-size: clamp(1rem, 2.1vw, 1.2rem);
          font-weight: 500;
          color: #3a4d62;
          max-width: 38rem;
          margin: 0 auto 0.6rem;
          line-height: 1.45;
        }
        .nexus-hero-micro {
          font-size: 0.875rem;
          font-weight: 400;
          color: #6b7c90;
          max-width: 28rem;
          margin: 0 auto;
          line-height: 1.5;
        }

        .nexus-module-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.25rem;
          max-width: 1120px;
          margin: 0 auto 2rem;
          font-family: 'Inter', system-ui, sans-serif;
        }
        @media (max-width: 900px) {
          .nexus-module-grid { grid-template-columns: 1fr; }
        }
        .nexus-module {
          position: relative;
          display: block;
          text-decoration: none !important;
          color: inherit !important;
          padding: 1.5rem 1.35rem 1.4rem;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.78);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(228, 236, 245, 0.95);
          box-shadow: 0 8px 28px rgba(17, 32, 49, 0.05);
          transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }
        .nexus-module:hover {
          transform: translateY(-4px);
          box-shadow: 0 16px 40px rgba(17, 32, 49, 0.09);
          border-color: rgba(11, 138, 120, 0.22);
        }
        .nexus-module--active {
          border-color: rgba(11, 138, 120, 0.45);
          box-shadow: 0 0 0 1px rgba(11, 138, 120, 0.12), 0 12px 36px rgba(11, 138, 120, 0.1);
          background: linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(240, 250, 247, 0.9) 100%);
        }
        .nexus-module-icon {
          display: flex;
          align-items: center;
          justify-content: flex-start;
          margin-bottom: 0.65rem;
          color: #0b8a78;
        }
        .nexus-module-icon svg {
          width: 28px;
          height: 28px;
          opacity: 0.9;
        }
        .nexus-module-title {
          display: block;
          font-size: 1.0625rem;
          font-weight: 600;
          color: #0f1f2e;
          margin-bottom: 0.35rem;
          letter-spacing: -0.02em;
        }
        .nexus-module-desc {
          display: block;
          font-size: 0.8125rem;
          color: #6b7c90;
          line-height: 1.45;
        }

        .nexus-kpi-strip {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 1rem;
          max-width: 1120px;
          margin: 0 auto 2rem;
          font-family: 'Inter', system-ui, sans-serif;
        }
        @media (max-width: 900px) {
          .nexus-kpi-strip { grid-template-columns: repeat(2, 1fr); }
        }
        .nexus-kpi-card {
          padding: 1rem 1rem 1.05rem;
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.65);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(236, 242, 249, 0.9);
          box-shadow: 0 4px 16px rgba(17, 32, 49, 0.035);
        }
        .nexus-kpi-label {
          font-size: 0.6875rem;
          font-weight: 600;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: #7a8b9e;
          margin-bottom: 0.35rem;
        }
        .nexus-kpi-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #0f1f2e;
          letter-spacing: -0.02em;
          line-height: 1.2;
        }
        .nexus-kpi-sub {
          font-size: 0.6875rem;
          color: #9aa8b8;
          margin-top: 0.25rem;
        }

        @media (max-width: 900px) {
          .kpi-wrap { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
          .profile-grid { grid-template-columns: 1fr; }
          .nexus-table { min-width: 820px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_query_value(value: object) -> str:
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    if value is None:
        return ""
    return str(value).strip()


def get_selected_orcid() -> str:
    raw = normalize_query_value(st.query_params.get("orcid", ""))
    return _normalize_orcid_from_cell(raw) or raw.strip()


def cohort_from_query_params() -> str:
    raw = normalize_query_value(st.query_params.get("cohort", "")).lower()
    if raw in ("part", "part-time", "parttime"):
        return "part"
    return "full"


def format_recent_items(value: str) -> str:
    parts = [escape(piece.strip()) for piece in str(value).split("|") if piece.strip()]
    if not parts:
        return "-"
    return "<br>".join(parts)


def normalize_research_field(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\*+$", "", text).strip()
    return text


def _normalize_orcid_from_cell(raw: object) -> str:
    text = str(raw or "").strip().replace("\u00a0", " ")
    match = re.search(r"(\d{4}-\d{4}-\d{4}-[\dXx]{4})", text)
    return match.group(1).upper() if match else ""


def _roster_column(roster: pd.DataFrame, target: str) -> str | None:
    target_stripped = target.strip()
    for col in roster.columns:
        if str(col).strip() == target_stripped:
            return col
    return None


def merge_roster(summary_df: pd.DataFrame, roster_path: Path) -> pd.DataFrame:
    """Fill unic_entity from roster CSV and append people on the roster but missing from summary."""
    if not roster_path.exists():
        return summary_df

    roster = pd.read_csv(roster_path, dtype=str).fillna("")
    c_name = _roster_column(roster, "Name")
    c_entity = _roster_column(roster, "UNIC Entity")
    if not c_name or not c_entity:
        return summary_df

    c_dept = _roster_column(roster, "Department")
    if c_dept is None:
        c_dept = next((c for c in roster.columns if "Department" in str(c)), None)
    c_email = _roster_column(roster, "Email")
    c_tel = _roster_column(roster, "Telephone")
    c_rank = _roster_column(roster, "Rank")
    if c_rank is None:
        c_rank = next((c for c in roster.columns if str(c).strip().startswith("Rank")), None)
    c_rf = _roster_column(roster, "Research Field")
    c_orcid = _roster_column(roster, "ORCID")
    c_scopus = _roster_column(roster, "Scopus ID")

    def norm_name(value: object) -> str:
        return str(value).strip().lower()

    entity_by_name: dict[str, str] = {}
    roster_row_by_name: dict[str, pd.Series] = {}
    for _, row in roster.iterrows():
        nm = str(row.get(c_name, "")).strip()
        if not nm:
            continue
        key = norm_name(nm)
        entity_by_name[key] = str(row.get(c_entity, "")).strip()
        roster_row_by_name[key] = row

    name_keys = summary_df["name"].map(norm_name)
    filled: list[str] = []
    for key, existing in zip(name_keys, summary_df["unic_entity"].tolist()):
        from_roster = entity_by_name.get(key, "").strip()
        ex = str(existing).strip() if existing is not None and str(existing) != "nan" else ""
        filled.append(from_roster if from_roster else ex)
    summary_df = summary_df.copy()
    summary_df["unic_entity"] = filled

    present = set(name_keys.tolist())
    stub_list: list[dict] = []
    for key, rseries in roster_row_by_name.items():
        if key in present:
            continue
        nm = str(rseries.get(c_name, "")).strip()
        raw_orch = str(rseries.get(c_orcid, "")) if c_orcid else ""
        orcid_out = _normalize_orcid_from_cell(raw_orch) or raw_orch.strip()
        stub: dict = {
            "name": nm,
            "department": str(rseries.get(c_dept, "")).strip() if c_dept else "",
            "email": str(rseries.get(c_email, "")).strip() if c_email else "",
            "telephone": str(rseries.get(c_tel, "")).strip() if c_tel else "",
            "rank": str(rseries.get(c_rank, "")).strip() if c_rank else "",
            "research_field": normalize_research_field(str(rseries.get(c_rf, "")) if c_rf else ""),
            "unic_entity": entity_by_name.get(key, ""),
            "orcid": orcid_out,
            "scopus_id": str(rseries.get(c_scopus, "")).strip() if c_scopus else "",
            "identifier_source": "",
            "total_publications_last_6_years": 0,
            "journal_publications_last_6_years": 0,
            "recent_3_articles": "",
            "status": "does not fulfill requirements",
            "notes": "Roster only until the Scopus pipeline is run for this person.",
        }
        stub_list.append(stub)

    if not stub_list:
        return summary_df

    stub_df = pd.DataFrame(stub_list)
    for col in summary_df.columns:
        if col not in stub_df.columns:
            if col in ("journal_publications_last_6_years", "total_publications_last_6_years"):
                stub_df[col] = 0
            else:
                stub_df[col] = ""
    stub_df = stub_df[summary_df.columns.tolist()]
    return pd.concat([summary_df, stub_df], ignore_index=True)


def load_data(cohort: str) -> tuple[pd.DataFrame, pd.DataFrame, Path, Path]:
    if cohort == "part":
        summary_path = PART_SUMMARY_PATH
        pubs_path = PART_PUBLICATIONS_PATH
        roster_path = PART_TIMER_ROSTER_PATH
        run_hint = (
            'python src/pipeline.py --input "Part timers ORCID.csv" --output-dir outputs/part_timers'
        )
    else:
        summary_path = SUMMARY_PATH
        pubs_path = PUBLICATIONS_PATH
        roster_path = FULL_TIMER_ROSTER_PATH
        run_hint = 'python src/pipeline.py --input "Full timers ORCID.csv" --output-dir outputs'

    if not summary_path.exists():
        st.info(f"No summary found yet. Run the pipeline first, for example:\n\n`{run_hint}`")
        st.stop()
    if not pubs_path.exists():
        st.info(f"No publications file found yet. Run the pipeline first, for example:\n\n`{run_hint}`")
        st.stop()

    summary_df = pd.read_csv(summary_path)
    publications_df = pd.read_csv(pubs_path)

    if summary_df.empty:
        st.warning("Summary file is empty.")
        st.stop()

    summary_df["name"] = summary_df["name"].fillna("").astype(str)
    summary_df["orcid"] = summary_df["orcid"].fillna("").astype(str)
    summary_df["recent_3_articles"] = summary_df["recent_3_articles"].fillna("").astype(str)
    summary_df["journal_publications_last_6_years"] = pd.to_numeric(
        summary_df.get("journal_publications_last_6_years", 0), errors="coerce"
    ).fillna(0).astype(int)
    summary_df["total_publications_last_6_years"] = pd.to_numeric(
        summary_df.get("total_publications_last_6_years", 0), errors="coerce"
    ).fillna(0).astype(int)

    for col in ["department", "email", "telephone", "rank", "research_field"]:
        summary_df[col] = summary_df.get(col, "").fillna("").astype(str)
    summary_df["research_field"] = summary_df["research_field"].map(normalize_research_field)

    if "unic_entity" not in summary_df.columns:
        summary_df["unic_entity"] = ""
    summary_df["unic_entity"] = summary_df["unic_entity"].fillna("").astype(str)

    summary_df = merge_roster(summary_df, roster_path)

    # Blank research fields are excluded by the field checkboxes unless we label them.
    blank_rf = summary_df["research_field"].fillna("").astype(str).str.strip() == ""
    summary_df.loc[blank_rf, "research_field"] = "Uncategorized"

    summary_df["unic_entity"] = summary_df["unic_entity"].fillna("").astype(str).str.strip()
    summary_df["status"] = summary_df["status"].fillna("does not fulfill requirements").astype(str)
    summary_df["status"] = summary_df["status"].replace(
        {
            "fulfills requirements": "Faculty sufficiency",
            "does not fulfill requirements": "Research committee review",
        }
    )
    ce = summary_df["unic_entity"]
    summary_df["_campus_filter"] = ce.where(ce.str.len() > 0, "Not specified")

    publications_df["orcid"] = publications_df.get("orcid", "").fillna("").astype(str)
    publications_df["research_field"] = publications_df.get("research_field", "").fillna("").astype(str)
    publications_df["research_field"] = publications_df["research_field"].map(normalize_research_field)
    publications_df["title"] = publications_df.get("title", "").fillna("").astype(str)
    publications_df["publication_type"] = publications_df.get("publication_type", "Unknown").fillna("Unknown").astype(str)
    publications_df["source_title"] = publications_df.get("source_title", "").fillna("").astype(str)
    publications_df["doi"] = publications_df.get("doi", "").fillna("").astype(str)
    publications_df["cover_date"] = publications_df.get("cover_date", "").fillna("").astype(str)
    publications_df["year"] = pd.to_numeric(publications_df.get("year", 0), errors="coerce").fillna(0).astype(int)

    return summary_df, publications_df, summary_path, pubs_path


def format_updated_time(path: Path) -> str:
    timestamp = datetime.fromtimestamp(path.stat().st_mtime)
    return timestamp.strftime("%d %b %Y, %H:%M")


def render_freshness_banner(summary_path: Path, pubs_path: Path) -> None:
    summary_updated = format_updated_time(summary_path)
    pubs_updated = format_updated_time(pubs_path)
    st.markdown(
        f"""
        <div class="data-freshness">
          <div><strong>Data freshness:</strong> outputs are loaded from the latest generated CSV files.</div>
          <div class="freshness-meta">Summary updated: {summary_updated} | Publications updated: {pubs_updated} | Weekly automation: Monday 05:00 UTC</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _orcid_row_key(value: object) -> str:
    norm = _normalize_orcid_from_cell(value)
    return (norm or str(value).strip()).lower()


def clear_profile_query_params() -> None:
    """Remove only `orcid` from the URL so `cohort` (and other params) stay for part-time vs full-time."""
    if "orcid" not in st.query_params:
        return
    try:
        del st.query_params["orcid"]
    except (KeyError, TypeError, AttributeError):
        remaining = {k: v for k, v in st.query_params.items() if k != "orcid"}
        st.query_params.clear()
        for key, val in remaining.items():
            st.query_params[key] = val


def get_app_page() -> str:
    raw = normalize_query_value(st.query_params.get("page", "")).lower()
    if raw in ("research", "teaching", "analytics"):
        return raw
    return "landing"


def go_home() -> None:
    st.query_params.clear()
    st.rerun()


def back_to_research_table() -> None:
    """Leave profile view and return to the publications table (research workspace)."""
    clear_profile_query_params()
    st.query_params["page"] = "research"
    st.rerun()


def load_landing_kpi_stats() -> dict[str, object]:
    """Aggregate light KPIs from publication summaries and optional teaching roster."""
    out: dict[str, object] = {
        "total_faculty": None,
        "total_pubs": None,
        "teaching_hours": None,
        "active_researchers": None,
        "teaching_sections": None,
    }
    name_keys: set[str] = set()
    active_keys: set[str] = set()
    total_pubs_sum = 0

    for path in (SUMMARY_PATH, PART_SUMMARY_PATH):
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str)
        if df.empty or "name" not in df.columns:
            continue
        df = df.copy()
        df["_tp"] = pd.to_numeric(df.get("total_publications_last_6_years", 0), errors="coerce").fillna(0)
        for _, row in df.iterrows():
            nm = str(row.get("name", "")).strip().lower()
            if nm and nm != "nan":
                name_keys.add(nm)
            try:
                t = int(row["_tp"])
            except (ValueError, TypeError):
                t = 0
            total_pubs_sum += t
            if t > 0 and nm and nm != "nan":
                active_keys.add(nm)

    courses_path = BASE_DIR.parent / "Courses_cleaned.csv"
    sections = None
    if courses_path.exists():
        try:
            cdf = pd.read_csv(courses_path, dtype=str, encoding="utf-8-sig", skiprows=1)
            sections = len(cdf)
        except (OSError, UnicodeDecodeError, ValueError):
            try:
                cdf = pd.read_csv(courses_path, dtype=str, encoding="cp1252", skiprows=1)
                sections = len(cdf)
            except (OSError, UnicodeDecodeError, ValueError):
                sections = None
    out["total_faculty"] = len(name_keys) if name_keys else None
    out["total_pubs"] = total_pubs_sum
    out["active_researchers"] = len(active_keys) if active_keys else None
    out["teaching_sections"] = sections
    return out


def _fmt_kpi_num(val: object) -> str:
    if val is None:
        return "—"
    try:
        n = int(val)
    except (ValueError, TypeError):
        return "—"
    return f"{n:,}"


def render_landing() -> None:
    kpi = load_landing_kpi_stats()
    fac = _fmt_kpi_num(kpi.get("total_faculty"))
    pubs = _fmt_kpi_num(kpi.get("total_pubs"))
    act = _fmt_kpi_num(kpi.get("active_researchers"))
    sections = kpi.get("teaching_sections")
    teach_hours = "—"
    teach_sub = "Hours sync pending"
    if sections is not None:
        teach_sub = f"{int(sections):,} roster sections · hours pending"

    st.markdown(
        """
        <nav class="nexus-nav-shell" aria-label="Primary">
          <div class="nexus-nav">
            <a class="nexus-nav-active" href="?">Dashboard</a>
            <span class="nexus-nav-sep">·</span>
            <a href="?page=research">Faculty profiles</a>
            <span class="nexus-nav-sep">·</span>
            <a href="?page=research">Publications</a>
            <span class="nexus-nav-sep">·</span>
            <a href="?page=teaching">Teaching load</a>
            <span class="nexus-nav-sep">·</span>
            <a href="?page=analytics">Analytics settings</a>
          </div>
        </nav>
        <div class="nexus-hero-v2">
          <div class="nexus-hero-pattern"></div>
          <div class="nexus-hero-inner">
            <span class="nexus-pill">UNIC Business School Intelligence System</span>
            <h1 class="nexus-hero-brand">NEXUS</h1>
            <p class="nexus-hero-sub">An Academic Intelligence System for Faculty Activity and Research Output</p>
            <p class="nexus-hero-micro">Transforming academic activity into institutional insight.</p>
          </div>
        </div>
        <div class="nexus-module-grid">
          <a class="nexus-module nexus-module--active" href="?page=research">
            <span class="nexus-module-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/><circle cx="17" cy="7" r="1.2" fill="currentColor" stroke="none"/></svg></span>
            <span class="nexus-module-title">Research Output</span>
            <span class="nexus-module-desc">Publications, Scopus activity, and faculty sufficiency views.</span>
          </a>
          <a class="nexus-module" href="?page=teaching">
            <span class="nexus-module-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6.5v12l8-2.5 8 2.5V6.5"/><path d="M12 4v12"/><path d="M4 6.5L12 4l8 2.5"/></svg></span>
            <span class="nexus-module-title">Teaching Analytics</span>
            <span class="nexus-module-desc">Courses, workload, and teaching assignments (in development).</span>
          </a>
          <a class="nexus-module" href="?page=analytics">
            <span class="nexus-module-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="8" r="2.2"/><circle cx="17" cy="6" r="2.2"/><circle cx="14" cy="17" r="2.2"/><path d="M8.5 9.5 12 15M15.5 8 12 15M9 8l8-1"/></svg></span>
            <span class="nexus-module-title">Institutional Analytics</span>
            <span class="nexus-module-desc">Aggregated faculty insight and leadership dashboards (in development).</span>
          </a>
        </div>
        <div class="nexus-kpi-strip">
          <div class="nexus-kpi-card">
            <div class="nexus-kpi-label">Total faculty</div>
            <div class="nexus-kpi-value">"""
        + escape(fac)
        + """</div>
            <div class="nexus-kpi-sub">Unique roster · full &amp; part-time summaries</div>
          </div>
          <div class="nexus-kpi-card">
            <div class="nexus-kpi-label">Total publications</div>
            <div class="nexus-kpi-value">"""
        + escape(pubs)
        + """</div>
            <div class="nexus-kpi-sub">Sum · last 6 years (Scopus pipeline)</div>
          </div>
          <div class="nexus-kpi-card">
            <div class="nexus-kpi-label">Teaching load hours</div>
            <div class="nexus-kpi-value">"""
        + escape(teach_hours)
        + """</div>
            <div class="nexus-kpi-sub">"""
        + escape(teach_sub)
        + """</div>
          </div>
          <div class="nexus-kpi-card">
            <div class="nexus-kpi-label">Active researchers</div>
            <div class="nexus-kpi-value">"""
        + escape(act)
        + """</div>
            <div class="nexus-kpi-sub">With ≥1 publication in window</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_teaching_placeholder() -> None:
    h1, _ = st.columns([0.14, 0.86])
    with h1:
        if st.button("Home", key="nav_home_teaching"):
            go_home()
    st.title("Teaching Analytics")
    st.info("This workspace is coming soon. Courses, workload, and teaching insights will appear here.")


def render_analytics_placeholder() -> None:
    h1, _ = st.columns([0.14, 0.86])
    with h1:
        if st.button("Home", key="nav_home_analytics"):
            go_home()
    st.title("Institutional Analytics")
    st.info("This workspace is coming soon. School-wide summaries and leadership dashboards will live here.")


def render_master_table() -> None:
    nav_home, nav_title = st.columns([0.12, 0.88])
    with nav_home:
        if st.button("Home", key="nav_home_research"):
            go_home()
    with nav_title:
        st.title("Research output")
    st.markdown(
        '<p class="nexus-dashboard-subtitle">Data refreshed every Monday</p>',
        unsafe_allow_html=True,
    )

    preferred_status_order = ["Faculty sufficiency", "HOD Consideration", "Research committee review"]
    if "dashboard_faculty_cohort" not in st.session_state:
        st.session_state.dashboard_faculty_cohort = (
            "Part-time" if cohort_from_query_params() == "part" else "Full-time"
        )

    with st.expander("Filters", expanded=False):
        faculty_choice = st.radio(
            "Faculty",
            ["Full-time", "Part-time"],
            horizontal=True,
            key="dashboard_faculty_cohort",
        )
        cohort_key = "part" if faculty_choice == "Part-time" else "full"

        summary_df, _, _, _ = load_data(cohort_key)

        present_statuses = [s for s in preferred_status_order if s in set(summary_df["status"].dropna().tolist())]
        other_statuses = sorted([s for s in summary_df["status"].dropna().unique().tolist() if s not in present_statuses])
        statuses = present_statuses + other_statuses
        research_fields = sorted([f for f in summary_df["research_field"].dropna().unique().tolist() if f.strip()])
        campus_preferred = ["UNIC Nicosia", "UNIC Athens", "Not specified"]
        campus_present = summary_df["_campus_filter"].dropna().unique().tolist()
        campus_options = [c for c in campus_preferred if c in campus_present] + sorted(
            c for c in campus_present if c not in campus_preferred
        )

        c_campus, c_status = st.columns([1.15, 1.15])
        with c_campus:
            campus_filter = st.multiselect("UNIC Entity (campus)", options=campus_options, default=campus_options)
        with c_status:
            status_filter = st.multiselect("Status", options=statuses, default=statuses)

        st.markdown("**Research Field**")
        field_selection: dict[str, bool] = {}

        grouped_fields: list[tuple[str, list[str]]] = [
            ("Accounting / Economics / Finance", ["Accounting", "Economics", "Finance"]),
            ("Digital Innovation", ["Blockchain"]),
            ("Management", ["Management", "Marketing", "Information Systems"]),
        ]

        # Any unexpected field still appears as selectable in an extra group.
        known_fields = {item for _, group_items in grouped_fields for item in group_items}
        extra_fields = sorted([field for field in research_fields if field not in known_fields])
        if extra_fields:
            grouped_fields.append(("Other", extra_fields))

        group_cols = st.columns(len(grouped_fields))
        for idx, (group_name, group_items) in enumerate(grouped_fields):
            available_items = [item for item in group_items if item in research_fields]
            if not available_items:
                continue

            key_suffix = re.sub(r"\W+", "_", group_name.lower()).strip("_")
            with group_cols[idx]:
                st.markdown(f"**{group_name}**")
                if len(available_items) > 1:
                    select_all = st.checkbox("Select all", value=True, key=f"field_group_all_{key_suffix}")
                else:
                    select_all = True
                for field in available_items:
                    field_key = re.sub(r"\W+", "_", field.lower()).strip("_")
                    field_selection[field] = st.checkbox(
                        field,
                        value=select_all,
                        key=f"field_{field_key}",
                    )

        field_filter = [field for field, is_selected in field_selection.items() if is_selected]

        name_query = st.text_input("Search name", placeholder="Type a faculty name...")

    filtered = summary_df.copy()
    if name_query:
        filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
    if campus_filter:
        filtered = filtered[filtered["_campus_filter"].isin(campus_filter)]
    filtered = filtered[filtered["status"].isin(status_filter)]
    filtered = filtered[filtered["research_field"].isin(field_filter)]
    # Exclude this person from the dashboard table regardless of source spelling variations.
    filtered = filtered[~filtered["name"].str.contains(r"\bria\s+(morphidou|morphitou)\b", case=False, na=False, regex=True)]
    filtered = filtered.sort_values(
      by=["name"],
      ascending=[True],
    )

    st.markdown(
        f"""
        <div class="kpi-wrap">
          <div class="kpi-card"><div class="kpi-label">People Visible</div><div class="kpi-value">{len(filtered)}</div></div>
          <div class="kpi-card"><div class="kpi-label">Faculty Sufficiency</div><div class="kpi-value">{int((filtered['status'] == 'Faculty sufficiency').sum())}</div></div>
          <div class="kpi-card"><div class="kpi-label">Total Publications Visible</div><div class="kpi-value">{int(filtered['total_publications_last_6_years'].sum())}</div></div>
          <div class="kpi-card"><div class="kpi-label">Journal Publications Visible</div><div class="kpi-value">{int(filtered['journal_publications_last_6_years'].sum())}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    export_summary = filtered.drop(columns=["_campus_filter"], errors="ignore")
    st.download_button(
        label="Download filtered summary CSV",
        data=export_summary.to_csv(index=False).encode("utf-8"),
        file_name="summary_filtered.csv",
        mime="text/csv",
    )

    rows_html = []
    for _, row in filtered.iterrows():
        status_value = row["status"]
        if status_value == "Faculty sufficiency":
            status_class = "status-ok"
        elif status_value == "HOD Consideration":
            status_class = "status-hod"
        else:
            status_class = "status-no"
        orcid_cell = str(row["orcid"]).strip()
        orcid_for_url = _normalize_orcid_from_cell(orcid_cell) or orcid_cell
        encoded_orcid = quote_plus(orcid_for_url)
        ue = str(row.get("unic_entity", "")).strip()
        if ue == "UNIC Athens":
            entity_class = "entity-pill entity-athens"
        elif ue == "UNIC Nicosia":
            entity_class = "entity-pill entity-nicosia"
        else:
            entity_class = "entity-pill"
        entity_text = escape(ue) if ue else "—"
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td><a class='name-link' href='?page=research&cohort={cohort_key}&orcid={encoded_orcid}'>{escape(str(row['name']))}</a></td>",
                    f"<td><span class='{entity_class}'>{entity_text}</span></td>",
                    f"<td>{escape(str(row['research_field'])) or '-'}</td>",
                    f"<td class='articles-cell'>{format_recent_items(row['recent_3_articles'])}</td>",
                    f"<td>{int(row['total_publications_last_6_years'])}</td>",
                    f"<td>{int(row['journal_publications_last_6_years'])}</td>",
                    f"<td><span class='status-pill {status_class}'>{escape(status_value)}</span></td>",
                    "</tr>",
                ]
            )
        )

    table_html = f"""
    <div class="table-shell">
      <table class="nexus-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>UNIC Entity</th>
            <th>Research Field</th>
            <th>Recent 3 Publications</th>
            <th class='split-header'><span class='main'>Total</span><span class='sub'>(6 Years)</span></th>
            <th class='split-header'><span class='main'>PRJ</span><span class='sub'>(6 Years)</span></th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html) if rows_html else '<tr><td colspan="7">No matching records.</td></tr>'}
        </tbody>
      </table>
    </div>
    """

    st.markdown(table_html, unsafe_allow_html=True)


def render_profile_page(
    summary_df: pd.DataFrame,
    publications_df: pd.DataFrame,
    orcid: str,
    cohort: str,
    summary_path: Path,
    pubs_path: Path,
) -> None:
    orcid_key = _orcid_row_key(orcid)
    person_df = summary_df[summary_df["orcid"].map(_orcid_row_key) == orcid_key]
    if person_df.empty:
        st.warning(
            "Selected profile was not found. If you opened an old link, try "
            "**?page=research&cohort=part&orcid=…** for part-time faculty. "
            "Otherwise return to Research output and click the name again."
        )
        ph1, ph2 = st.columns(2)
        with ph1:
            if st.button("Home", key="nav_home_profile_missing"):
                go_home()
        with ph2:
            if st.button("Back to Research output", key="nav_back_profile_missing"):
                back_to_research_table()
        return

    person = person_df.iloc[0]

    pb1, pb2 = st.columns(2)
    with pb1:
        if st.button("Home", key="nav_home_profile"):
            go_home()
    with pb2:
        if st.button("Back to Research output", key="nav_back_profile"):
            back_to_research_table()

    cohort_title = "Part-time faculty" if cohort == "part" else "Full-time faculty"
    st.title(f"{person['name']} - Profile")
    st.caption(f"{cohort_title} — all Scopus publications in the last 6 years")
    render_freshness_banner(summary_path, pubs_path)

    st.markdown(
        f"""
        <div class="profile-grid">
          <div class="profile-card"><div class="profile-label">Name</div><div class="profile-value">{escape(str(person['name']))}</div></div>
          <div class="profile-card"><div class="profile-label">Department</div><div class="profile-value">{escape(str(person['department'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">UNIC Entity</div><div class="profile-value">{escape(str(person.get('unic_entity', '')).strip()) or '—'}</div></div>
          <div class="profile-card"><div class="profile-label">Research Field</div><div class="profile-value">{escape(str(person['research_field'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Rank</div><div class="profile-value">{escape(str(person['rank'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Email</div><div class="profile-value">{escape(str(person['email'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Mobile / Telephone</div><div class="profile-value">{escape(str(person['telephone'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">ORCID</div><div class="profile-value">{escape(str(person['orcid']))}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    person_pubs = publications_df[publications_df["orcid"].map(_orcid_row_key) == orcid_key].copy()
    person_pubs = person_pubs.sort_values(by=["year", "cover_date"], ascending=[False, False])

    p1, p2 = st.columns([1.25, 1.25])
    with p1:
        title_query = st.text_input("Search publication title", placeholder="Type keywords...")
    with p2:
        type_options = sorted(person_pubs["publication_type"].dropna().unique().tolist())
        type_filter = st.multiselect("Publication type", options=type_options, default=type_options)

    if title_query:
        person_pubs = person_pubs[person_pubs["title"].str.contains(title_query, case=False, na=False)]
    if type_filter:
        person_pubs = person_pubs[person_pubs["publication_type"].isin(type_filter)]

    if not person_pubs.empty:
      st.subheader("Publication Mix by Category")
      chart_df = (
        person_pubs["publication_type"]
        .value_counts()
        .rename_axis("publication_type")
        .reset_index(name="count")
      )
      total_count = int(chart_df["count"].sum())
      chart_df["pct"] = chart_df["count"] / total_count

      donut_chart = (
        alt.Chart(chart_df)
        .mark_arc(innerRadius=70, cornerRadius=6)
        .encode(
          theta=alt.Theta(field="count", type="quantitative"),
          color=alt.Color(
            field="publication_type",
            type="nominal",
            legend=alt.Legend(title="Category", orient="right"),
            scale=alt.Scale(
              range=[
                "#0f7b6c",
                "#da5b2d",
                "#1e4f9b",
                "#be8f00",
                "#7a3fa0",
                "#2d8fb3",
              ]
            ),
          ),
          tooltip=[
            alt.Tooltip("publication_type:N", title="Category"),
            alt.Tooltip("count:Q", title="Count"),
            alt.Tooltip("pct:Q", title="Percentage", format=".1%"),
          ],
        )
        .properties(height=320)
      )
      st.altair_chart(donut_chart, use_container_width=True)

    st.download_button(
        label="Download this profile publications CSV",
        data=person_pubs.to_csv(index=False).encode("utf-8"),
        file_name=f"publications_{orcid}.csv",
        mime="text/csv",
    )

    rows_html = []
    for _, pub in person_pubs.iterrows():
        doi_value = str(pub["doi"]).strip()
        doi_html = (
            f"<a class='name-link' href='https://doi.org/{escape(doi_value)}' target='_blank'>{escape(doi_value)}</a>"
            if doi_value
            else "-"
        )
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td class='title-cell'>{escape(str(pub['title'])) or '-'}</td>",
                    f"<td>{escape(str(pub['publication_type']))}</td>",
                    f"<td>{escape(str(pub['source_title'])) or '-'}</td>",
                    f"<td>{int(pub['year']) if int(pub['year']) > 0 else '-'}</td>",
                    f"<td>{doi_html}</td>",
                    "</tr>",
                ]
            )
        )

    table_html = f"""
    <div class="table-shell">
      <table class="nexus-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Journal / Conference / Book Source</th>
            <th>Year</th>
            <th>DOI</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html) if rows_html else '<tr><td colspan="5">No matching publications found.</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


inject_styles()

selected_orcid = get_selected_orcid()
app_page = get_app_page()

if selected_orcid:
    cohort_key = cohort_from_query_params()
    summary_data, publications_data, active_summary_path, active_pubs_path = load_data(cohort_key)
    render_profile_page(
        summary_data,
        publications_data,
        selected_orcid,
        cohort_key,
        active_summary_path,
        active_pubs_path,
    )
elif app_page == "research":
    render_master_table()
elif app_page == "teaching":
    render_teaching_placeholder()
elif app_page == "analytics":
    render_analytics_placeholder()
else:
    render_landing()
