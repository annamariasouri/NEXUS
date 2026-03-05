from html import escape
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = BASE_DIR / "outputs" / "summary.csv"
PUBLICATIONS_PATH = BASE_DIR / "outputs" / "publications_raw.csv"

st.set_page_config(page_title="NEXUS Research Dashboard", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        :root {
          --bg-1: #f4fbff;
          --bg-2: #fef6ec;
          --ink: #13212e;
          --muted: #506276;
          --accent: #0f7b6c;
          --accent-2: #da5b2d;
          --card: rgba(255, 255, 255, 0.84);
          --border: #d7e2ee;
          --ok: #0d8f62;
          --no: #b53b1f;
        }

        .stApp {
          background:
            radial-gradient(1200px 600px at -10% -10%, rgba(15, 123, 108, 0.18), transparent 60%),
            radial-gradient(900px 500px at 110% -10%, rgba(218, 91, 45, 0.16), transparent 55%),
            linear-gradient(140deg, var(--bg-1), var(--bg-2));
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
          gap: 12px;
          margin-bottom: 14px;
        }

        .kpi-card {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 14px 16px;
          backdrop-filter: blur(6px);
          box-shadow: 0 8px 25px rgba(20, 31, 51, 0.08);
        }

        .kpi-label { color: var(--muted); font-size: 0.86rem; }
        .kpi-value { color: var(--ink); font-size: 1.35rem; font-weight: 700; }

        .profile-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(190px, 1fr));
          gap: 12px;
          margin-top: 6px;
          margin-bottom: 14px;
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
          box-shadow: 0 10px 28px rgba(15, 36, 64, 0.08);
          margin-top: 10px;
        }

        .nexus-table {
          width: 100%;
          border-collapse: collapse;
          min-width: 960px;
        }

        .nexus-table thead th {
          position: sticky;
          top: 0;
          z-index: 1;
          text-align: left;
          background: #12253a;
          color: #f8fbff;
          padding: 12px 14px;
          font-size: 0.9rem;
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
          color: var(--no);
          background: #fff0ec;
          border-color: #f8c9bb;
        }

        .articles-cell, .title-cell {
          line-height: 1.45;
          white-space: normal;
        }

        @media (max-width: 900px) {
          .kpi-wrap { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
          .profile-grid { grid-template-columns: 1fr; }
          .nexus-table { min-width: 720px; }
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
    return normalize_query_value(st.query_params.get("orcid", ""))


def format_recent_items(value: str) -> str:
    parts = [escape(piece.strip()) for piece in str(value).split("|") if piece.strip()]
    if not parts:
        return "-"
    return "<br>".join(parts)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not SUMMARY_PATH.exists():
        st.info("No summary found yet. Run pipeline first to generate outputs/summary.csv.")
        st.stop()
    if not PUBLICATIONS_PATH.exists():
        st.info("No publications file found yet. Run pipeline first to generate outputs/publications_raw.csv.")
        st.stop()

    summary_df = pd.read_csv(SUMMARY_PATH)
    publications_df = pd.read_csv(PUBLICATIONS_PATH)

    if summary_df.empty:
        st.warning("Summary file is empty.")
        st.stop()

    summary_df["name"] = summary_df["name"].fillna("").astype(str)
    summary_df["orcid"] = summary_df["orcid"].fillna("").astype(str)
    summary_df["status"] = summary_df["status"].fillna("does not fulfill requirements").astype(str)
    summary_df["recent_3_articles"] = summary_df["recent_3_articles"].fillna("").astype(str)
    summary_df["journal_publications_last_6_years"] = pd.to_numeric(
        summary_df.get("journal_publications_last_6_years", 0), errors="coerce"
    ).fillna(0).astype(int)
    summary_df["total_publications_last_6_years"] = pd.to_numeric(
        summary_df.get("total_publications_last_6_years", 0), errors="coerce"
    ).fillna(0).astype(int)

    for col in ["department", "email", "telephone", "rank"]:
        summary_df[col] = summary_df.get(col, "").fillna("").astype(str)

    publications_df["orcid"] = publications_df.get("orcid", "").fillna("").astype(str)
    publications_df["title"] = publications_df.get("title", "").fillna("").astype(str)
    publications_df["publication_type"] = publications_df.get("publication_type", "Unknown").fillna("Unknown").astype(str)
    publications_df["source_title"] = publications_df.get("source_title", "").fillna("").astype(str)
    publications_df["doi"] = publications_df.get("doi", "").fillna("").astype(str)
    publications_df["cover_date"] = publications_df.get("cover_date", "").fillna("").astype(str)
    publications_df["year"] = pd.to_numeric(publications_df.get("year", 0), errors="coerce").fillna(0).astype(int)

    return summary_df, publications_df


def render_master_table(summary_df: pd.DataFrame) -> None:
    st.title("NEXUS Publications Dashboard")
    st.caption("All Scopus publication types in the last 6 years. Click a name to open the profile page.")

    statuses = sorted(summary_df["status"].dropna().unique().tolist())
    c1, c2, c3 = st.columns([1.35, 1.15, 1.15])
    with c1:
        name_query = st.text_input("Search name", placeholder="Type a faculty name...")
    with c2:
        status_filter = st.multiselect("Status", options=statuses, default=statuses)
    with c3:
        min_count = st.slider("Min journal count", min_value=0, max_value=40, value=0)

    filtered = summary_df.copy()
    if name_query:
        filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]
    filtered = filtered[filtered["journal_publications_last_6_years"] >= min_count]
    filtered = filtered.sort_values(
        by=["total_publications_last_6_years", "journal_publications_last_6_years", "name"],
        ascending=[False, False, True],
    )

    st.markdown(
        f"""
        <div class="kpi-wrap">
          <div class="kpi-card"><div class="kpi-label">People Visible</div><div class="kpi-value">{len(filtered)}</div></div>
          <div class="kpi-card"><div class="kpi-label">Fulfills Requirements</div><div class="kpi-value">{int((filtered['status'] == 'fulfills requirements').sum())}</div></div>
          <div class="kpi-card"><div class="kpi-label">Total Publications Visible</div><div class="kpi-value">{int(filtered['total_publications_last_6_years'].sum())}</div></div>
          <div class="kpi-card"><div class="kpi-label">Journal Publications Visible</div><div class="kpi-value">{int(filtered['journal_publications_last_6_years'].sum())}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        label="Download filtered summary CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="summary_filtered.csv",
        mime="text/csv",
    )

    rows_html = []
    for _, row in filtered.iterrows():
        status_value = row["status"]
        status_class = "status-ok" if status_value == "fulfills requirements" else "status-no"
        encoded_orcid = quote_plus(str(row["orcid"]))
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td><a class='name-link' href='?orcid={encoded_orcid}'>{escape(str(row['name']))}</a></td>",
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
            <th>Recent 3 Publications</th>
            <th>Total (6 Years)</th>
            <th>Journals (6 Years)</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html) if rows_html else '<tr><td colspan="5">No matching records.</td></tr>'}
        </tbody>
      </table>
    </div>
    """

    st.markdown(table_html, unsafe_allow_html=True)


def render_profile_page(summary_df: pd.DataFrame, publications_df: pd.DataFrame, orcid: str) -> None:
    person_df = summary_df[summary_df["orcid"] == orcid]
    if person_df.empty:
        st.warning("Selected profile was not found. Please return to the main table.")
        if st.button("Back to Dashboard"):
            st.query_params.clear()
            st.rerun()
        return

    person = person_df.iloc[0]

    if st.button("Back to Dashboard"):
        st.query_params.clear()
        st.rerun()

    st.title(f"{person['name']} - Profile")
    st.caption("All Scopus publications in the last 6 years")

    st.markdown(
        f"""
        <div class="profile-grid">
          <div class="profile-card"><div class="profile-label">Name</div><div class="profile-value">{escape(str(person['name']))}</div></div>
          <div class="profile-card"><div class="profile-label">Department</div><div class="profile-value">{escape(str(person['department'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Rank</div><div class="profile-value">{escape(str(person['rank'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Email</div><div class="profile-value">{escape(str(person['email'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Mobile / Telephone</div><div class="profile-value">{escape(str(person['telephone'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">ORCID</div><div class="profile-value">{escape(str(person['orcid']))}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    person_pubs = publications_df[publications_df["orcid"] == orcid].copy()
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
summary_data, publications_data = load_data()
selected_orcid = get_selected_orcid()

if selected_orcid:
    render_profile_page(summary_data, publications_data, selected_orcid)
else:
    render_master_table(summary_data)
