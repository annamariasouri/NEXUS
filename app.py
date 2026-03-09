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

st.set_page_config(page_title="NEXUS Research Dashboard", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

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
          gap: 12px;
          margin-bottom: 14px;
        }

        .kpi-card {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 14px 16px;
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
          box-shadow: 0 12px 30px rgba(15, 36, 64, 0.1);
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
          background: linear-gradient(90deg, #12253a, #1f3d5a);
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

        .data-freshness {
          background: rgba(255, 255, 255, 0.86);
          border: 1px solid var(--border);
          border-left: 4px solid var(--accent);
          border-radius: 12px;
          padding: 10px 12px;
          margin-bottom: 12px;
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

        .articles-cell, .title-cell {
          line-height: 1.45;
          white-space: normal;
        }

        /* Keep label text normal and style only the checkbox control. */
        .stCheckbox [role="checkbox"] {
          border-color: #0b8a5d !important;
        }

        .stCheckbox [role="checkbox"][aria-checked="true"] {
          background-color: #0b8a5d !important;
          border-color: #0b8a5d !important;
          color: #ffffff !important;
        }

        .stCheckbox label,
        .stCheckbox label span,
        .stCheckbox label p {
          background: transparent !important;
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


def normalize_research_field(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\*+$", "", text).strip()
    return text


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
    summary_df["status"] = summary_df["status"].replace(
      {
        "fulfills requirements": "Faculty sufficiency",
        "does not fulfill requirements": "Research committee review",
      }
    )
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

    publications_df["orcid"] = publications_df.get("orcid", "").fillna("").astype(str)
    publications_df["research_field"] = publications_df.get("research_field", "").fillna("").astype(str)
    publications_df["research_field"] = publications_df["research_field"].map(normalize_research_field)
    publications_df["title"] = publications_df.get("title", "").fillna("").astype(str)
    publications_df["publication_type"] = publications_df.get("publication_type", "Unknown").fillna("Unknown").astype(str)
    publications_df["source_title"] = publications_df.get("source_title", "").fillna("").astype(str)
    publications_df["doi"] = publications_df.get("doi", "").fillna("").astype(str)
    publications_df["cover_date"] = publications_df.get("cover_date", "").fillna("").astype(str)
    publications_df["year"] = pd.to_numeric(publications_df.get("year", 0), errors="coerce").fillna(0).astype(int)

    return summary_df, publications_df


def format_updated_time(path: Path) -> str:
    timestamp = datetime.fromtimestamp(path.stat().st_mtime)
    return timestamp.strftime("%d %b %Y, %H:%M")


def render_freshness_banner() -> None:
    summary_updated = format_updated_time(SUMMARY_PATH)
    pubs_updated = format_updated_time(PUBLICATIONS_PATH)
    st.markdown(
        f"""
        <div class="data-freshness">
          <div><strong>Data freshness:</strong> outputs are loaded from the latest generated CSV files.</div>
          <div class="freshness-meta">Summary updated: {summary_updated} | Publications updated: {pubs_updated} | Weekly automation: Monday 05:00 UTC</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_master_table(summary_df: pd.DataFrame) -> None:
    st.title("NEXUS Publications Dashboard")
    st.caption("All Scopus publication types in the last 6 years. Click a name to open the profile page.")
    render_freshness_banner()

    preferred_status_order = ["Faculty sufficiency", "Research committee review"]
    present_statuses = [s for s in preferred_status_order if s in set(summary_df["status"].dropna().tolist())]
    other_statuses = sorted([s for s in summary_df["status"].dropna().unique().tolist() if s not in present_statuses])
    statuses = present_statuses + other_statuses
    research_fields = sorted([f for f in summary_df["research_field"].dropna().unique().tolist() if f.strip()])
    c1, c2 = st.columns([1.5, 1.5])
    with c1:
        name_query = st.text_input("Search name", placeholder="Type a faculty name...")
    with c2:
        min_count = st.slider("Min journal count", min_value=0, max_value=40, value=0)

    st.markdown("**Status**")
    status_selection: dict[str, bool] = {}
    for status in statuses:
      status_selection[status] = st.checkbox(status, value=True, key=f"status_{status}")
    status_filter = [status for status, is_selected in status_selection.items() if is_selected]

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

    filtered = summary_df.copy()
    if name_query:
        filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]
    if field_filter:
      filtered = filtered[filtered["research_field"].isin(field_filter)]
    filtered = filtered[filtered["journal_publications_last_6_years"] >= min_count]
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

    st.download_button(
        label="Download filtered summary CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="summary_filtered.csv",
        mime="text/csv",
    )

    rows_html = []
    for _, row in filtered.iterrows():
        status_value = row["status"]
        status_class = "status-ok" if status_value == "Faculty sufficiency" else "status-no"
        encoded_orcid = quote_plus(str(row["orcid"]))
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td><a class='name-link' href='?orcid={encoded_orcid}'>{escape(str(row['name']))}</a></td>",
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
            <th>Research Field</th>
            <th>Recent 3 Publications</th>
            <th>Total (6 Years)</th>
            <th>Journals (6 Years)</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html) if rows_html else '<tr><td colspan="6">No matching records.</td></tr>'}
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
    render_freshness_banner()

    st.markdown(
        f"""
        <div class="profile-grid">
          <div class="profile-card"><div class="profile-label">Name</div><div class="profile-value">{escape(str(person['name']))}</div></div>
          <div class="profile-card"><div class="profile-label">Department</div><div class="profile-value">{escape(str(person['department'])) or '-'}</div></div>
          <div class="profile-card"><div class="profile-label">Research Field</div><div class="profile-value">{escape(str(person['research_field'])) or '-'}</div></div>
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
summary_data, publications_data = load_data()
selected_orcid = get_selected_orcid()

if selected_orcid:
    render_profile_page(summary_data, publications_data, selected_orcid)
else:
    render_master_table(summary_data)
