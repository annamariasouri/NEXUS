import os
from html import escape

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="NEXUS Research Dashboard", layout="wide")


def get_secret_value(key: str) -> str:
        # Streamlit Cloud secrets take priority, local env is fallback.
        if key in st.secrets:
                return str(st.secrets.get(key, "")).strip()
        return os.getenv(key, "").strip()


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
                    --card: rgba(255, 255, 255, 0.82);
                    --border: #d7e2ee;
                    --ok: #0d8f62;
                    --no: #b53b1f;
                }

                .stApp {
                    background:
                        radial-gradient(1200px 600px at -10% -10%, rgba(15, 123, 108, 0.18), transparent 60%),
                        radial-gradient(900px 500px at 110% -10%, rgba(218, 91, 45, 0.15), transparent 55%),
                        linear-gradient(140deg, var(--bg-1), var(--bg-2));
                }

                h1, h2, h3 {
                    font-family: 'Space Grotesk', sans-serif;
                    color: var(--ink);
                    letter-spacing: -0.02em;
                }

                p, div, label, span {
                    font-family: 'IBM Plex Sans', sans-serif;
                }

                .kpi-wrap {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(180px, 1fr));
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
                .kpi-value { color: var(--ink); font-size: 1.45rem; font-weight: 700; }

                .table-shell {
                    background: rgba(255, 255, 255, 0.9);
                    border: 1px solid var(--border);
                    border-radius: 18px;
                    overflow: auto;
                    box-shadow: 0 10px 28px rgba(15, 36, 64, 0.08);
                }

                .nexus-table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 880px;
                }

                .nexus-table thead th {
                    position: sticky;
                    top: 0;
                    z-index: 1;
                    text-align: left;
                    background: #12253a;
                    color: #f8fbff;
                    padding: 12px 14px;
                    font-size: 0.92rem;
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

                .articles-cell {
                    line-height: 1.45;
                    white-space: normal;
                }
                </style>
                """,
                unsafe_allow_html=True,
        )


inject_styles()

st.title("NEXUS Journal Publications Dashboard")
st.caption("Scopus journals only, last 6 years")


# Simple access gate for local/private usage.
def check_password() -> bool:
    required_password = get_secret_value("APP_ACCESS_PASSWORD")
    if not required_password:
        st.error(
            "APP_ACCESS_PASSWORD is not configured. Set it in local .env or Streamlit secrets."
        )
        return False

    if st.session_state.get("authenticated", False):
        return True

    entered = st.text_input("Enter dashboard password", type="password")
    if st.button("Login"):
        if entered == required_password:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Incorrect password")
    return False


if not check_password():
    st.stop()

summary_path = "outputs/summary.csv"
if not os.path.exists(summary_path):
    st.info("No summary found yet. Run the pipeline first to generate outputs/summary.csv.")
    st.stop()

df = pd.read_csv(summary_path)

if df.empty:
    st.warning("Summary file is empty.")
    st.stop()

df["name"] = df["name"].fillna("").astype(str)
df["status"] = df["status"].fillna("does not fulfill requirements").astype(str)
df["journal_publications_last_6_years"] = pd.to_numeric(
    df["journal_publications_last_6_years"], errors="coerce"
).fillna(0).astype(int)
df["recent_3_articles"] = df["recent_3_articles"].fillna("").astype(str)

all_statuses = sorted(df["status"].dropna().unique().tolist())
col1, col2, col3 = st.columns([1.3, 1.1, 1.1])

with col1:
    name_query = st.text_input("Search name", placeholder="Type a name...")
with col2:
    status_filter = st.multiselect("Status", options=all_statuses, default=all_statuses)
with col3:
    min_count = st.slider("Min journal count", min_value=0, max_value=20, value=0)

filtered = df.copy()
if name_query:
    filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
if status_filter:
    filtered = filtered[filtered["status"].isin(status_filter)]
filtered = filtered[filtered["journal_publications_last_6_years"] >= min_count]
filtered = filtered.sort_values(
    by=["journal_publications_last_6_years", "name"], ascending=[False, True]
)

total_people = len(filtered)
met_count = int((filtered["status"] == "fulfills requirements").sum())
not_met_count = int((filtered["status"] == "does not fulfill requirements").sum())

st.markdown(
    f"""
    <div class="kpi-wrap">
      <div class="kpi-card"><div class="kpi-label">People Visible</div><div class="kpi-value">{total_people}</div></div>
      <div class="kpi-card"><div class="kpi-label">Fulfills Requirements</div><div class="kpi-value">{met_count}</div></div>
      <div class="kpi-card"><div class="kpi-label">Does Not Fulfill</div><div class="kpi-value">{not_met_count}</div></div>
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


def format_articles(value: str) -> str:
    parts = [escape(piece.strip()) for piece in value.split("|") if piece.strip()]
    if not parts:
        return "-"
    return "<br>".join(parts)


rows_html = []
for _, row in filtered.iterrows():
    status_value = row["status"]
    status_class = "status-ok" if status_value == "fulfills requirements" else "status-no"
    rows_html.append(
        "".join(
            [
                "<tr>",
                f"<td>{escape(row['name'])}</td>",
                f"<td class='articles-cell'>{format_articles(row['recent_3_articles'])}</td>",
                f"<td><span class='status-pill {status_class}'>{escape(status_value)}</span></td>",
                f"<td>{int(row['journal_publications_last_6_years'])}</td>",
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
        <th>Articles (Recent 3)</th>
        <th>Status</th>
        <th>Journal Count (Last 6 Years)</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html) if rows_html else '<tr><td colspan="4">No matching records.</td></tr>'}
    </tbody>
  </table>
</div>
"""

st.markdown(table_html, unsafe_allow_html=True)
