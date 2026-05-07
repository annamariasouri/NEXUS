from collections.abc import Mapping
from html import escape
import hashlib
import hmac
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
# One roster row = one course section; used for teaching load estimates on dashboard + Teaching Analytics.
# Data: Spring 2025 then Fall 2025 (BUS), concatenated in that order.
SPRING_2025_TEACHING_CSV = "spring_2025_lecturer_courses.csv"
FALL_2025_TEACHING_CSV = "fall_2025_lecturer_courses_BUS.csv"
TEACHING_HOURS_PER_SECTION_WEEK = 3
TEACHING_HOURS_PROJECT_PRACTICUM_WEEK = 1
ABDC_CANDIDATE_PATHS = (
    BASE_DIR / "ABDC.xlsx",
    BASE_DIR / "ABDC_JQL.xlsx",
    BASE_DIR / "ABDC.csv",
    BASE_DIR / "abdc.csv",
    BASE_DIR / "ABDC_journal_list.csv",
    BASE_DIR / "data" / "ABDC.xlsx",
    BASE_DIR / "data" / "ABDC.csv",
)


def _teaching_csv_candidate_paths(filename: str) -> tuple[Path, Path]:
    """Next to app.py (deploy) or parent folder (local OneDrive layout)."""
    return (BASE_DIR / filename, BASE_DIR.parent / filename)


def resolve_teaching_data_file(filename: str) -> Path | None:
    for p in _teaching_csv_candidate_paths(filename):
        if p.exists():
            return p
    return None


def teaching_roster_paths_hint() -> str:
    """Locations checked for Spring + Fall roster files (for error messages)."""
    blocks: list[str] = []
    for fn in (SPRING_2025_TEACHING_CSV, FALL_2025_TEACHING_CSV):
        a, b = _teaching_csv_candidate_paths(fn)
        blocks.append(f"{fn}:\n{a}\n{b}")
    return "\n\n".join(blocks)

st.set_page_config(page_title="NEXUS Dashboard", layout="wide")

# Session-state keys used by the Nexus authentication layer.
SESSION_AUTHENTICATED = "is_authenticated"
SESSION_AUTH_EMAIL = "auth_user_email"
SESSION_AUTH_NAME = "auth_user_name"
AUTH_QP_EMAIL = "auth_user"
AUTH_QP_SIG = "auth_sig"
AUTH_QP_LOGOUT = "logout"

# Friendly display names shown in the top-right profile dropdown.
USER_DISPLAY_NAMES = {
    "souri.am@unic.ac.cy": "Annamaria Souri",
    "kokkinaki.a@unic.ac.cy": "Angelika Kokkinaki",
}


def init_auth_state() -> None:
    """Initialize authentication state once per session."""
    st.session_state.setdefault(SESSION_AUTHENTICATED, False)
    st.session_state.setdefault(SESSION_AUTH_EMAIL, "")
    st.session_state.setdefault(SESSION_AUTH_NAME, "")
    restore_auth_from_query_params()


def get_auth_credentials() -> dict[str, str]:
    """Load credentials from Streamlit secrets as {lower_email: password}."""
    auth_block = st.secrets.get("nexus_auth", {})
    users = auth_block.get("users", []) if isinstance(auth_block, Mapping) else []
    credentials: dict[str, str] = {}
    for user in users:
        if not isinstance(user, Mapping):
            continue
        email = str(user.get("email", "")).strip().lower()
        password = str(user.get("password", ""))
        if email and password:
            credentials[email] = password
    return credentials


def _auth_signing_key() -> str:
    """Resolve HMAC key used to persist auth across URL-based navigation."""
    auth_block = st.secrets.get("nexus_auth", {})
    if isinstance(auth_block, Mapping):
        key = str(auth_block.get("signing_key", "")).strip()
        if key:
            return key
    return "nexus-auth-signing-key"


