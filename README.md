# NEXUS Scopus Publications Tracker

This project fetches Scopus journal publications for ORCIDs listed in `Full timers ORCID.csv`, limited to the last 6 years, then creates:

- `outputs/publications_raw.csv` (all qualifying records)
- `outputs/summary.csv` (one row per person with status)

Status logic:

- `fulfills requirements`: at least 3 journal publications in last 6 years
- `does not fulfill requirements`: fewer than 3

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
APP_ACCESS_PASSWORD=...
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

- ORCID values are normalized automatically (supports raw ORCID and URL forms).
- Journal filter uses Scopus source type and aggregation type checks.
- If Scopus API returns errors for an author, the summary will include the error in `notes`.
