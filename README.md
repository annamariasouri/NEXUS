# NEXUS Scopus Publications Tracker

This project fetches **all Scopus publication types** for faculty rosters, limited to the last **6 calendar years** (including the current year), then writes CSV outputs and powers the Streamlit dashboard.

**Full-time** (`Full timers ORCID.csv`):

- `outputs/publications_raw.csv`
- `outputs/summary.csv`

**Part-time** (`Part timers ORCID.csv`):

- `outputs/part_timers/publications_raw.csv`
- `outputs/part_timers/summary.csv`

The same Scopus search logic, publication typing, and **status rules** apply to both cohorts (part-time rows may omit rank, telephone, and Scopus ID if you only have ORCID).

Status logic (for requirement tracking):

- `fulfills requirements`: at least 3 **journal** publications in the window
- `HOD Consideration`: 0 or 1 journal publication in the window
- `does not fulfill requirements`: exactly 2 journal publications in the window

## Dashboard Experience

- Use the sidebar **Faculty cohort** control to switch between **Full-time** and **Part-time** datasets (each loads its own precomputed CSV pair).
- Main table: modern summary dashboard with filters and clickable names.
- Profile page: clicking a name opens a dynamic profile with:
	- Name, department, rank, email, telephone, ORCID
	- All publications in the last 6 years
	- Columns: title, type, source (journal/conference/book), year, DOI
	- Per-profile CSV download

## Security and Access

- Keep this repository **private** so only invited collaborators can access data.
- Do **not** commit API keys or passwords.
- Use `.env` locally and GitHub Secrets in Actions.
- Dashboard includes password gate via `APP_ACCESS_PASSWORD`.

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and set values:

```env
SCOPUS_API_KEY=...
```

4. Run data pipelines (full-time and part-time):

```bash
python src/pipeline.py --input "Full timers ORCID.csv" --output-dir outputs
python src/pipeline.py --input "Part timers ORCID.csv" --output-dir outputs/part_timers
```

5. Run dashboard:

```bash
streamlit run app.py
```

## GitHub Actions Weekly Update

Workflow: `.github/workflows/weekly-update.yml`

- Runs every Monday at 05:00 UTC
- Can also run manually from GitHub Actions tab
- Refreshes full-time and part-time output CSV files and commits changes

### Required GitHub Secret

Set this secret in repository settings:

- `SCOPUS_API_KEY`

## Notes

- Lookup priority is ORCID first; if ORCID returns no results and `Scopus ID` exists, Scopus ID is used as fallback.
- ORCID values are normalized automatically (supports raw ORCID and URL forms).
- Publication type is normalized from Scopus aggregation type.
- If Scopus API returns errors for an author, the summary will include the error in `notes`.
