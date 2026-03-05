import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="NEXUS Research Dashboard", layout="wide")

st.title("NEXUS Journal Publications Dashboard")
st.caption("Last 6 years, Scopus journals only")


# Simple access gate for local/private usage.
def check_password() -> bool:
    required_password = os.getenv("APP_ACCESS_PASSWORD", "")
    if not required_password:
        st.warning("APP_ACCESS_PASSWORD is not set. Set it in .env to protect this dashboard.")
        return True

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

status_filter = st.multiselect(
    "Filter by status",
    options=sorted(df["status"].dropna().unique().tolist()),
    default=sorted(df["status"].dropna().unique().tolist()),
)

if status_filter:
    df = df[df["status"].isin(status_filter)]

display_df = df[["name", "recent_3_articles", "status", "journal_publications_last_6_years"]].copy()
display_df = display_df.rename(
    columns={
        "name": "Name",
        "recent_3_articles": "Articles (Recent 3)",
        "status": "Status",
        "journal_publications_last_6_years": "Journal Count (Last 6 Years)",
    }
)

st.dataframe(display_df, use_container_width=True, hide_index=True)
