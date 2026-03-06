# NEXUS Scopus Publications Tracker

This project fetches **all Scopus publication types** for people listed in `Full timers ORCID.csv`, limited to the last 6 years, then creates:

- `outputs/publications_raw.csv` (all publication records: journal, conference, book, etc.)
- `outputs/summary.csv` (one row per person with profile details and status)

Status logic (for requirement tracking):

- `fulfills requirements`: at least 3 **journal** publications in last 6 years
- `does not fulfill requirements`: fewer than 3

## Dashboard Experience

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

4. Run data pipeline:

```bash
python src/pipeline.py --input "Full timers ORCID.csv" --output-dir outputs
```

5. Run dashboard:

```bash
streamlit run app.py
```

## GitHub Actions Weekly Update

Workflow: `.github/workflows/weekly-update.yml`

- Runs every Monday at 05:00 UTC
- Can also run manually from GitHub Actions tab
- Refreshes output CSV files and commits changes

### Required GitHub Secret

Set this secret in repository settings:

- `SCOPUS_API_KEY`

## Notes

- Lookup priority is ORCID first; if ORCID returns no results and `Scopus ID` exists, Scopus ID is used as fallback.
- ORCID values are normalized automatically (supports raw ORCID and URL forms).
- Publication type is normalized from Scopus aggregation type.
- If Scopus API returns errors for an author, the summary will include the error in `notes`.