def auth_signature(email: str) -> str:
    """Build deterministic auth signature for URL persistence."""
    email_norm = str(email).strip().lower()
    digest = hmac.new(
        _auth_signing_key().encode("utf-8"),
        email_norm.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def set_internal_query_params(**params: str) -> None:
    """
    Replace URL query params while preserving auth markers for hard-link navigation.
    """
    out: dict[str, str] = {}
    email = str(st.session_state.get(SESSION_AUTH_EMAIL, "")).strip().lower()
    if email:
        out[AUTH_QP_EMAIL] = email
        out[AUTH_QP_SIG] = auth_signature(email)
    for key, value in params.items():
        val = str(value).strip()
        if val:
            out[key] = val
    st.query_params.clear()
    for key, value in out.items():
        st.query_params[key] = value


def build_internal_href(
    *,
    page: str | None = None,
    cohort: str | None = None,
    orcid: str | None = None,
) -> str:
    """Create internal links that preserve authenticated identity markers."""
    parts: list[tuple[str, str]] = []
    if page:
        parts.append(("page", page))
    if cohort:
        parts.append(("cohort", cohort))
    if orcid:
        parts.append(("orcid", orcid))

    email = str(st.session_state.get(SESSION_AUTH_EMAIL, "")).strip().lower()
    if email:
        parts.append((AUTH_QP_EMAIL, email))
        parts.append((AUTH_QP_SIG, auth_signature(email)))

    if not parts:
        return "?"
    q = "&".join(f"{k}={quote_plus(v)}" for k, v in parts)
    return f"?{q}"


def restore_auth_from_query_params() -> None:
    """Rehydrate session auth when URL navigation creates a fresh Streamlit session."""
    if st.session_state.get(SESSION_AUTHENTICATED, False):
        return

    email = normalize_query_value(st.query_params.get(AUTH_QP_EMAIL, "")).strip().lower()
    sig = normalize_query_value(st.query_params.get(AUTH_QP_SIG, "")).strip()
    if not email or not sig:
        return

    credentials = get_auth_credentials()
    if email not in credentials:
        return
    if not hmac.compare_digest(sig, auth_signature(email)):
        return

    st.session_state[SESSION_AUTHENTICATED] = True
    st.session_state[SESSION_AUTH_EMAIL] = email
    st.session_state[SESSION_AUTH_NAME] = USER_DISPLAY_NAMES.get(email, email)


def should_sign_out_from_query_params() -> bool:
    """Detect explicit logout request from URL query params."""
    raw = normalize_query_value(st.query_params.get(AUTH_QP_LOGOUT, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def build_logout_href() -> str:
    """Build URL for navbar sign-out action."""
    return f"?{AUTH_QP_LOGOUT}=1"


def resolve_logo_path() -> Path | None:
    """Find the Nexus logo from common project locations."""
    candidates = (
        BASE_DIR / "assets" / "nexus-logo.png",
        BASE_DIR / "assets" / "nexus-logo.jpg",
        BASE_DIR / "assets" / "logo.png",
        BASE_DIR / "logo.png",
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def sign_out() -> None:
    """Clear auth session and return to login page."""
    st.session_state[SESSION_AUTHENTICATED] = False
    st.session_state[SESSION_AUTH_EMAIL] = ""
    st.session_state[SESSION_AUTH_NAME] = ""
    st.query_params.clear()
    st.rerun()


def inject_login_styles() -> None:
    """Inject premium login-page styling for Nexus."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .stApp {
          background: #edf1f6;
          font-family: 'Inter', sans-serif;
        }

        .stApp::before {
          content: "";
          position: fixed;
          top: clamp(16vh, 20vh, 24vh);
          left: 50%;
          transform: translateX(-50%);
          width: min(1320px, 94vw);
          height: min(68vh, 620px);
          background:
            radial-gradient(360px 260px at 16% 92%, rgba(31, 149, 255, 0.45), transparent 64%),
            radial-gradient(300px 220px at 62% 0%, rgba(60, 145, 255, 0.24), transparent 60%),
            linear-gradient(135deg, #0e7ad7 0%, #0f67bd 42%, #0b5aaa 100%);
          border-radius: 22px;
          border: 1px solid rgba(14, 93, 171, 0.35);
          box-shadow: 0 25px 45px rgba(15, 34, 62, 0.22);
          z-index: 0;
          pointer-events: none;
        }

        .block-container {
          position: relative;
          z-index: 1;
          padding-top: clamp(18vh, 22vh, 26vh) !important;
        }

        .nexus-row-offset {
          height: clamp(1.6rem, 4.6vh, 3rem);
        }

        .nexus-login-grid {
          max-width: 980px;
          margin: 0 auto;
        }

        .nexus-left-panel {
          color: #f4f8ff;
          max-width: 360px;
          padding-top: 0.6rem;
          padding-left: clamp(0.4rem, 1.2vw, 1.2rem);
        }

        .nexus-right-panel {
          max-width: 470px;
          margin-left: auto;
          padding-top: 0.6rem;
        }

        .nexus-left-panel h1 {
          margin: 0;
          font-size: clamp(2rem, 4vw, 2.7rem);
          font-weight: 700;
          letter-spacing: 0.08em;
          color: #ffffff !important;
          text-shadow: 0 2px 8px rgba(5, 34, 75, 0.28);
        }

        .nexus-left-panel h2 {
          margin: 0.7rem 0 0 0;
          font-size: 1.12rem;
          line-height: 1.35;
          font-weight: 600;
          letter-spacing: 0.02em;
          color: #ffffff !important;
          text-shadow: 0 1px 6px rgba(5, 34, 75, 0.24);
        }

        .nexus-left-panel p {
          margin-top: 1rem;
          color: #f3f8ff !important;
          font-size: 0.92rem;
          line-height: 1.55;
          text-shadow: 0 1px 4px rgba(5, 34, 75, 0.20);
        }

        .nexus-auth-brand {
          text-align: left;
          margin-bottom: 0.9rem;
        }

        .nexus-auth-brand h1 {
          margin: 0;
          font-size: clamp(2rem, 3.3vw, 2.4rem);
          font-weight: 700;
          color: #ffffff !important;
          letter-spacing: -0.02em;
          text-shadow: 0 2px 8px rgba(5, 34, 75, 0.24);
        }

        .nexus-auth-brand p {
          margin: 0.25rem 0 0.7rem 0;
          color: #eaf3ff;
          font-size: 0.75rem;
          font-weight: 500;
          text-shadow: 0 1px 4px rgba(5, 34, 75, 0.20);
        }

        div[data-testid="stForm"] {
          background: rgba(247, 249, 252, 0.99);
          border: 1px solid rgba(21, 36, 58, 0.10);
          border-radius: 18px;
          padding: 1.05rem 1rem 0.9rem 1rem;
          box-shadow: 0 18px 32px rgba(18, 32, 54, 0.24);
          margin-right: 0;
        }

        div[data-testid="stTextInput"] label p {
          color: #5b6880 !important;
          font-weight: 600 !important;
          font-size: 0.82rem !important;
        }

        div[data-testid="stTextInput"] input {
          border-radius: 12px !important;
          border: 1px solid #d8dde6 !important;
          background: #ffffff !important;
          transition: all 0.2s ease !important;
          min-height: 42px !important;
        }

        div[data-testid="stTextInput"] input:hover {
          border-color: #b5c5da !important;
          box-shadow: 0 3px 12px rgba(20, 53, 97, 0.08) !important;
        }

        div[data-testid="stTextInput"] input:focus {
          border-color: #0f66c3 !important;
          box-shadow: 0 0 0 3px rgba(15, 102, 195, 0.14) !important;
        }

        div[data-testid="stCheckbox"] label p {
          color: #5f6d80 !important;
          font-size: 0.78rem !important;
          font-weight: 500 !important;
        }

        div[data-testid="stForm"] button[kind="secondaryFormSubmit"] {
          border-radius: 12px !important;
          border: none !important;
          background: linear-gradient(90deg, #0f63c0, #0f79da) !important;
          color: #ffffff !important;
          font-weight: 600 !important;
          min-height: 44px !important;
          transition: transform 0.18s ease, box-shadow 0.18s ease !important;
          box-shadow: 0 10px 20px rgba(14, 96, 183, 0.28) !important;
        }

        div[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover {
          transform: translateY(-1px);
          box-shadow: 0 14px 24px rgba(14, 96, 183, 0.34) !important;
        }

        @media (max-width: 980px) {
          .stApp::before {
            top: 12vh;
            height: min(62vh, 520px);
          }
          .block-container {
            padding-top: 13vh !important;
          }
          .nexus-row-offset { height: 1rem; }
          .nexus-left-panel {
            padding-top: 0.6rem;
            max-width: 100%;
          }
          .nexus-right-panel {
            max-width: 100%;
            margin-left: 0;
            padding-top: 0.3rem;
          }
          div[data-testid="stForm"] { margin-right: 0; }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_profile_styles() -> None:
    """Polish the top-right user dropdown in authenticated views."""
    st.markdown(
        """
        <style>
        div[data-testid="stPopover"] button {
          border-radius: 999px !important;
          border: 1px solid rgba(19, 40, 67, 0.16) !important;
          background: rgba(255, 255, 255, 0.92) !important;
          font-weight: 600 !important;
          color: #12253c !important;
          transition: box-shadow 0.16s ease, border-color 0.16s ease !important;
        }
        div[data-testid="stPopover"] button:hover {
          border-color: rgba(19, 40, 67, 0.34) !important;
          box-shadow: 0 8px 18px rgba(19, 40, 67, 0.14) !important;
        }
        div[data-testid="stPopoverContent"] button[kind="secondary"] {
          border-radius: 10px !important;
          font-weight: 600 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login_page() -> None:
    """Render the login screen and set session state on successful auth."""
    inject_login_styles()

    outer_left, outer_center, outer_right = st.columns([0.16, 0.68, 0.16])
    with outer_center:
        st.markdown('<div class="nexus-row-offset"></div>', unsafe_allow_html=True)
        st.markdown('<div class="nexus-login-grid">', unsafe_allow_html=True)
        left_col, right_col = st.columns([1, 1], gap="small")
        with left_col:
            st.markdown(
                """
                <div class="nexus-left-panel">
                  <h1>WELCOME</h1>
                  <h2>ACADEMIC INTELLIGENCE &amp;<br/>RESEARCH ANALYTICS PLATFORM</h2>
                  <p>
                    Securely access Nexus to explore faculty productivity, teaching allocation,
                    and institutional research intelligence through a modern analytics workspace.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with right_col:
            st.markdown('<div class="nexus-right-panel">', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="nexus-auth-brand">
                  <h1>Log In</h1>
                  <p>Use the credentials sent to you via email to continue</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.form("nexus_login_form", clear_on_submit=False):
                email_input = st.text_input(
                    "User Name",
                    placeholder="Enter your email",
                )
                password_input = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Enter your password",
                )
                submit = st.form_submit_button("Log In", use_container_width=True)

            if submit:
                email = email_input.strip().lower()
                credentials = get_auth_credentials()
                expected_password = credentials.get(email)

                # Constant-time comparison avoids timing attacks on password checks.
                if expected_password and hmac.compare_digest(password_input, expected_password):
                    st.session_state[SESSION_AUTHENTICATED] = True
                    st.session_state[SESSION_AUTH_EMAIL] = email
                    st.session_state[SESSION_AUTH_NAME] = USER_DISPLAY_NAMES.get(email, email)
                    set_internal_query_params()
                    st.rerun()
                else:
                    st.error("Invalid email or password. Please try again.")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with outer_left:
        st.empty()
    with outer_right:
        st.empty()


def render_profile_dropdown() -> None:
    """Show authenticated user menu with a sign-out action."""
    spacer, menu_col = st.columns([9, 1.6])
    with spacer:
        st.empty()
    with menu_col:
        user_name = st.session_state.get(SESSION_AUTH_NAME, "User")
        with st.popover(user_name, use_container_width=True):
            if st.button("Sign Out", use_container_width=True):
                sign_out()


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
          /* Faculty profile (fp-*) */
          --fp-primary-900: #0A2540;
          --fp-primary-700: #1565C0;
          --fp-primary-500: #1E88E5;
          --fp-primary-400: #42A5F5;
          --fp-primary-300: #64B5F6;
          --fp-primary-200: #BBDEFB;
          --fp-primary-100: #BBDEFB;
          --fp-primary-50: #E3F2FD;
          --fp-neutral-900: #1A1A2E;
          --fp-neutral-700: #4B5563;
          --fp-neutral-500: #6B7280;
          --fp-neutral-200: #E5E7EB;
          --fp-neutral-50: #F9FAFB;
          --fp-white: #FFFFFF;
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

        /* Research output: on-brand multiselect tags (blue family, not red/coral) */
        .stMultiSelect [data-baseweb="tag"] {
          max-width: none !important;
          background: var(--fp-primary-100) !important;
          border: 1px solid var(--fp-primary-200) !important;
          border-radius: 20px !important;
        }

        .stMultiSelect [data-baseweb="tag"] span {
          max-width: none !important;
          overflow: visible !important;
          text-overflow: clip !important;
          white-space: nowrap !important;
          color: var(--fp-primary-700) !important;
          font-size: 14px !important;
          font-weight: 500 !important;
        }

        .stMultiSelect [data-baseweb="tag"] [role="button"] svg {
          fill: var(--fp-primary-500) !important;
        }

        /* Research output: radio + checkbox accent (primary blue) */
        [data-testid="stRadio"] [data-baseweb="radio"] {
          border-color: var(--fp-neutral-300) !important;
        }
        [data-testid="stRadio"] [aria-checked="true"] > div:first-child {
          border-color: var(--fp-primary-500) !important;
          background: var(--fp-primary-500) !important;
        }
        [data-testid="stCheckbox"] [data-baseweb="checkbox"] {
          border-color: var(--fp-neutral-300) !important;
          border-radius: 4px !important;
        }
        [data-testid="stCheckbox"] [data-state="checked"] [data-baseweb="checkbox"] {
          background: var(--fp-primary-500) !important;
          border-color: var(--fp-primary-500) !important;
        }

        .ro-kpi-ico {
          display: inline-flex;
          color: var(--fp-primary-300);
          flex-shrink: 0;
        }
        .ro-kpi-ico svg {
          width: 18px;
          height: 18px;
        }
        .ro-field-section-label {
          font-size: 13px;
          font-weight: 600;
          color: var(--fp-primary-700);
          margin: 0 0 12px 0;
          padding-top: 16px;
          border-top: 1px solid var(--fp-neutral-200);
          font-family: 'Inter', system-ui, sans-serif;
        }
        .ro-field-group-title {
          font-size: 12px;
          font-weight: 600;
          color: var(--fp-neutral-900);
          margin: 0 0 8px 0;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .ro-filter-actions { display: flex; flex-direction: column; gap: 12px; justify-content: flex-end; align-items: flex-start; padding-top: 20px; }
        .ro-inline-dl { display: flex; justify-content: flex-end; align-items: center; gap: 8px; }
        .ro-inline-dl [data-testid="stDownloadButton"] button {
          border: none !important;
          background: transparent !important;
          color: var(--fp-primary-700) !important;
          font-size: 13px !important;
          font-weight: 500 !important;
          padding: 0 !important;
          box-shadow: none !important;
        }
        .ro-inline-dl [data-testid="stDownloadButton"] button:hover {
          color: var(--fp-primary-500) !important;
          background: transparent !important;
        }
        section[data-testid="stExpander"] details > summary svg {
          color: var(--fp-primary-500) !important;
          transition: transform 0.25s ease-out;
        }
        section[data-testid="stExpander"] details[open] > summary svg {
          transform: rotate(90deg);
        }
        [data-testid="stExpanderDetails"] {
          transition: max-height 0.25s ease-out, opacity 0.2s ease;
        }

        .ro-page-header {
          font-family: 'Inter', system-ui, sans-serif;
          max-width: min(1320px, 98vw);
          margin: 0 auto;
          padding: 40px 20px 32px 20px;
        }
        .ro-page-header h1 {
          font-size: 32px;
          font-weight: 700;
          color: var(--fp-primary-900);
          margin: 0;
          letter-spacing: -0.02em;
        }
        .ro-caption-refresh {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 8px;
          font-size: 12px;
          font-weight: 400;
          color: var(--fp-neutral-500);
        }
        .ro-accent-bar {
          width: 40px;
          height: 3px;
          background: var(--fp-primary-500);
          border-radius: 2px;
          margin-top: 8px;
        }
        .ro-caption-refresh svg { flex-shrink: 0; color: var(--fp-neutral-400); }

        .ro-kpi-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          max-width: min(1320px, 98vw);
          margin: 0 auto 8px auto;
          padding: 0 20px;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .ro-kpi-card {
          background: var(--fp-white);
          border-radius: 12px;
          padding: 24px;
          border-left: 4px solid var(--fp-primary-500);
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        .ro-kpi-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        .ro-kpi-top {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--fp-neutral-500);
          margin-bottom: 12px;
        }
        .ro-kpi-val {
          font-size: 28px;
          font-weight: 700;
          color: var(--fp-primary-900);
          line-height: 1.15;
          font-variant-numeric: tabular-nums;
        }
        .ro-kpi-dl-row {
          max-width: min(1320px, 98vw);
          margin: 0 auto 24px auto;
          padding: 0 20px;
          text-align: right;
          font-family: 'Inter', system-ui, sans-serif;
        }

        .ro-table-shell {
          max-width: min(1320px, 98vw);
          margin: 24px auto 48px auto;
          padding: 0 20px;
        }
        .ro-table-card {
          background: var(--fp-white);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        }
        table.ro-table {
          width: 100%;
          border-collapse: collapse;
          min-width: 960px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 14px;
        }
        table.ro-table thead th {
          background: var(--fp-primary-50);
          color: var(--fp-primary-700);
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          height: 48px;
          padding: 0 14px;
          text-align: left;
          vertical-align: middle;
          border-bottom: 2px solid var(--fp-primary-300);
        }
        table.ro-table thead th.ro-th-num,
        table.ro-table thead th.ro-th-center { text-align: center; }
        table.ro-table thead th .ro-th-sub {
          display: block;
          font-size: 11px;
          font-weight: 500;
          text-transform: none;
          letter-spacing: 0.02em;
          color: var(--fp-primary-700);
          opacity: 0.85;
          margin-top: 2px;
        }
        table.ro-table tbody td {
          padding: 16px 14px;
          border-bottom: 1px solid var(--fp-neutral-200);
          vertical-align: top;
          color: var(--fp-neutral-900);
        }
        table.ro-table tbody tr:nth-child(odd) { background: var(--fp-white); }
        table.ro-table tbody tr:nth-child(even) { background: var(--fp-neutral-50); }
        table.ro-table tbody tr {
          transition: background 0.15s ease, box-shadow 0.15s ease;
        }
        table.ro-table tbody tr:hover {
          background: var(--fp-primary-50) !important;
          box-shadow: inset 3px 0 0 0 var(--fp-primary-500);
        }
        .ro-name-link {
          color: var(--fp-primary-700);
          font-weight: 500;
          text-decoration: none;
        }
        .ro-name-link:hover {
          text-decoration: underline;
          text-decoration-color: var(--fp-primary-300);
          text-underline-offset: 2px;
        }
        .ro-entity-pill {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          background: var(--fp-primary-50);
          border: 1px solid var(--fp-primary-200);
          color: var(--fp-primary-700);
          white-space: nowrap;
        }
        .ro-status-pill {
          display: inline-block;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 600;
          white-space: normal;
          max-width: 100%;
        }
        .ro-status-pill.ro-status-sufficiency {
          color: #166534;
          background: #ecfdf5;
          border: 1px solid #bbf7d0;
        }
        .ro-status-pill.ro-status-committee {
          color: #854d0e;
          background: #fef9c3;
          border: 1px solid #fde047;
        }
        .ro-status-pill.ro-status-hod {
          color: #b91c1c;
          background: #fef2f2;
          border: 1px solid #fecaca;
        }
        .ro-status-pill.ro-status-default {
          color: var(--fp-neutral-900);
          background: var(--fp-neutral-50);
          border: 1px solid var(--fp-neutral-200);
        }
        .ro-articles {
          font-size: 13px;
          color: var(--fp-neutral-700);
          line-height: 1.45;
        }
        .ro-articles .ro-pub-line {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          margin-bottom: 8px;
        }
        .ro-articles .ro-pub-line:last-child { margin-bottom: 0; }
        .ro-pub-year {
          font-weight: 600;
          color: var(--fp-primary-700);
          margin-right: 4px;
        }
        .ro-empty {
          text-align: center;
          padding: 48px 24px;
          color: var(--fp-neutral-500);
          font-size: 16px;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .ro-empty svg { margin: 0 auto 12px auto; display: block; color: var(--fp-primary-200); }
        @media (max-width: 1199px) {
          .ro-kpi-grid { grid-template-columns: 1fr 1fr; }
          .ro-table-card { overflow-x: auto; }
        }
        @media (max-width: 767px) {
          .ro-kpi-grid { grid-template-columns: 1fr; }
        }

        .nexus-dashboard-subtitle {
          font-size: 0.92rem;
          color: var(--muted);
          font-weight: 500;
          margin: -0.2rem 0 0.65rem 0;
          line-height: 1.35;
        }

        section[data-testid="stExpander"] {
          border: none;
          border-radius: 12px;
          background: var(--fp-white);
          margin-bottom: 32px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          font-family: 'Inter', system-ui, sans-serif;
        }

        section[data-testid="stExpander"] details summary {
          min-height: 48px !important;
          padding: 12px 16px !important;
          font-size: 14px !important;
          font-weight: 600 !important;
          color: var(--fp-primary-700) !important;
          letter-spacing: 0.01em;
        }

        section[data-testid="stExpander"] details summary span {
          font-size: 14px !important;
          font-weight: 600 !important;
          color: var(--fp-primary-700) !important;
        }

        section[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
          padding: 24px !important;
        }

        /* —— Landing: same typography + fp-* palette as Research / Faculty profile —— */
        .nexus-nav-shell {
          font-family: 'Inter', system-ui, sans-serif;
          margin: 0 0 1.5rem 0;
          padding: 0.5rem 0 0.75rem 0;
          background: var(--fp-white);
          border-bottom: 1px solid var(--fp-neutral-200);
          border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
        }
        .nexus-nav {
          max-width: min(1320px, 98vw);
          margin: 0 auto;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 0.25rem 1.25rem;
          font-size: 13px;
          font-weight: 500;
        }
        .nexus-nav-links {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: center;
          gap: 0.25rem 1.25rem;
          margin: 0 auto;
        }
        .nexus-nav a {
          color: var(--fp-neutral-500);
          text-decoration: none;
          padding: 0.35rem 0.15rem;
          border-radius: 6px;
          transition: color 0.15s ease, background 0.15s ease;
        }
        .nexus-nav a:hover {
          color: var(--fp-primary-700);
          background: var(--fp-primary-50);
        }
        .nexus-nav a.nexus-nav-active {
          color: var(--fp-primary-700);
          font-weight: 600;
        }
        .nexus-nav-sep { color: var(--fp-neutral-200); user-select: none; }
        .nexus-nav-signout {
          color: var(--fp-neutral-700) !important;
          font-weight: 600 !important;
          margin-right: 0.55rem;
        }
        .nexus-nav-signout:hover {
          color: var(--fp-primary-700) !important;
          background: var(--fp-primary-50) !important;
        }

        .nexus-hero-v2 {
          position: relative;
          font-family: 'Inter', system-ui, sans-serif;
          text-align: center;
          padding: 2.5rem 1.5rem 2.25rem;
          margin: 0 auto 2rem;
          max-width: min(920px, 98vw);
          border-radius: 12px;
          background: var(--fp-white);
          border: 1px solid var(--fp-neutral-200);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
          overflow: hidden;
        }
        .nexus-hero-pattern {
          position: absolute;
          inset: 0;
          opacity: 0.35;
          background-image: radial-gradient(circle at 1px 1px, rgba(30, 136, 229, 0.08) 1px, transparent 0);
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
          background: radial-gradient(ellipse, rgba(30, 136, 229, 0.06) 0%, transparent 70%);
          pointer-events: none;
        }
        .nexus-hero-inner {
          position: relative;
          z-index: 1;
          width: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          box-sizing: border-box;
        }
        .nexus-pill {
          display: inline-block;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--fp-primary-700);
          background: var(--fp-primary-50);
          border: 1px solid var(--fp-primary-200);
          padding: 0.4rem 0.9rem;
          border-radius: 999px;
          margin-bottom: 1rem;
        }
        .nexus-hero-brand {
          font-family: 'Inter', system-ui, sans-serif;
          font-size: clamp(2.75rem, 6vw, 3.75rem);
          font-weight: 700;
          letter-spacing: -0.045em;
          color: var(--fp-primary-900);
          margin: 0 0 0.75rem 0;
          line-height: 1.05;
          width: 100%;
          text-align: center !important;
        }
        .nexus-hero-sub {
          font-size: clamp(1rem, 2.1vw, 1.2rem);
          font-weight: 500;
          color: var(--fp-neutral-900);
          width: 100%;
          max-width: 36rem;
          margin: 0 0 0.6rem 0;
          line-height: 1.45;
          text-align: center !important;
          box-sizing: border-box;
        }
        .nexus-hero-micro {
          font-size: 12px;
          font-weight: 400;
          color: var(--fp-neutral-500);
          width: 100%;
          max-width: 28rem;
          margin: 0;
          line-height: 1.5;
          text-align: center !important;
          box-sizing: border-box;
        }
        [data-testid="stMarkdownContainer"] .nexus-hero-v2 .nexus-hero-brand,
        [data-testid="stMarkdownContainer"] .nexus-hero-v2 .nexus-hero-sub,
        [data-testid="stMarkdownContainer"] .nexus-hero-v2 .nexus-hero-micro {
          text-align: center !important;
        }

        .nexus-module-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.25rem;
          max-width: min(1320px, 98vw);
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
          border-radius: 12px;
          border: 1px solid var(--fp-neutral-200);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
          background: var(--fp-white);
          transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
        }
        .nexus-module:hover {
          transform: translateY(-2px);
          border-color: var(--fp-primary-500);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
          background: var(--fp-primary-50);
        }
        .nexus-module-icon {
          display: flex;
          align-items: center;
          justify-content: flex-start;
          margin-bottom: 0.65rem;
          color: var(--fp-primary-500);
        }
        .nexus-module-icon svg {
          width: 28px;
          height: 28px;
          opacity: 0.95;
        }
        .nexus-module-title {
          display: block;
          font-size: 17px;
          font-weight: 600;
          color: var(--fp-primary-900);
          margin-bottom: 0.35rem;
          letter-spacing: -0.02em;
        }
        .nexus-module-desc {
          display: block;
          font-size: 13px;
          color: var(--fp-neutral-700);
          line-height: 1.45;
        }

        .nexus-kpi-strip {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 1rem;
          max-width: min(1320px, 98vw);
          margin: 0 auto 2rem;
          font-family: 'Inter', system-ui, sans-serif;
        }
        @media (max-width: 900px) {
          .nexus-kpi-strip { grid-template-columns: repeat(2, 1fr); }
        }
        .nexus-kpi-card {
          padding: 1.25rem 1.25rem 1.2rem;
          border-radius: 12px;
          background: var(--fp-white);
          border: 1px solid var(--fp-neutral-200);
          border-left: 4px solid var(--fp-primary-500);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
          transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        .nexus-kpi-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }
        .nexus-kpi-label {
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--fp-neutral-500);
          margin-bottom: 0.35rem;
        }
        .nexus-kpi-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--fp-primary-900);
          letter-spacing: -0.02em;
          line-height: 1.2;
          font-variant-numeric: tabular-nums;
        }
        .nexus-kpi-sub {
          font-size: 11px;
          font-weight: 400;
          color: var(--fp-neutral-500);
          margin-top: 0.35rem;
          line-height: 1.35;
        }

        @media (max-width: 900px) {
          .kpi-wrap { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
          .profile-grid { grid-template-columns: 1fr; }
          .nexus-table { min-width: 820px; }
        }

        /* Faculty teaching: same fp palette + Inter as Research Output (.ro-table) */
        .teach-dash-wrap {
          font-family: 'Inter', system-ui, sans-serif;
          width: 100%;
          margin: 4px 0 12px 0;
          border-radius: 12px;
          border: 1px solid var(--fp-neutral-200);
          background: var(--fp-white);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
          overflow-x: auto;
        }
        .teach-strip {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem 2.25rem;
          padding: 0.65rem 1rem;
          background: var(--fp-neutral-50);
          border-bottom: 1px solid var(--fp-neutral-200);
          font-size: 13px;
          color: var(--fp-neutral-700);
          line-height: 1.45;
        }
        .teach-strip strong { color: var(--fp-primary-900); font-weight: 600; }
        /* Div-based grid only (no <table>): avoids broken layout when grid is applied inside table rows */
        .teach-faculty-shell {
          width: 100%;
          min-width: 0;
          font-size: 14px;
        }
        .teach-faculty-body {
          width: 100%;
        }
        /* Shared grid: header + rows — no column gutters (reads as one table) */
        .teach-faculty-cols {
          display: grid;
          grid-template-columns:
            minmax(9.5rem, 0.42fr)
            minmax(4rem, 0.18fr)
            minmax(6.25rem, 0.22fr)
            minmax(5rem, 0.18fr)
            minmax(3.75rem, 0.14fr);
          column-gap: 0;
          row-gap: 0;
          align-items: stretch;
          justify-items: stretch;
          box-sizing: border-box;
          width: 100%;
        }
        .teach-faculty-header.teach-faculty-cols > div {
          padding: 0.5rem 0.75rem;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: var(--fp-primary-700);
          background: var(--fp-primary-50);
          border-bottom: 2px solid var(--fp-primary-300);
          border-right: 1px solid var(--fp-primary-200);
          text-align: left;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          box-sizing: border-box;
          min-width: 0;
          width: 100%;
        }
        .teach-faculty-header.teach-faculty-cols > div:nth-child(2),
        .teach-faculty-header.teach-faculty-cols > div:nth-child(3),
        .teach-faculty-header.teach-faculty-cols > div:nth-child(4) {
          text-align: left;
        }
        .teach-faculty-header.teach-faculty-cols > div:nth-child(3),
        .teach-faculty-header.teach-faculty-cols > div:nth-child(4) {
          white-space: normal;
          line-height: 1.2;
        }
        .teach-faculty-header.teach-faculty-cols > div:last-child {
          border-right: none;
          text-align: right;
        }
        .teach-season-cell {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 2px;
          width: 100%;
          justify-self: stretch;
        }
        .teach-fall-delta-note {
          font-size: 11px;
          font-weight: 400;
          color: var(--fp-neutral-500);
          text-transform: lowercase;
          line-height: 1.25;
          letter-spacing: 0.01em;
        }
        details.teach-faccard {
          margin: 0;
          border-bottom: 1px solid var(--fp-neutral-200);
        }
        details.teach-faccard:last-of-type { border-bottom: none; }
        details.teach-faccard > summary.teach-faculty-cols {
          list-style: none;
          cursor: pointer;
          padding: 0;
          transition: background 0.15s ease, box-shadow 0.15s ease;
        }
        /* Body cells: flush columns + light dividers (no white gutters) */
        details.teach-faccard > summary.teach-faculty-cols > * {
          padding: 0.5rem 0.75rem;
          box-sizing: border-box;
          min-width: 0;
          background: var(--fp-white);
          border-right: 1px solid var(--fp-neutral-200);
        }
        details.teach-faccard > summary.teach-faculty-cols > *:last-child {
          border-right: none;
        }
        details.teach-faccard > summary.teach-faculty-cols::-webkit-details-marker { display: none; }
        details.teach-faccard > summary.teach-faculty-cols:hover > * {
          background: var(--fp-primary-50) !important;
        }
        details.teach-faccard > summary.teach-faculty-cols:hover {
          box-shadow: inset 3px 0 0 0 var(--fp-primary-500);
        }
        details.teach-faccard[open] > summary.teach-faculty-cols > * {
          background: var(--fp-neutral-50);
        }
        .teach-col-name {
          font-weight: 600;
          color: var(--fp-neutral-900);
          font-size: 14px;
          line-height: 1.35;
          text-align: left;
          width: 100%;
          justify-self: stretch;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .teach-col-num {
          font-weight: 600;
          color: var(--fp-neutral-900);
          font-variant-numeric: tabular-nums;
          font-size: 14px;
          text-align: left;
          width: 100%;
          justify-self: stretch;
        }
        .teach-hours-val {
          font-weight: 600;
          color: var(--fp-primary-700);
          font-variant-numeric: tabular-nums;
          font-size: 13px;
          text-align: left;
          align-self: flex-start;
          width: 100%;
        }
        .teach-col-toggle {
          text-align: right;
          font-size: 12px;
          color: var(--fp-neutral-500);
          user-select: none;
          font-weight: 500;
          width: 100%;
          justify-self: stretch;
        }
        details.teach-faccard[open] .teach-toggle-hint-open { display: inline; }
        details.teach-faccard:not([open]) .teach-toggle-hint-open { display: none; }
        details.teach-faccard[open] .teach-toggle-hint-closed { display: none; }
        details.teach-faccard:not([open]) .teach-toggle-hint-closed { display: inline; }
        .teach-nested {
          padding: 0.35rem 0.75rem 0.75rem 1rem;
          margin: 0 0.5rem 0.4rem 0.75rem;
          border-left: 2px solid var(--fp-primary-200);
          background: var(--fp-white);
          font-size: 13px;
          color: var(--fp-neutral-700);
          line-height: 1.48;
        }
        .teach-nested-line {
          padding: 0.2rem 0;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          color: var(--fp-neutral-900);
          letter-spacing: 0.01em;
        }
        details.teach-faccard.teach-load-high > summary {
          box-shadow: inset 3px 0 0 0 var(--accent-2);
        }
        details.teach-faccard.teach-load-mid > summary {
          box-shadow: inset 3px 0 0 0 var(--fp-primary-500);
        }
        details.teach-faccard.teach-load-low > summary {
          box-shadow: inset 3px 0 0 0 var(--fp-primary-300);
        }

        /* Slightly wider main column so profile + tables use less side dead space */
        main .block-container,
        section[data-testid="stMain"] > div.block-container {
          max-width: min(1320px, 98vw) !important;
          padding-left: 1.25rem !important;
          padding-right: 1.25rem !important;
        }

        .fp-max {
          max-width: min(1320px, 98vw);
          margin-left: auto;
          margin-right: auto;
          padding-left: 20px;
          padding-right: 20px;
        }
        .fp-nav {
          width: auto;
          min-height: 56px;
          background: var(--fp-white);
          border-bottom: 1px solid var(--fp-neutral-200);
          box-shadow: 0 1px 0 rgba(0,0,0,0.04);
          font-family: 'Inter', system-ui, sans-serif;
          border-radius: 12px;
          overflow: hidden;
        }
        .fp-nav-inner {
          max-width: min(1320px, 98vw);
          margin: 0 auto;
          padding: 0 24px;
          height: 56px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }
        /* Sticky breadcrumb bar (markdown block that contains the nav) */
        .element-container:has(nav.fp-nav-sticky) {
          position: sticky;
          top: 0;
          z-index: 50;
          background: transparent !important;
          margin-left: 0 !important;
          margin-right: 0 !important;
          padding-left: 0 !important;
          padding-right: 0 !important;
        }
        /* Analytics card wrapper around the two-column chart block */
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"] {
          background: var(--fp-white);
          border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
          padding: 24px 28px 28px 28px;
          margin-top: 20px;
          max-width: min(1320px, 98vw) !important;
          margin-left: auto !important;
          margin-right: auto !important;
          align-items: stretch !important;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"] {
          display: flex !important;
          flex-direction: column !important;
          justify-content: center !important;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"]:nth-child(1) {
          align-items: center !important;
          padding-top: 20px !important;
          padding-bottom: 16px !important;
          overflow: visible !important;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          .vega-embed,
        .element-container:has(.fp-analytics-marker)
          + .element-container
          .vega-embed canvas {
          overflow: visible !important;
        }
        /* Center donut + legend in the left analytics column */
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"]:nth-child(1)
          > div[data-testid="stVerticalBlock"] {
          width: 100% !important;
          align-items: center !important;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"]:nth-child(1)
          .vega-embed {
          margin-left: auto !important;
          margin-right: auto !important;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"]:nth-child(1)
          [data-testid="stMarkdownContainer"] {
          width: 100%;
          text-align: center;
        }
        .element-container:has(.fp-analytics-marker)
          + .element-container
          [data-testid="stHorizontalBlock"]
          [data-testid="column"]:nth-child(2) {
          align-items: stretch !important;
        }
        .fp-nav-crumb {
          font-size: 13px;
          color: var(--fp-neutral-500);
        }
        .fp-nav-crumb a {
          color: var(--fp-neutral-500);
          text-decoration: none;
          transition: color 0.15s ease;
        }
        .fp-nav-crumb a:hover { color: var(--fp-primary-700); }
        .fp-nav-sep { color: var(--fp-neutral-200); margin: 0 6px; }
        .fp-nav-current { color: var(--fp-primary-700); font-weight: 600; }
        .fp-nav-action a {
          font-size: 13px;
          color: var(--fp-neutral-700);
          text-decoration: none;
          font-weight: 600;
          border-radius: 8px;
          padding: 0.35rem 0.55rem;
          margin-right: 0.3rem;
          transition: color 0.15s ease, background 0.15s ease;
        }
        .fp-nav-action a:hover {
          color: var(--fp-primary-700);
          background: var(--fp-primary-50);
        }
        .fp-header {
          display: grid;
          grid-template-columns: 2fr 1fr;
          gap: 24px;
          padding: 40px 20px 32px 20px;
          max-width: min(1320px, 98vw);
          margin: 0 auto;
          align-items: center;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .fp-header-left {
          min-width: 0;
        }
        .fp-header-text { min-width: 0; }
        .fp-h1 {
          font-size: 32px;
          font-weight: 700;
          line-height: 1.2;
          color: var(--fp-primary-900);
          margin: 0;
          letter-spacing: -0.02em;
        }
        .fp-header-sub {
          margin-top: 8px;
          font-size: 16px;
          font-weight: 400;
          color: var(--fp-neutral-500);
          line-height: 1.45;
        }
        .fp-accent-line {
          width: 40px;
          height: 3px;
          background: var(--fp-primary-500);
          border-radius: 2px;
          margin-top: 12px;
        }
        .fp-header-right {
          text-align: right;
          display: flex;
          flex-direction: row;
          flex-wrap: wrap;
          align-items: center;
          justify-content: flex-end;
          gap: 24px;
        }
        .fp-link-icon {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 500;
          color: var(--fp-primary-700);
          text-decoration: none;
          transition: color 0.15s ease, text-decoration 0.15s ease;
        }
        .fp-link-icon:hover {
          color: var(--fp-primary-700);
          text-decoration: underline;
          text-decoration-color: var(--fp-primary-300);
          text-underline-offset: 2px;
        }
        .fp-info-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          padding: 0 20px 8px 20px;
          max-width: min(1320px, 98vw);
          margin: 0 auto;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .fp-info-card {
          background: var(--fp-white);
          border-radius: 12px;
          padding: 24px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          border-left: 4px solid var(--fp-primary-500);
          transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
        }
        .fp-info-card:hover {
          box-shadow: 0 4px 12px rgba(0,0,0,0.08);
          transform: translateY(-2px);
          border-left-color: var(--fp-primary-700);
        }
        .fp-info-card-top {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--fp-neutral-500);
          margin-bottom: 8px;
        }
        .fp-info-card-val {
          font-size: 16px;
          font-weight: 600;
          color: var(--fp-primary-900);
          line-height: 1.35;
          word-break: break-word;
        }
        .fp-info-card-val.fp-mono { font-family: ui-monospace, 'Consolas', monospace; font-weight: 500; }
        .fp-section {
          margin-top: 48px;
          padding: 0 20px;
          max-width: min(1320px, 98vw);
          margin-left: auto;
          margin-right: auto;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .fp-h2 {
          font-size: 22px;
          font-weight: 600;
          line-height: 1.3;
          color: var(--fp-primary-700);
          margin: 0 0 16px 0;
        }
        .fp-toolbar {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 16px;
          margin-bottom: 8px;
        }
        .fp-abdc-caption {
          font-size: 12px;
          color: var(--fp-neutral-500);
          margin: 8px 0 0 0;
        }
        .fp-abdc-caption a {
          color: var(--fp-primary-700);
          text-decoration: none;
          font-weight: 500;
        }
        .fp-abdc-caption a:hover { text-decoration: underline; }
        .fp-analytics-card {
          background: var(--fp-white);
          border-radius: 12px;
          padding: 32px;
          margin-top: 24px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          font-family: 'Inter', system-ui, sans-serif;
        }
        .fp-analytics-inner {
          display: grid;
          grid-template-columns: 5fr 7fr;
          gap: 32px;
          align-items: start;
        }
        .fp-chart-wrap { text-align: center; max-width: 220px; margin: 0 auto; }
        .fp-stats-panel {
          border-left: 1px solid var(--fp-neutral-200);
          padding-left: 28px;
          margin-left: 0;
          max-width: 100%;
        }
        @media (min-width: 900px) {
          .fp-stats-panel {
            padding-top: 8px;
            padding-bottom: 8px;
          }
        }
        .fp-stats-label {
          font-size: 13px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--fp-neutral-500);
          margin-bottom: 10px;
        }
        .fp-stats-body {
          font-size: 17px;
          color: var(--fp-neutral-900);
          line-height: 1.5;
        }
        .fp-stats-body .fp-num {
          color: var(--fp-primary-700);
          font-weight: 700;
          font-size: 1.2em;
          font-variant-numeric: tabular-nums;
        }
        .fp-stats-sub {
          font-size: 14px;
          color: var(--fp-neutral-500);
          margin-top: 8px;
          line-height: 1.45;
        }
        .fp-stats-sub .fp-num {
          font-size: 1.1em;
          font-weight: 700;
        }
        .fp-stats-divider { height: 1px; background: var(--fp-neutral-200); margin: 22px 0; }
        .fp-table-card {
          background: var(--fp-white);
          border-radius: 12px;
          margin-top: 24px;
          max-width: min(1320px, 98vw);
          margin-left: auto;
          margin-right: auto;
          overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          font-family: 'Inter', system-ui, sans-serif;
        }
        table.fp-pubs-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 14px;
          color: var(--fp-neutral-900);
        }
        table.fp-pubs-table thead th {
          background: var(--fp-primary-50);
          color: var(--fp-primary-700);
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          height: 48px;
          padding: 0 16px;
          text-align: left;
          border-bottom: 1px solid var(--fp-neutral-200);
        }
        table.fp-pubs-table thead th.fp-col-abdc,
        table.fp-pubs-table thead th.fp-col-year,
        table.fp-pubs-table thead th.fp-col-scopus { text-align: center; }
        table.fp-pubs-table thead th.fp-col-doi { text-align: right; }
        table.fp-pubs-table tbody td {
          padding: 0 16px;
          height: 52px;
          vertical-align: middle;
          border-bottom: 1px solid var(--fp-neutral-200);
        }
        table.fp-pubs-table tbody tr:nth-child(odd) { background: var(--fp-white); }
        table.fp-pubs-table tbody tr:nth-child(even) { background: var(--fp-neutral-50); }
        table.fp-pubs-table tbody tr {
          transition: background 0.15s ease, box-shadow 0.15s ease;
        }
        table.fp-pubs-table tbody tr:hover {
          background: var(--fp-primary-50) !important;
          box-shadow: inset 3px 0 0 0 var(--fp-primary-500);
        }
        table.fp-pubs-table .fp-col-title { width: 40%; max-width: 0; }
        table.fp-pubs-table .fp-col-type { width: 10%; text-align: center; }
        table.fp-pubs-table .fp-col-source { width: 25%; }
        table.fp-pubs-table .fp-col-abdc { width: 8%; text-align: center; }
        table.fp-pubs-table .fp-col-year { width: 7%; text-align: center; font-variant-numeric: tabular-nums; }
        table.fp-pubs-table .fp-col-scopus { width: 5%; text-align: center; }
        table.fp-pubs-table .fp-col-doi { width: 10%; text-align: right; }
        .fp-type-pill {
          display: inline-block;
          background: var(--fp-primary-100);
          color: var(--fp-primary-700);
          font-size: 12px;
          font-weight: 500;
          padding: 4px 10px;
          border-radius: 20px;
        }
        .fp-scopus-dot {
          display: inline-block;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--fp-primary-500);
          cursor: default;
        }
        .fp-scopus-dot.fp-off {
          background: var(--fp-neutral-200);
        }
        .fp-doi-link {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          color: var(--fp-primary-700);
          font-weight: 500;
          font-size: 13px;
          text-decoration: none;
        }
        .fp-doi-link:hover { text-decoration: underline; text-underline-offset: 2px; }
        @media (max-width: 1199px) {
          .fp-info-grid { grid-template-columns: 1fr 1fr; }
          .fp-analytics-inner { grid-template-columns: 1fr; }
          .fp-table-card { overflow-x: auto; }
          .element-container:has(.fp-analytics-marker)
            + .element-container
            [data-testid="stHorizontalBlock"]
            [data-testid="column"] {
            align-items: center !important;
          }
          .fp-stats-panel {
            border-left: none;
            padding-left: 0;
            border-top: 1px solid var(--fp-neutral-200);
            padding-top: 20px;
            margin-top: 16px;
            max-width: 36rem;
          }
        }
        @media (max-width: 767px) {
          .fp-header { grid-template-columns: 1fr; }
          .fp-header-right { align-items: flex-start; text-align: left; justify-content: flex-start; }
          .fp-info-grid { grid-template-columns: 1fr; }
          .fp-nav-inner { flex-wrap: wrap; height: auto; min-height: 56px; padding: 8px 16px; }
          .element-container:has(nav.fp-nav-sticky) {
            margin-left: -1.25rem;
            margin-right: -1.25rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
          }
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


def format_recent_publications_ro(value: object) -> str:
    """Recent publications cell: year prefix + clamped lines, blue palette."""
    raw = str(value or "")
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    if not parts:
        return "—"
    chunks: list[str] = []
    for p in parts:
        m = re.match(r"^(\d{4})\s*[-–—:]\s*(.+)$", p)
        if not m:
            m = re.match(r"^(\d{4})\s+(.+)$", p)
        if m:
            year, title = m.group(1), m.group(2).strip()
            chunks.append(
                f'<div class="ro-pub-line"><span class="ro-pub-year">{escape(year)}</span> {escape(title)}</div>'
            )
        else:
            chunks.append(f'<div class="ro-pub-line">{escape(p)}</div>')
    return f'<div class="ro-articles">{"".join(chunks)}</div>'


def _research_clear_filters_callback() -> None:
    st.session_state["_ro_clear_now"] = True


def _research_status_pill_class(status_value: str) -> str:
    """Semantic colours for research table status column."""
    s = str(status_value).strip()
    if s == "Faculty sufficiency":
        return "ro-status-pill ro-status-sufficiency"
    if s == "Research committee review":
        return "ro-status-pill ro-status-committee"
    if s == "HOD Consideration":
        return "ro-status-pill ro-status-hod"
    return "ro-status-pill ro-status-default"


def _research_count_active_filters(
    faculty_choice: str,
    campus_filter: list[str],
    campus_options: list[str],
    status_filter: list[str],
    statuses: list[str],
    name_query: str,
    field_filter: list[str],
    research_fields: list[str],
) -> int:
    n = 0
    if faculty_choice != "All":
        n += 1
    if campus_options and set(campus_filter or []) != set(campus_options):
        n += 1
    if statuses and set(status_filter or []) != set(statuses):
        n += 1
    if name_query.strip():
        n += 1
    if research_fields and set(field_filter or []) != set(research_fields):
        n += 1
    return n


def normalize_research_field(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\*+$", "", text).strip()
    return text


def normalize_source_title_for_match(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {col: str(col).strip().lower() for col in columns}
    for candidate in candidates:
        for col, norm in normalized.items():
            if norm == candidate:
                return col
    for candidate in candidates:
        for col, norm in normalized.items():
            if candidate in norm:
                return col
    return None


def _abdc_rank_priority(rank: str) -> int:
    normalized = str(rank or "").strip().upper()
    order = {"A*": 4, "A": 3, "B": 2, "C": 1}
    return order.get(normalized, 0)


def _sheet_with_abdc_data(path: Path) -> str | int:
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        return 0
    try:
        xl = pd.ExcelFile(path)
        for preferred in ("2025 JQL", "2022 JQL", "2019 JQL"):
            if preferred in xl.sheet_names:
                return preferred
        return xl.sheet_names[0] if xl.sheet_names else 0
    except Exception:
        return 0


def _extract_abdc_table(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Find header row containing Journal Title and return normalized table."""
    if df_raw.empty:
        return pd.DataFrame()
    header_row_idx: int | None = None
    for idx, row in df_raw.iterrows():
        values = [str(v).strip().lower() for v in row.tolist() if str(v).strip() and str(v).lower() != "nan"]
        if any("journal title" in v for v in values):
            header_row_idx = int(idx)
            break
    if header_row_idx is None:
        return pd.DataFrame()
    headers = [str(v).strip() for v in df_raw.iloc[header_row_idx].tolist()]
    body = df_raw.iloc[header_row_idx + 1 :].copy()
    body.columns = headers
    body = body.fillna("")
    return body


@st.cache_data(show_spinner=False)
def load_abdc_lookup() -> tuple[dict[str, str], str]:
    """Load ABDC journal list from known local paths and return title->rank mapping."""
    abdc_path: Path | None = None
    for candidate in ABDC_CANDIDATE_PATHS:
        if candidate.exists():
            abdc_path = candidate
            break
    if abdc_path is None:
        return {}, ""

    if abdc_path.suffix.lower() == ".csv":
        abdc_df = pd.read_csv(abdc_path, dtype=str).fillna("")
    else:
        sheet = _sheet_with_abdc_data(abdc_path)
        raw = pd.read_excel(abdc_path, sheet_name=sheet, header=None, dtype=str)
        abdc_df = _extract_abdc_table(raw)
    if abdc_df.empty:
        return {}, str(abdc_path)

    title_col = _pick_column(
        abdc_df.columns.tolist(),
        ("journal title", "title", "journal", "source title", "journal name"),
    )
    rank_col = _pick_column(
        abdc_df.columns.tolist(),
        ("abdc", "abdc rank", "rank", "rating", "ranking"),
    )
    if title_col is None:
        return {}, str(abdc_path)

    lookup: dict[str, str] = {}
    for _, row in abdc_df.iterrows():
        title_norm = normalize_source_title_for_match(row.get(title_col, ""))
        if not title_norm:
            continue
        rank_val = str(row.get(rank_col, "")).strip().upper() if rank_col else ""
        if title_norm not in lookup:
            lookup[title_norm] = rank_val
            continue
        prev_rank = lookup[title_norm]
        if _abdc_rank_priority(rank_val) > _abdc_rank_priority(prev_rank):
            lookup[title_norm] = rank_val

    return lookup, str(abdc_path)


def classify_abdc_status(
    publication_type: object, source_title: object, abdc_lookup: dict[str, str], abdc_available: bool
) -> str:
    pub_type = str(publication_type or "").strip().lower()
    if pub_type != "journal":
        return "N/A"
    if not abdc_available:
        return "ABDC list missing"
    title_key = normalize_source_title_for_match(source_title)
    if not title_key:
        return "Unknown source"
    if title_key in abdc_lookup:
        rank = str(abdc_lookup.get(title_key, "")).strip().upper()
        if rank in {"A*", "A", "B", "C"}:
            return f"ABDC {rank}"
        return "ABDC listed"
    return "Not in ABDC"


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
            "scopus_publications_last_6_years": 0,
            "non_scopus_publications_last_6_years": 0,
            "non_scopus_journal_publications_last_6_years": 0,
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
    numeric_summary_cols = (
        "journal_publications_last_6_years",
        "total_publications_last_6_years",
        "scopus_publications_last_6_years",
        "non_scopus_publications_last_6_years",
        "non_scopus_journal_publications_last_6_years",
    )
    for col in summary_df.columns:
        if col not in stub_df.columns:
            if col in numeric_summary_cols:
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
    for extra_sum_col in (
        "scopus_publications_last_6_years",
        "non_scopus_publications_last_6_years",
        "non_scopus_journal_publications_last_6_years",
    ):
        summary_df[extra_sum_col] = pd.to_numeric(
            summary_df.get(extra_sum_col, 0), errors="coerce"
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
    if "record_source" not in publications_df.columns:
        publications_df["record_source"] = "Scopus"
    else:
        publications_df["record_source"] = publications_df["record_source"].fillna("Scopus").astype(str)
    if "indexed_in_scopus" not in publications_df.columns:
        publications_df["indexed_in_scopus"] = "Yes"
    else:
        publications_df["indexed_in_scopus"] = publications_df["indexed_in_scopus"].fillna("Yes").astype(str)

    return summary_df, publications_df, summary_path, pubs_path


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
    set_internal_query_params()
    st.rerun()


def back_to_research_table() -> None:
    """Leave profile view and return to the publications table (research workspace)."""
    set_internal_query_params(page="research")
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

    sections = None
    teach_hrs = None
    sw = teaching_schoolwide_from_files()
    if sw is not None:
        sections = sw["sections_total"]
        teach_hrs = sw["hours_total"]
        out["teaching_sections_spring"] = sw["sections_spring"]
        out["teaching_sections_fall"] = sw["sections_fall"]
        out["teaching_hours_spring"] = sw["hours_spring"]
        out["teaching_hours_fall"] = sw["hours_fall"]
        out["teaching_faculty_roster"] = sw["faculty_unique"]
    out["total_faculty"] = len(name_keys) if name_keys else None
    out["total_pubs"] = total_pubs_sum
    out["active_researchers"] = len(active_keys) if active_keys else None
    out["teaching_sections"] = sections
    out["teaching_hours"] = teach_hrs
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
    st.markdown(
        "<style>.stApp{background:var(--fp-neutral-50)!important;}</style>",
        unsafe_allow_html=True,
    )
    kpi = load_landing_kpi_stats()
    fac = _fmt_kpi_num(kpi.get("total_faculty"))
    pubs = _fmt_kpi_num(kpi.get("total_pubs"))
    act = _fmt_kpi_num(kpi.get("active_researchers"))
    sections = kpi.get("teaching_sections")
    th = kpi.get("teaching_hours")
    teach_hours = _fmt_kpi_num(th) if th is not None else "—"
    hsp = kpi.get("teaching_hours_spring")
    hfa = kpi.get("teaching_hours_fall")
    ssp = kpi.get("teaching_sections_spring")
    sfa = kpi.get("teaching_sections_fall")
    if sections is not None and th is not None and all(
        x is not None for x in (hsp, hfa, ssp, sfa)
    ):
        teach_sub = (
            f"{int(th):,} h/wk ({int(hsp):,} spring · {int(hfa):,} fall) · "
            f"{int(sections):,} sections ({int(ssp):,} spring · {int(sfa):,} fall) · "
            f"from CSVs · Project/Practicum = {TEACHING_HOURS_PROJECT_PRACTICUM_WEEK} h/wk"
        )
    elif sections is not None and th is not None:
        teach_sub = (
            f"{int(th):,} est. hrs/wk · {int(sections):,} sections · Spring + Fall 2025 "
            f"(Project/Practicum = {TEACHING_HOURS_PROJECT_PRACTICUM_WEEK} h/wk)"
        )
    elif sections is not None:
        teach_sub = f"{int(sections):,} sections (Spring + Fall 2025)"
    else:
        teach_sub = "Teaching CSVs not found"

    home_href = build_internal_href()
    research_href = build_internal_href(page="research")
    teaching_href = build_internal_href(page="teaching")
    analytics_href = build_internal_href(page="analytics")
    logout_href = build_logout_href()

    st.markdown(
        f"""
        <nav class="nexus-nav-shell" aria-label="Primary">
          <div class="nexus-nav">
            <div class="nexus-nav-links">
              <a class="nexus-nav-active" href="{escape(home_href, quote=True)}" target="_self">Dashboard</a>
              <span class="nexus-nav-sep">·</span>
              <a href="{escape(research_href, quote=True)}" target="_self">Publications</a>
              <span class="nexus-nav-sep">·</span>
              <a href="{escape(teaching_href, quote=True)}" target="_self">Teaching load</a>
              <span class="nexus-nav-sep">·</span>
              <a href="{escape(analytics_href, quote=True)}" target="_self">Analytics</a>
            </div>
            <a class="nexus-nav-signout" href="{escape(logout_href, quote=True)}" target="_self">Sign out</a>
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
          <a class="nexus-module" href="{escape(research_href, quote=True)}" target="_self">
            <span class="nexus-module-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/><circle cx="17" cy="7" r="1.2" fill="currentColor" stroke="none"/></svg></span>
            <span class="nexus-module-title">Research Output</span>
            <span class="nexus-module-desc">Publications (Scopus + ORCID), and faculty sufficiency views.</span>
          </a>
          <a class="nexus-module" href="{escape(teaching_href, quote=True)}" target="_self">
            <span class="nexus-module-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6.5v12l8-2.5 8 2.5V6.5"/><path d="M12 4v12"/><path d="M4 6.5L12 4l8 2.5"/></svg></span>
            <span class="nexus-module-title">Teaching load</span>
            <span class="nexus-module-desc">Sections per lecturer, estimated weekly contact hours, and workload chart.</span>
          </a>
          <a class="nexus-module" href="{escape(analytics_href, quote=True)}" target="_self">
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
            <div class="nexus-kpi-sub">Sum · last 6 years (Scopus + ORCID-only, deduplicated)</div>
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


def _read_teaching_roster_csv(path: Path) -> pd.DataFrame | None:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            return df if not df.empty else None
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return None


def _normalize_teaching_roster_df(df: pd.DataFrame, default_semester: str) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    drop_cols = [
        c
        for c in out.columns
        if str(c).startswith("Unnamed")
        and out[c].fillna("").map(lambda x: str(x).strip()).eq("").all()
    ]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    ren: dict[str, str] = {}
    if "Lecturer name" in out.columns:
        ren["Lecturer name"] = "Lecturer"
    if "Course schedule" in out.columns:
        ren["Course schedule"] = "Schedule"
    if ren:
        out = out.rename(columns=ren)
    if "Semester" not in out.columns:
        out = out.copy()
        out["Semester"] = default_semester
    else:
        blank = out["Semester"].fillna("").map(lambda x: str(x).strip()).eq("")
        if blank.any():
            out = out.copy()
            out.loc[blank, "Semester"] = default_semester
    return out


def load_teaching_roster() -> pd.DataFrame | None:
    """Spring 2025 then Fall 2025 BUS rows; None if no roster files load."""
    frames: list[pd.DataFrame] = []
    spring_path = resolve_teaching_data_file(SPRING_2025_TEACHING_CSV)
    if spring_path:
        sdf = _read_teaching_roster_csv(spring_path)
        if sdf is not None:
            frames.append(_normalize_teaching_roster_df(sdf, "Spring 2025"))
    fall_path = resolve_teaching_data_file(FALL_2025_TEACHING_CSV)
    if fall_path:
        fdf = _read_teaching_roster_csv(fall_path)
        if fdf is not None:
            frames.append(_normalize_teaching_roster_df(fdf, "Fall 2025"))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _apply_teaching_lecturer_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Same Lecturer cleanup as the teaching page (strip, not-assigned)."""
    out = df.copy()
    if "Lecturer" not in out.columns:
        return out
    out["Lecturer"] = out["Lecturer"].fillna("").map(lambda x: str(x).strip())
    out.loc[out["Lecturer"].isin(("", "nan")), "Lecturer"] = "(Not assigned)"
    return out


def load_normalized_teaching_roster_file(filename: str, default_semester: str) -> pd.DataFrame | None:
    """Load one roster CSV from disk (canonical source for that semester)."""
    path = resolve_teaching_data_file(filename)
    if not path:
        return None
    raw = _read_teaching_roster_csv(path)
    if raw is None:
        return None
    out = _normalize_teaching_roster_df(raw, default_semester)
    return _apply_teaching_lecturer_labels(out)


def _teaching_language_series(df: pd.DataFrame) -> pd.Series:
    if "Language" in df.columns:
        return df["Language"]
    out = pd.Series([pd.NA] * len(df), index=df.index, dtype=object)
    return out


def _teaching_unique_languages(series: pd.Series) -> str:
    vals = sorted(
        {str(x).strip() for x in series.dropna() if str(x).strip() and str(x).lower() != "nan"}
    )
    return ", ".join(vals) if vals else "—"


def teaching_weekly_hours_for_schedule(schedule: object) -> int:
    """Default section ≈ TEACHING_HOURS_PER_SECTION_WEEK; Project / Practicum count as 1 h/wk."""
    if schedule is None or (isinstance(schedule, float) and pd.isna(schedule)):
        return TEACHING_HOURS_PER_SECTION_WEEK
    s = str(schedule).strip().lower()
    if s in ("project", "practicum"):
        return TEACHING_HOURS_PROJECT_PRACTICUM_WEEK
    return TEACHING_HOURS_PER_SECTION_WEEK


def teaching_roster_weighted_hours_sum(df: pd.DataFrame | None) -> int:
    if df is None or df.empty:
        return 0
    if "Schedule" not in df.columns:
        return int(len(df) * TEACHING_HOURS_PER_SECTION_WEEK)
    return int(df["Schedule"].map(teaching_weekly_hours_for_schedule).sum())


def teaching_schoolwide_from_files() -> dict[str, int] | None:
    """School-wide sections, weighted hours, and faculty count from the two roster CSVs only."""
    spring = load_normalized_teaching_roster_file(SPRING_2025_TEACHING_CSV, "Spring 2025")
    fall = load_normalized_teaching_roster_file(FALL_2025_TEACHING_CSV, "Fall 2025")
    if (spring is None or spring.empty) and (fall is None or fall.empty):
        return None

    ss = len(spring) if spring is not None and not spring.empty else 0
    sf = len(fall) if fall is not None and not fall.empty else 0
    hs = teaching_roster_weighted_hours_sum(spring)
    hf = teaching_roster_weighted_hours_sum(fall)

    lec_keys: set[str] = set()
    for d in (spring, fall):
        if d is None or d.empty or "Lecturer" not in d.columns:
            continue
        for v in d["Lecturer"].tolist():
            t = str(v).strip()
            if t and t.lower() != "nan":
                lec_keys.add(t)

    return {
        "sections_spring": ss,
        "sections_fall": sf,
        "sections_total": ss + sf,
        "hours_spring": hs,
        "hours_fall": hf,
        "hours_total": hs + hf,
        "faculty_unique": len(lec_keys),
    }


def _weighted_hours_subset(sub: pd.DataFrame) -> int:
    if sub is None or sub.empty:
        return 0
    if "Schedule" in sub.columns:
        return int(sub["Schedule"].map(teaching_weekly_hours_for_schedule).sum())
    return int(len(sub) * TEACHING_HOURS_PER_SECTION_WEEK)


def teaching_fall_delta_vs_spring_note(spring_h: int, fall_h: int) -> str:
    """Small caption under Fall hours: change in fall vs spring (fall − spring), same person."""
    if spring_h <= 0 and fall_h <= 0:
        return ""
    if spring_h <= 0 and fall_h > 0:
        return "no spring baseline"
    delta = int(fall_h) - int(spring_h)
    if delta > 0:
        return f"+{delta} vs spring"
    if delta == 0:
        return "0 vs spring"
    return f"{delta} vs spring"


def _lecturer_weighted_hours_map(roster: pd.DataFrame | None) -> dict[str, int]:
    """Lecturer name -> weighted weekly hours for rows that appear only in this file."""
    if roster is None or roster.empty or "Lecturer" not in roster.columns:
        return {}
    out: dict[str, int] = {}
    for lec, g in roster.groupby("Lecturer", sort=False):
        key = str(lec).strip()
        out[key] = _weighted_hours_subset(g)
    return out


def build_teaching_lecturer_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per lecturer: section count from combined roster; Spring/Fall hours from each CSV file."""
    spring_only = load_normalized_teaching_roster_file(SPRING_2025_TEACHING_CSV, "Spring 2025")
    fall_only = load_normalized_teaching_roster_file(FALL_2025_TEACHING_CSV, "Fall 2025")
    spring_hrs = _lecturer_weighted_hours_map(spring_only)
    fall_hrs = _lecturer_weighted_hours_map(fall_only)

    rows: list[dict[str, object]] = []
    for lec, g in df.groupby("Lecturer", sort=False):
        n = len(g)
        lec_key = str(lec).strip()
        h_sp = int(spring_hrs.get(lec_key, 0))
        h_fa = int(fall_hrs.get(lec_key, 0))
        total = h_sp + h_fa
        rows.append(
            {
                "Lecturer": lec,
                "Sections": n,
                "Hours Spring 2025": h_sp,
                "Hours Fall 2025": h_fa,
                "Est. hours / week": total,
                "Languages": _teaching_unique_languages(_teaching_language_series(g)),
            }
        )
    return pd.DataFrame(rows)


def schedule_to_delivery_mode(val: object) -> str:
    """Map roster Schedule cell to a simple delivery label (no times)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return "—"
    sl = s.lower()
    if "dist" in sl:
        return "Distance learning"
    if "not sched" in sl:
        return "Not scheduled"
    if re.match(r"^(Mo|Tu|We|Th|Fr|Sa|Su)\b", s, re.IGNORECASE):
        return "On campus (scheduled)"
    return "Other"


def _teaching_summary_display_names() -> dict[str, str]:
    return {
        "Lecturer": "Faculty",
        "Sections": "Classes",
        "Hours Spring 2025": "Spring 2025 (h/wk)",
        "Hours Fall 2025": "Fall 2025 (h/wk)",
        "Est. hours / week": "Total h/wk",
        "Languages": "Languages",
    }


TEACH_SORT_OPTIONS: tuple[str, ...] = (
    "Name (A-Z)",
    "Name (Z-A)",
    "Classes (most first)",
    "Classes (fewest first)",
    "Hours (most first)",
    "Hours (fewest first)",
)


def teaching_sub_matches_course(sub: pd.DataFrame, q: str) -> bool:
    qn = q.strip().lower()
    if not qn:
        return False
    for _, r in sub.iterrows():
        cid = str(r.get("Course ID", "")).lower()
        tit = str(r.get("Title", "")).lower()
        if qn in cid or qn in tit:
            return True
    return False


def teaching_filter_faculty_names(summary: pd.DataFrame, df: pd.DataFrame, q: str) -> list[str]:
    all_names = sorted(summary["Lecturer"].unique().tolist(), key=str)
    qn = (q or "").strip().lower()
    if not qn:
        return all_names
    out: list[str] = []
    for n in all_names:
        if qn in str(n).lower():
            out.append(n)
            continue
        sub = df.loc[df["Lecturer"] == n]
        if teaching_sub_matches_course(sub, qn):
            out.append(n)
    return out


def teaching_sort_faculty_names(names: list[str], summary: pd.DataFrame, sort_mode: str) -> list[str]:
    def sn(n: str) -> str:
        return str(n).lower()

    if sort_mode == "Name (Z-A)":
        return sorted(names, key=sn, reverse=True)
    if sort_mode == "Name (A-Z)":
        return sorted(names, key=sn)
    if sort_mode == "Classes (most first)":
        return sorted(
            names,
            key=lambda n: (-int(summary.loc[summary["Lecturer"] == n, "Sections"].iloc[0]), sn(n)),
        )
    if sort_mode == "Classes (fewest first)":
        return sorted(
            names,
            key=lambda n: (int(summary.loc[summary["Lecturer"] == n, "Sections"].iloc[0]), sn(n)),
        )
    if sort_mode == "Hours (most first)":
        return sorted(
            names,
            key=lambda n: (-int(summary.loc[summary["Lecturer"] == n, "Est. hours / week"].iloc[0]), sn(n)),
        )
    if sort_mode == "Hours (fewest first)":
        return sorted(
            names,
            key=lambda n: (int(summary.loc[summary["Lecturer"] == n, "Est. hours / week"].iloc[0]), sn(n)),
        )
    return sorted(names, key=sn)


def teaching_load_tier_class(hours: int, q33: float, q66: float) -> str:
    if hours <= q33:
        return "teach-load-low"
    if hours <= q66:
        return "teach-load-mid"
    return "teach-load-high"


def teaching_faculty_table_html(
    names: list[str],
    summary: pd.DataFrame,
    df: pd.DataFrame,
    strip_stats: tuple[int, float, int] | None = None,
) -> str:
    """Div-based grid + <details> rows (no <table>) so headers and cells share one layout."""
    hrs_series = summary["Est. hours / week"].astype(float)
    q33 = float(hrs_series.quantile(0.33)) if len(hrs_series) else 0.0
    q66 = float(hrs_series.quantile(0.66)) if len(hrs_series) else 0.0

    parts: list[str] = ['<div class="teach-dash-wrap">']
    if strip_stats is not None:
        nf_s, avg_s, mx_s = strip_stats
        parts.append(
            '<div class="teach-strip">'
            f"<span><strong>{nf_s}</strong> faculty in this view</span>"
            f"<span>Avg total <strong>{avg_s:.1f}</strong> h/wk (spring+fall)</span>"
            f"<span>Max total <strong>{mx_s}</strong> h/wk</span>"
            "</div>"
        )
    parts.extend(
        [
        '<div class="teach-faculty-shell" role="table" aria-label="Faculty teaching">',
        '<div class="teach-faculty-cols teach-faculty-header" role="row">',
        '<div role="columnheader">Name</div>',
        '<div role="columnheader">Classes</div>',
        '<div role="columnheader">Spring 2025<br/><span style="font-weight:500;text-transform:none;letter-spacing:0.02em;">(h/wk est.)</span></div>',
        '<div role="columnheader">Fall 2025<br/><span style="font-weight:500;text-transform:none;letter-spacing:0.02em;">(h/wk est. · Δ vs spring)</span></div>',
        '<div role="columnheader">Expand</div>',
        "</div>",
        '<div class="teach-faculty-body" role="rowgroup">',
        ]
    )

    for name in names:
        row = summary.loc[summary["Lecturer"] == name].iloc[0]
        n_cls = int(row["Sections"])
        hrs = int(row["Est. hours / week"])
        h_sp = int(row["Hours Spring 2025"]) if "Hours Spring 2025" in row.index else 0
        h_fa = int(row["Hours Fall 2025"]) if "Hours Fall 2025" in row.index else 0
        tier = teaching_load_tier_class(hrs, q33, q66)

        nm_esc = escape(str(name))
        n_esc = escape(str(n_cls))
        fall_delta_note = teaching_fall_delta_vs_spring_note(h_sp, h_fa)

        sub = df.loc[df["Lecturer"] == name].copy()
        if "Schedule" in sub.columns:
            deliv = sub["Schedule"].map(schedule_to_delivery_mode).reset_index(drop=True)
        else:
            deliv = pd.Series(["—"] * len(sub), dtype=object)

        parts.append(f'<details class="teach-faccard {tier}" role="row">')
        parts.append('<summary class="teach-faculty-cols">')
        parts.append(
            f'<span class="teach-col-name" title="{escape(str(name), quote=True)}">{nm_esc}</span>'
        )
        parts.append(f'<span class="teach-col-num">{n_esc}</span>')
        parts.append('<span class="teach-season-cell teach-season-spring">')
        parts.append(f'<span class="teach-hours-val">{escape(str(h_sp))}</span>')
        parts.append("</span>")
        parts.append('<span class="teach-season-cell teach-season-fall">')
        parts.append(f'<span class="teach-hours-val">{escape(str(h_fa))}</span>')
        if fall_delta_note:
            parts.append(f'<span class="teach-fall-delta-note">{escape(fall_delta_note)}</span>')
        parts.append("</span>")
        parts.append('<span class="teach-col-toggle">')
        parts.append('<span class="teach-toggle-hint-closed">Expand</span>')
        parts.append('<span class="teach-toggle-hint-open">Collapse</span>')
        parts.append("</span></summary>")
        parts.append('<div class="teach-nested">')
        if sub.empty:
            parts.append('<div class="teach-nested-line">No assignments</div>')
        else:
            for idx, (_, r) in enumerate(sub.iterrows()):
                code = escape(str(r.get("Course ID", "")).strip())
                title = escape(str(r.get("Title", "")).strip())
                sec_raw = str(r.get("Section", "")).strip()
                if sec_raw.lower().startswith("section"):
                    sec_disp = escape(sec_raw)
                else:
                    sec_disp = escape(f"Section {sec_raw}" if sec_raw else "Section —")
                d = escape(str(deliv.iloc[idx]) if idx < len(deliv) else "—")
                sem_bit = ""
                if "Semester" in sub.columns:
                    sr = str(r.get("Semester", "")).strip()
                    if sr and sr.lower() != "nan":
                        sem_bit = f" | {escape(sr)}"
                parts.append(f'<div class="teach-nested-line">{code} | {title} | {sec_disp} | {d}{sem_bit}</div>')
        parts.append("</div></details>")

    parts.append("</div></div></div>")
    return "".join(parts)


def teaching_workload_threshold_counts(hours: pd.Series) -> dict[str, int]:
    """How many faculty strictly exceed common hour thresholds (cumulative-style counts)."""
    h = hours.astype(int)
    return {
        "total": int(len(h)),
        "gt6": int((h > 6).sum()),
        "gt12": int((h > 12).sum()),
        "gt20": int((h > 20).sum()),
        "gt30": int((h > 30).sum()),
    }


def render_teaching_analytics() -> None:
    st.markdown(
        "<style>.stApp{background:var(--fp-neutral-50)!important;}</style>",
        unsafe_allow_html=True,
    )
    home_href = build_internal_href()
    logout_href = build_logout_href()
    st.markdown(
        f"""
        <nav class="fp-nav fp-nav-inner fp-nav-sticky ro-research-nav" aria-label="Breadcrumb">
          <div class="fp-nav-crumb">
            <a href="{escape(home_href, quote=True)}" target="_self">Home</a>
            <span class="fp-nav-sep">/</span>
            <span class="fp-nav-current">Teaching load</span>
          </div>
          <div class="fp-nav-action"><a href="{escape(logout_href, quote=True)}" target="_self">Sign out</a></div>
        </nav>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <header class="ro-page-header">
          <h1>Teaching load</h1>
          <div class="ro-accent-bar" aria-hidden="true"></div>
        </header>
        """,
        unsafe_allow_html=True,
    )

    cdf = load_teaching_roster()
    if cdf is None:
        st.warning(
            "We could not find the **Spring** or **Fall** 2025 teaching roster CSVs. Add both files next to "
            "**app.py** or one folder above (OneDrive layout)."
        )
        st.code(teaching_roster_paths_hint(), language=None)
        return
    if cdf.empty:
        st.info("The teaching roster has no rows yet.")
        return

    required = {"Lecturer", "Course ID", "Title", "Section", "Semester", "Schedule"}
    if not required.issubset(cdf.columns):
        st.error("The course file is missing columns we need. Please check the header row.")
        st.write("Found columns:", ", ".join(map(str, cdf.columns)))
        return

    df = _apply_teaching_lecturer_labels(cdf.copy())

    summary = build_teaching_lecturer_summary(df)

    sw_totals = teaching_schoolwide_from_files()
    if sw_totals is not None:
        n_faculty = int(sw_totals["faculty_unique"])
        total_sections = int(sw_totals["sections_total"])
        total_hours = int(sw_totals["hours_total"])
        sec_sp, sec_fa = int(sw_totals["sections_spring"]), int(sw_totals["sections_fall"])
        hrs_sp, hrs_fa = int(sw_totals["hours_spring"]), int(sw_totals["hours_fall"])
    else:
        n_faculty = len(summary)
        total_sections = int(summary["Sections"].sum())
        total_hours = int(summary["Est. hours / week"].sum())
        sec_sp = sec_fa = hrs_sp = hrs_fa = None
    hrs_wk = summary["Est. hours / week"].astype(int)
    thr = teaching_workload_threshold_counts(hrs_wk)
    n_tot = thr["total"]
    pct_over6 = 100.0 * thr["gt6"] / n_tot if n_tot else 0.0
    pct_over12 = 100.0 * thr["gt12"] / n_tot if n_tot else 0.0
    pct_over20 = 100.0 * thr["gt20"] / n_tot if n_tot else 0.0

    with st.container(border=True):
        st.subheader("School-wide totals")
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Faculty in this list",
            f"{n_faculty:,}",
            help=(
                "Distinct names in the **Lecturer** column across both CSVs (after the same cleanup as the table). "
                "Someone in only one semester still counts once."
            ),
        )
        c2.metric(
            "Class sections in the files",
            f"{total_sections:,}",
            help=(
                "Row counts: spring CSV + fall CSV (one row = one course section in that semester). "
                + (
                    f"Breakdown: {sec_sp:,} spring + {sec_fa:,} fall."
                    if sec_sp is not None
                    else "Spring + Fall 2025."
                )
            ),
        )
        c3.metric(
            "In-class hours per week (whole school, about)",
            f"{total_hours:,}",
            help=(
                f"Weighted sum from both CSVs: {TEACHING_HOURS_PER_SECTION_WEEK} h/wk per section by default, "
                f"Project/Practicum = {TEACHING_HOURS_PROJECT_PRACTICUM_WEEK} h/wk. "
                + (
                    f"Breakdown: {hrs_sp:,} spring + {hrs_fa:,} fall."
                    if hrs_sp is not None
                    else "Spring + Fall rows summed."
                )
            ),
        )
        p1, p2, p3 = st.columns(3)
        p1.metric(
            "% Faculty over 6 hrs/wk (about)",
            f"{pct_over6:.0f}%",
            help=f"{thr['gt6']:,} of {n_tot:,} faculty with estimated weekly in-class hours strictly above 6.",
        )
        p2.metric(
            "% Faculty over 12 hrs/wk (about)",
            f"{pct_over12:.0f}%",
            help=f"{thr['gt12']:,} of {n_tot:,} faculty with estimated weekly in-class hours strictly above 12.",
        )
        p3.metric(
            "% Faculty over 20 hrs/wk (about)",
            f"{pct_over20:.0f}%",
            help=f"{thr['gt20']:,} of {n_tot:,} faculty with estimated weekly in-class hours strictly above 20.",
        )

    st.divider()

    with st.container(border=True):
        st.subheader("Faculty teaching")
        fc1, fc2 = st.columns([1.4, 1])
        with fc1:
            filt = st.text_input(
                "Filter by name",
                placeholder="Name, course code, or course title…",
                key="teach_filter_by_name",
            )
        with fc2:
            sort_mode = st.selectbox("Sort by", TEACH_SORT_OPTIONS, index=0, key="teach_sort_mode")

        names = teaching_filter_faculty_names(summary, df, filt)
        names = teaching_sort_faculty_names(names, summary, sort_mode)

        if not names:
            st.caption("No faculty match this filter.")
        else:
            hrs_list = [int(summary.loc[summary["Lecturer"] == n, "Est. hours / week"].iloc[0]) for n in names]
            nf = len(names)
            avg_h = sum(hrs_list) / nf if nf else 0.0
            mx_h = max(hrs_list)
            st.markdown(
                '<div class="ro-table-shell" style="margin-top:8px;">'
                + teaching_faculty_table_html(names, summary, df, strip_stats=(nf, avg_h, mx_h))
                + "</div>",
                unsafe_allow_html=True,
            )


def render_analytics_placeholder() -> None:
    h1, _ = st.columns([0.14, 0.86])
    with h1:
        if st.button("Home", key="nav_home_analytics"):
            go_home()
    st.title("Institutional Analytics")
    st.info("This workspace is coming soon. School-wide summaries and leadership dashboards will live here.")


def render_master_table() -> None:
    st.markdown(
        "<style>.stApp{background:var(--fp-neutral-50)!important;}</style>",
        unsafe_allow_html=True,
    )
    home_href = build_internal_href()
    logout_href = build_logout_href()
    st.markdown(
        f"""
        <nav class="fp-nav fp-nav-inner fp-nav-sticky ro-research-nav" aria-label="Breadcrumb">
          <div class="fp-nav-crumb">
            <a href="{escape(home_href, quote=True)}" target="_self">Home</a>
            <span class="fp-nav-sep">/</span>
            <span class="fp-nav-current">Research Output</span>
          </div>
          <div class="fp-nav-action"><a href="{escape(logout_href, quote=True)}" target="_self">Sign out</a></div>
        </nav>
        """,
        unsafe_allow_html=True,
    )

    clock_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M12 7v5l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
    )
    st.markdown(
        f"""
        <header class="ro-page-header">
          <h1>Research Output</h1>
          <div class="ro-caption-refresh">{clock_svg}<span>Data refreshed every Monday</span></div>
          <div class="ro-accent-bar" aria-hidden="true"></div>
        </header>
        """,
        unsafe_allow_html=True,
    )

    preferred_status_order = ["Faculty sufficiency", "HOD Consideration", "Research committee review"]
    faculty_options = ("All", "Full-time", "Part-time")
    if "dashboard_faculty_cohort" not in st.session_state:
        st.session_state.dashboard_faculty_cohort = "All"
    elif st.session_state.dashboard_faculty_cohort not in faculty_options:
        st.session_state.dashboard_faculty_cohort = "All"

    prior_active = int(st.session_state.get("ro_active_filters", 0) or 0)
    expander_title = f"Filters ({prior_active} active)" if prior_active else "Filters"

    with st.expander(expander_title, expanded=False):
        clear_pending = st.session_state.pop("_ro_clear_now", False)
        if clear_pending:
            st.session_state["dashboard_faculty_cohort"] = "All"

        st.markdown(
            '<span style="font-size:11px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:var(--fp-neutral-500);display:block;margin-bottom:4px;">Faculty</span>',
            unsafe_allow_html=True,
        )
        faculty_choice = st.radio(
            "Faculty cohort",
            list(faculty_options),
            horizontal=True,
            key="dashboard_faculty_cohort",
            label_visibility="collapsed",
        )

        if faculty_choice == "Part-time":
            summary_df, _, _, _ = load_data("part")
            summary_df = summary_df.copy()
            summary_df["_cohort_key"] = "part"
        elif faculty_choice == "Full-time":
            summary_df, _, _, _ = load_data("full")
            summary_df = summary_df.copy()
            summary_df["_cohort_key"] = "full"
        else:
            full_summary, _, _, _ = load_data("full")
            part_summary, _, _, _ = load_data("part")
            full_summary = full_summary.copy()
            part_summary = part_summary.copy()
            full_summary["_cohort_key"] = "full"
            part_summary["_cohort_key"] = "part"
            summary_df = pd.concat([full_summary, part_summary], ignore_index=True)

        present_statuses = [s for s in preferred_status_order if s in set(summary_df["status"].dropna().tolist())]
        other_statuses = sorted([s for s in summary_df["status"].dropna().unique().tolist() if s not in present_statuses])
        statuses = present_statuses + other_statuses
        research_fields = sorted([f for f in summary_df["research_field"].dropna().unique().tolist() if f.strip()])
        campus_preferred = ["UNIC Nicosia", "UNIC Athens", "Not specified"]
        campus_present = summary_df["_campus_filter"].dropna().unique().tolist()
        campus_options = [c for c in campus_preferred if c in campus_present] + sorted(
            c for c in campus_present if c not in campus_preferred
        )

        grouped_fields: list[tuple[str, list[str]]] = [
            ("Accounting / Economics / Finance", ["Accounting", "Economics", "Finance"]),
            ("Digital Innovation", ["Blockchain"]),
            ("Management", ["Management", "Marketing", "Information Systems"]),
        ]
        known_fields = {item for _, group_items in grouped_fields for item in group_items}
        extra_fields = sorted([field for field in research_fields if field not in known_fields])
        if extra_fields:
            grouped_fields.append(("Other", extra_fields))

        if clear_pending:
            st.session_state["ro_campus_filter"] = list(campus_options)
            st.session_state["ro_status_filter"] = list(statuses)
            st.session_state["ro_name_query"] = ""
            for field in research_fields:
                fk = re.sub(r"\W+", "_", field.lower()).strip("_")
                st.session_state[f"field_{fk}"] = True
            for group_name, group_items in grouped_fields:
                available_items = [item for item in group_items if item in research_fields]
                if len(available_items) > 1:
                    key_suffix = re.sub(r"\W+", "_", group_name.lower()).strip("_")
                    st.session_state[f"field_group_all_{key_suffix}"] = True

        if "ro_campus_filter" not in st.session_state:
            st.session_state["ro_campus_filter"] = list(campus_options)
        if "ro_status_filter" not in st.session_state:
            st.session_state["ro_status_filter"] = list(statuses)

        ent_col, stat_col = st.columns(2)
        _lbl = '<span style="font-size:11px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:var(--fp-neutral-500);display:block;margin-bottom:4px;">{}</span>'
        with ent_col:
            st.markdown(_lbl.format("UNIC Entity"), unsafe_allow_html=True)
            campus_filter = st.multiselect(
                "UNIC Entity",
                options=campus_options,
                key="ro_campus_filter",
                placeholder="Select campus...",
                label_visibility="collapsed",
            )
        with stat_col:
            st.markdown(_lbl.format("Status"), unsafe_allow_html=True)
            status_filter = st.multiselect(
                "Status",
                options=statuses,
                key="ro_status_filter",
                placeholder="Select status...",
                label_visibility="collapsed",
            )

        st.markdown('<div class="ro-field-section-label">Research Field</div>', unsafe_allow_html=True)

        field_selection: dict[str, bool] = {}
        group_cols = st.columns(len(grouped_fields))
        for idx, (group_name, group_items) in enumerate(grouped_fields):
            available_items = [item for item in group_items if item in research_fields]
            if not available_items:
                continue
            key_suffix = re.sub(r"\W+", "_", group_name.lower()).strip("_")
            with group_cols[idx]:
                st.markdown(
                    f'<p class="ro-field-group-title">{escape(group_name)}</p>',
                    unsafe_allow_html=True,
                )
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

        _, clear_col = st.columns([3, 1])
        with clear_col:
            st.button(
                "✕ Clear all filters",
                key="ro_clear_all",
                on_click=_research_clear_filters_callback,
                type="secondary",
            )

    name_query = str(st.session_state.get("ro_name_query", ""))

    filtered = summary_df.copy()
    if name_query:
        filtered = filtered[filtered["name"].str.contains(name_query, case=False, na=False)]
    if campus_filter:
        filtered = filtered[filtered["_campus_filter"].isin(campus_filter)]
    filtered = filtered[filtered["status"].isin(status_filter)]
    filtered = filtered[filtered["research_field"].isin(field_filter)]
    filtered = filtered[
        ~filtered["name"].str.contains(r"\bria\s+(morphidou|morphitou)\b", case=False, na=False, regex=True)
    ]
    filtered = filtered.sort_values(by=["name"], ascending=[True])

    st.session_state["ro_active_filters"] = _research_count_active_filters(
        faculty_choice,
        list(campus_filter),
        campus_options,
        list(status_filter),
        statuses,
        str(name_query),
        field_filter,
        research_fields,
    )

    n_people = len(filtered)
    n_suff = int((filtered["status"] == "Faculty sufficiency").sum())
    n_tot_pub = int(filtered["total_publications_last_6_years"].sum())
    n_j_pub = int(filtered["journal_publications_last_6_years"].sum())

    ico_users = '<span class="ro-kpi-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="9" cy="7" r="4" stroke="currentColor" stroke-width="1.6"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></span>'
    ico_shield = '<span class="ro-kpi-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg></span>'
    ico_docs = '<span class="ro-kpi-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" stroke="currentColor" stroke-width="1.6"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></span>'
    ico_book = '<span class="ro-kpi-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" stroke="currentColor" stroke-width="1.6"/><path d="M8 7h8M8 11h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></span>'

    st.markdown(
        f"""
        <div class="ro-kpi-grid">
          <div class="ro-kpi-card"><div class="ro-kpi-top">{ico_users}<span>People Visible</span></div><div class="ro-kpi-val">{n_people:,}</div></div>
          <div class="ro-kpi-card"><div class="ro-kpi-top">{ico_shield}<span>Faculty Sufficiency</span></div><div class="ro-kpi-val">{n_suff:,}</div></div>
          <div class="ro-kpi-card"><div class="ro-kpi-top">{ico_docs}<span>Total Publications Visible</span></div><div class="ro-kpi-val">{n_tot_pub:,}</div></div>
          <div class="ro-kpi-card"><div class="ro-kpi-top">{ico_book}<span>Journal Publications Visible</span></div><div class="ro-kpi-val">{n_j_pub:,}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    export_summary = filtered.drop(columns=["_campus_filter"], errors="ignore")
    csv_bytes = export_summary.to_csv(index=False).encode("utf-8")

    search_col, dl_col = st.columns([2, 1], vertical_alignment="bottom")
    with search_col:
        st.text_input(
            "Search by faculty name",
            placeholder="Search by faculty name...",
            key="ro_name_query",
        )
    with dl_col:
        st.download_button(
            label="⭳ Download CSV",
            data=csv_bytes,
            file_name="summary_filtered.csv",
            mime="text/csv",
            key="ro_dl_inline",
            use_container_width=True,
        )

    rows_html: list[str] = []
    for _, row in filtered.iterrows():
        status_value = str(row["status"])
        orcid_cell = str(row["orcid"]).strip()
        orcid_for_url = _normalize_orcid_from_cell(orcid_cell) or orcid_cell
        ue = str(row.get("unic_entity", "")).strip()
        entity_text = escape(ue) if ue else "—"
        row_cohort_key = str(row.get("_cohort_key", "full")).strip() or "full"
        profile_href = build_internal_href(
            page="research",
            cohort=row_cohort_key,
            orcid=orcid_for_url,
        )
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td style=\"width:15%;\"><a class=\"ro-name-link\" href=\"{escape(profile_href, quote=True)}\" target=\"_self\">{escape(str(row['name']))}</a></td>",
                    f"<td style=\"width:10%;\"><span class=\"ro-entity-pill\">{entity_text}</span></td>",
                    f"<td style=\"width:10%;\">{escape(str(row['research_field'])) or '—'}</td>",
                    f"<td style=\"width:30%;\">{format_recent_publications_ro(row['recent_3_articles'])}</td>",
                    f"<td style=\"width:8%;text-align:center;font-weight:600;color:var(--fp-primary-900);\">{int(row['total_publications_last_6_years']):,}</td>",
                    f"<td style=\"width:8%;text-align:center;font-weight:600;color:var(--fp-primary-900);\">{int(row['journal_publications_last_6_years']):,}</td>",
                    f"<td style=\"width:14%;\"><span class=\"{_research_status_pill_class(status_value)}\">{escape(status_value)}</span></td>",
                    "</tr>",
                ]
            )
        )

    empty_body = ""
    if not rows_html:
        empty_body = """
          <tr><td colspan="7">
            <div class="ro-empty">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.5"/><path d="m20 20-3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
              <div>No results match your filters</div>
            </div>
          </td></tr>
        """
    else:
        empty_body = "".join(rows_html)

    table_html = f"""
    <div class="ro-table-shell">
      <div class="ro-table-card">
        <table class="ro-table">
          <colgroup>
            <col style="width:15%" /><col style="width:10%" /><col style="width:10%" /><col style="width:30%" />
            <col style="width:8%" /><col style="width:8%" /><col style="width:14%" />
          </colgroup>
          <thead>
            <tr>
              <th>Name</th>
              <th>UNIC Entity</th>
              <th>Research Field</th>
              <th>Recent 3 Publications</th>
              <th class="ro-th-center">Total<span class="ro-th-sub">(6 Years)</span></th>
              <th class="ro-th-center">PRJ<span class="ro-th-sub">(6 Years)</span></th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {empty_body}
          </tbody>
        </table>
      </div>
    </div>
    """

    st.markdown(table_html, unsafe_allow_html=True)
    if filtered.empty:
        _, ce, _ = st.columns([1, 1, 1])
        with ce:
            st.button(
                "Clear all filters",
                key="ro_empty_clear",
                on_click=_research_clear_filters_callback,
            )


def _profile_chart_bucket(pub_type: object) -> str:
    s = str(pub_type).strip().lower()
    if s == "journal":
        return "Journal"
    if s == "conference":
        return "Conference"
    if s in ("book", "book series"):
        return "Book"
    return "Other"


def render_profile_page(
    summary_df: pd.DataFrame,
    publications_df: pd.DataFrame,
    orcid: str,
    cohort: str,
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
    person_pubs = publications_df[publications_df["orcid"].map(_orcid_row_key) == orcid_key].copy()
    person_pubs = person_pubs.sort_values(by=["year", "cover_date"], ascending=[False, False])
    abdc_lookup, abdc_path = load_abdc_lookup()
    abdc_available = bool(abdc_lookup)
    if not person_pubs.empty:
        person_pubs["abdc_status"] = person_pubs.apply(
            lambda row: classify_abdc_status(
                row.get("publication_type", ""),
                row.get("source_title", ""),
                abdc_lookup,
                abdc_available,
            ),
            axis=1,
        )
    person_pubs_all = person_pubs.copy()

    st.markdown(
        "<style>.stApp{background:var(--fp-neutral-50)!important;}</style>",
        unsafe_allow_html=True,
    )

    cohort_q = str(cohort).strip().lower()
    if cohort_q not in ("full", "part"):
        cohort_q = "full"
    home_href = build_internal_href()
    research_href = build_internal_href(page="research", cohort=cohort_q)
    logout_href = build_logout_href()

    st.markdown(
        f"""
        <nav class="fp-nav fp-nav-inner fp-nav-sticky" aria-label="Breadcrumb">
          <div class="fp-nav-crumb">
            <a href="{escape(home_href, quote=True)}" target="_self">Home</a>
            <span class="fp-nav-sep">/</span>
            <a href="{escape(research_href, quote=True)}" target="_self">Research output</a>
            <span class="fp-nav-sep">/</span>
            <span class="fp-nav-current">Faculty profile</span>
          </div>
          <div class="fp-nav-action"><a href="{escape(logout_href, quote=True)}" target="_self">Sign out</a></div>
        </nav>
        """,
        unsafe_allow_html=True,
    )

    role_text = escape(str(person.get("rank", "")).strip() or "—")
    dept_text = escape(str(person.get("department", "")).strip() or "—")
    institution_text = escape(str(person.get("unic_entity", "")).strip() or "—")
    research_field_text = escape(str(person.get("research_field", "")).strip() or "—")
    contact_text = escape(str(person.get("telephone", "")).strip() or "—")
    email_text = str(person.get("email", "")).strip()
    email_href = f"mailto:{email_text}" if email_text else "#"
    orcid_value = _normalize_orcid_from_cell(person.get("orcid", "")) or str(person.get("orcid", "")).strip()
    orcid_href = f"https://orcid.org/{orcid_value}" if orcid_value else "#"
    display_name = escape(str(person.get("name", "")))

    ico_rf = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="#64B5F6" stroke-width="1.6" stroke-linecap="round"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="#64B5F6" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 7h8M8 11h8" stroke="#64B5F6" stroke-width="1.6" stroke-linecap="round"/></svg>"""
    ico_rank = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M2 10 12 5l10 5-10 5L2 10Z" stroke="#64B5F6" stroke-width="1.6" stroke-linejoin="round"/><path d="M22 10v1l-10 5L2 11v-1" stroke="#64B5F6" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11.5V17c0 1.7 2.2 3 6 3s6-1.3 6-3v-5.5" stroke="#64B5F6" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
    ico_inst = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6" stroke="#64B5F6" stroke-width="1.6" stroke-linejoin="round"/></svg>"""
    ico_contact = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M22 16.92V19a2 2 0 0 1-2.18 2A19.86 19.86 0 0 1 3 5.18 2 2 0 0 1 5 3h2.09a2 2 0 0 1 2 1.72c.12.81.3 1.6.54 2.36a2 2 0 0 1-.45 2.11L8.09 10.91a16 16 0 0 0 6 6l1.72-1.72a2 2 0 0 1 2.11-.45c.76.24 1.55.42 2.36.54A2 2 0 0 1 22 16.92Z" stroke="#64B5F6" stroke-width="1.6" stroke-linejoin="round"/></svg>"""
    svg_orcid = """<svg width="16" height="16" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="#1565C0"/><text x="12" y="15" text-anchor="middle" fill="#fff" font-size="9" font-weight="700" font-family="Inter, sans-serif">iD</text></svg>"""
    svg_mail = """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" stroke="#1565C0" stroke-width="1.6"/><path d="m3 7 9 6 9-6" stroke="#1565C0" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
    svg_ext = """<svg width="11" height="11" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M15 3h6v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M10 14 21 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>"""

    st.markdown(
        f"""
        <header class="fp-header">
          <div class="fp-header-left">
            <div class="fp-header-text">
              <h1 class="fp-h1">{display_name}</h1>
              <div class="fp-header-sub">{role_text}, {dept_text}</div>
            </div>
          </div>
          <div class="fp-header-right">
            <a class="fp-link-icon" href="{escape(orcid_href, quote=True)}" target="_self" rel="noopener noreferrer">
              {svg_orcid}
              ORCID
            </a>
            <a class="fp-link-icon" href="{escape(email_href, quote=True)}" target="_self">
              {svg_mail}
              Email
            </a>
          </div>
        </header>
        <div class="fp-info-grid">
          <div class="fp-info-card">
            <div class="fp-info-card-top">{ico_rf}<span>Research field</span></div>
            <div class="fp-info-card-val">{research_field_text}</div>
          </div>
          <div class="fp-info-card">
            <div class="fp-info-card-top">{ico_rank}<span>Rank</span></div>
            <div class="fp-info-card-val">{role_text}</div>
          </div>
          <div class="fp-info-card">
            <div class="fp-info-card-top">{ico_inst}<span>Institution</span></div>
            <div class="fp-info-card-val">{institution_text}</div>
          </div>
          <div class="fp-info-card">
            <div class="fp-info-card-top">{ico_contact}<span>Contact</span></div>
            <div class="fp-info-card-val fp-mono">{contact_text}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="fp-section"><h2 class="fp-h2">Publications</h2></div>',
        unsafe_allow_html=True,
    )

    person_pubs = person_pubs_all.copy()

    if not abdc_available:
        st.markdown(
            '<p class="fp-abdc-caption" style="max-width:min(1320px,98vw);margin:8px auto 0;padding:0 20px">'
            "ABDC list not found. Add <code>ABDC.xlsx</code> (preferred) or <code>ABDC.csv</code> "
            "in the project root to enable ABDC matching.</p>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="fp-analytics-marker" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    viz_left, viz_right = st.columns(2, gap="medium", vertical_alignment="center")

    _typed = person_pubs.assign(
        _b=lambda df: df["publication_type"].map(_profile_chart_bucket),
    )
    chart_buckets = (
        _typed["_b"].value_counts().rename_axis("bucket").reset_index(name="count")
    )
    total_count = int(chart_buckets["count"].sum()) if not chart_buckets.empty else 0
    if total_count > 0:
        chart_buckets["pct"] = chart_buckets["count"] / total_count
    else:
        chart_buckets["pct"] = 0.0

    indexed_series = (
        person_pubs.get("indexed_in_scopus", "Yes")
        .fillna("Yes")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    scopus_indexed_count = int((indexed_series == "yes").sum()) if len(person_pubs) else 0
    non_scopus_indexed_count = int(len(indexed_series) - scopus_indexed_count) if len(person_pubs) else 0
    abdc_series = person_pubs.get("abdc_status", "").fillna("").astype(str)
    journal_series = person_pubs.get("publication_type", "").fillna("").astype(str).str.strip().str.lower()
    is_journal = journal_series == "journal"
    peer_reviewed_journal_count = int(is_journal.sum()) if len(person_pubs) else 0
    scopus_peer_reviewed_journal_count = (
        int(((indexed_series == "yes") & is_journal).sum()) if len(person_pubs) else 0
    )
    abdc_peer_reviewed_journal_count = (
        int((is_journal & abdc_series.str.upper().str.startswith("ABDC")).sum()) if len(person_pubs) else 0
    )

    color_domain = ["Journal", "Conference", "Book", "Other"]
    color_range = ["#1565C0", "#42A5F5", "#BBDEFB", "#90CAF9"]

    with viz_left:
        _lc, chart_mid, _rc = st.columns([1, 2, 1])
        with chart_mid:
            if total_count > 0:
                donut_base = alt.Chart(chart_buckets).encode(
                    theta=alt.Theta(field="count", type="quantitative", stack=True),
                    color=alt.Color(
                        field="bucket",
                        type="nominal",
                        legend=None,
                        scale=alt.Scale(domain=color_domain, range=color_range),
                    ),
                    tooltip=[
                        alt.Tooltip("bucket:N", title="Category"),
                        alt.Tooltip("count:Q", title="Count"),
                        alt.Tooltip("pct:Q", title="Share", format=".1%"),
                    ],
                )
                donut_chart = donut_base.mark_arc(
                    innerRadius=88, outerRadius=138, cornerRadius=2
                ).encode(
                    x=alt.value(180),
                    y=alt.value(180),
                )
                # Plot is 360×360; arc is centered — stack count + label on the true center (180, 180).
                cx = 180
                y_count, y_label = 164, 196
                center_big = (
                    alt.Chart(pd.DataFrame({"t": [str(total_count)]}))
                    .mark_text(
                        align="center",
                        baseline="middle",
                        fontSize=36,
                        fontWeight=700,
                        color="#0A2540",
                    )
                    .encode(
                        text=alt.Text("t:N"),
                        x=alt.value(cx),
                        y=alt.value(y_count),
                    )
                )
                center_small = (
                    alt.Chart(pd.DataFrame({"t": ["Total"]}))
                    .mark_text(
                        align="center",
                        baseline="middle",
                        fontSize=13,
                        color="#6B7280",
                    )
                    .encode(
                        text=alt.Text("t:N"),
                        x=alt.value(cx),
                        y=alt.value(y_label),
                    )
                )
                layered = (
                    (donut_chart + center_big + center_small)
                    .properties(width=360, height=360)
                    .configure(background="transparent")
                    .configure_view(clip=False, stroke=None, fill=None)
                )
                st.altair_chart(layered, use_container_width=False, theme=None)
            else:
                st.caption("No publications in the current view.")

    j_total = peer_reviewed_journal_count
    with viz_right:
        st.markdown(
            f"""
            <div class="fp-stats-panel">
              <div class="fp-stats-label">Indexing</div>
              <div class="fp-stats-body">
                <span class="fp-num">{scopus_indexed_count}</span> Scopus indexed |
                <span class="fp-num">{non_scopus_indexed_count}</span> Non-Scopus
              </div>
              <div class="fp-stats-sub">of <span class="fp-num">{total_count}</span> visible publications</div>
              <div class="fp-stats-divider" aria-hidden="true"></div>
              <div class="fp-stats-label">Journal types</div>
              <div class="fp-stats-body">
                <span class="fp-num">{scopus_peer_reviewed_journal_count}</span> Scopus indexed journals |
                <span class="fp-num">{abdc_peer_reviewed_journal_count}</span> ABDC journal
              </div>
              <div class="fp-stats-sub">of <span class="fp-num">{j_total}</span> peer-reviewed journals</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    rows_html = []
    for _, pub in person_pubs.iterrows():
        doi_value = str(pub["doi"]).strip()
        doi_html = (
            f'<a class="fp-doi-link" href="https://doi.org/{escape(doi_value, quote=True)}" target="_self" rel="noopener noreferrer">{svg_ext} DOI</a>'
            if doi_value
            else "—"
        )
        idx_scopus = str(pub.get("indexed_in_scopus", "Yes")).strip() or "Yes"
        scopus_yes = idx_scopus.lower() == "yes"
        scopus_cell = (
            f'<span class="fp-scopus-dot" title="Scopus indexed"></span>'
            if scopus_yes
            else f'<span class="fp-scopus-dot fp-off" title="Not Scopus indexed"></span>'
        )
        try:
            y_raw = int(pub["year"])
            year_disp = str(y_raw) if y_raw > 0 else "—"
        except (TypeError, ValueError):
            year_disp = "—"
        ptype = escape(str(pub.get("publication_type", "")).strip() or "—")
        rows_html.append(
            "".join(
                [
                    "<tr>",
                    f"<td class='fp-col-title'>{escape(str(pub['title'])) or '—'}</td>",
                    f"<td class='fp-col-type'><span class='fp-type-pill'>{ptype}</span></td>",
                    f"<td class='fp-col-source'>{escape(str(pub['source_title'])) or '—'}</td>",
                    f"<td class='fp-col-abdc'>{escape(str(pub.get('abdc_status', '—')))}</td>",
                    f"<td class='fp-col-year'>{year_disp}</td>",
                    f"<td class='fp-col-scopus'>{scopus_cell}</td>",
                    f"<td class='fp-col-doi'>{doi_html}</td>",
                    "</tr>",
                ]
            )
        )

    table_html = f"""
    <div class="fp-table-card">
      <table class="fp-pubs-table">
        <thead>
          <tr>
            <th class="fp-col-title">Title</th>
            <th class="fp-col-type">Type</th>
            <th class="fp-col-source">Source</th>
            <th class="fp-col-abdc">ABDC</th>
            <th class="fp-col-year">Year</th>
            <th class="fp-col-scopus">Scopus</th>
            <th class="fp-col-doi">DOI</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html) if rows_html else '<tr><td colspan="7">No matching publications found.</td></tr>'}
        </tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


init_auth_state()

if should_sign_out_from_query_params():
    sign_out()

# Always gate app content behind the login screen.
if not st.session_state.get(SESSION_AUTHENTICATED, False):
    render_login_page()
    st.stop()

inject_styles()

selected_orcid = get_selected_orcid()
app_page = get_app_page()

if selected_orcid:
    cohort_key = cohort_from_query_params()
    summary_data, publications_data, _, _ = load_data(cohort_key)
    render_profile_page(
        summary_data,
        publications_data,
        selected_orcid,
        cohort_key,
    )
elif app_page == "research":
    render_master_table()
elif app_page == "teaching":
    render_teaching_analytics()
elif app_page == "analytics":
    render_analytics_placeholder()
else:
    render_landing()
