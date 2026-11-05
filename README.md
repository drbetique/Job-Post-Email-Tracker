# Job Post Email Tracker

A small Python utility that reads job-notification emails from Gmail, extracts posted job links, classifies by role, translates Finnish text to English, and writes results to a Google Sheet. The project also exports the processed sheet as a UTF-8 (BOM) CSV and converts the CSV to XLSX. It includes helpers for backup, repair of CSV encoding, link resolution caching, and verification.

This repository is commonly run on Windows (PowerShell helpers are included), but the Python scripts are cross-platform.

## What's included (high level)
- `job-tracker.py` — main pipeline: reads Gmail, extracts messages, translates subject/snippet, detects a job role, resolves links (optional), fetches page titles, writes batched rows to the `Processed Jobs` sheet/tab, and triggers export+verification+XLSX conversion.
- `add_role_and_sort.py` — helper to recompute roles/links for existing rows, backup the sheet, and sort by `Role`. Supports `--dry-run`.
- `export_processed_jobs.py` — exports the `Processed Jobs` sheet to a UTF-8 with BOM CSV in `%USERPROFILE%\Desktop\Job Posts` (writes timestamped fallback if the default file is locked).
- `csv_to_xlsx.py` — converts the latest processed CSV to XLSX using `openpyxl`.
- `verify_and_fix_export.py` — checks exported CSV for missing Links/Role and can re-run processing if problems are detected.
- `tools/link_cache.py` — small SQLite cache used to store resolved final URLs and titles with TTL support.
- `tools/repair_export_encoding.py` — helper to repair mojibake/encoding issues in existing exports and write a UTF-8-BOM CSV.
- `requirements.txt` — Python dependencies.
- PowerShell helpers: `setup_venv.ps1`, `secure_move_credentials.ps1`, `run_all.ps1`, `create_daily_task.ps1` for environment and scheduling.

## Key features added since the initial prototype
- Multi-link extraction from email bodies (configurable max links per message).
- Hybrid link resolution (HEAD first, fallback to a small GET if needed) with parallel fetching.
- Title extraction using BeautifulSoup with OG/twitter/meta tag fallbacks and <title> fallback.
- SQLite-based link cache with configurable TTL (`LINK_CACHE_TTL_DAYS`) to avoid repeated network calls.
- UTF-8 (with BOM) CSV export and a converter to XLSX for Excel-friendly files.
- Post-run verification that checks the CSV for missing Links/Role and re-runs processing if needed.
- Environment-driven configuration and secure credential helpers.

## Quickstart (recommended)

1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

3. Secure credentials (very important)
- Place your Google OAuth client JSON and any tokens in a secure folder. Use `secure_move_credentials.ps1` to move them under `%USERPROFILE%\.job_tracker_creds` and persist environment variables (`CREDENTIALS_FILE`, `TOKEN_GMAIL_FILE`, `TOKEN_SHEETS_FILE`) using `setx`. Restart PowerShell to pick up `setx` values.

4. (Optional) Enable better translations with Google Cloud Translate by setting:

```powershell
setx GOOGLE_API_KEY "YOUR_API_KEY"
# restart shell
```

5. Run the full pipeline (process new emails, update sheet, export CSV, verify and convert to XLSX):

```powershell
python .\job-tracker.py
```

6. To re-run link/title resolution and role computation on existing sheet rows (dry-run supported):

```powershell
python .\add_role_and_sort.py --dry-run
python .\add_role_and_sort.py         # to apply changes
```

7. Export only (reads the `Processed Jobs` sheet and writes CSV):

```powershell
python .\export_processed_jobs.py
```

## Configuration / Environment variables
The scripts can be configured via environment variables. Useful ones:

- `SHEET_ID` — (recommended) Google Sheets spreadsheetId to use instead of the hardcoded default.
- `CREDENTIALS_FILE` — Path to OAuth client secrets JSON used by google-auth.
- `TOKEN_GMAIL_FILE` — Path to Gmail token pickle file used to cache OAuth tokens.
- `TOKEN_SHEETS_FILE` — Path to Sheets token pickle file used to cache OAuth tokens.
- `GOOGLE_API_KEY` — (optional) Google Cloud Translate API key (preferred for production translations).
- `RESOLVE_LINKS` — Set to `1` or `true` to enable link resolving and title fetching. Defaults to enabled in current scripts but can be disabled for speed or privacy.
- `MAX_LINKS_PER_MESSAGE` — Maximum number of links to extract per message (default in code: 3).
- `LINK_WORKERS` — Number of parallel workers for link resolution (default: 5).
- `LINK_CACHE_TTL_DAYS` — TTL (days) for link cache entries (default: 30). Set lower for fresher data.
- `HEAD_TIMEOUT`, `GET_TIMEOUT` — HTTP timeouts (seconds) for HEAD/GET requests used in resolution.
- `EXPORT_DIR` — Directory for exports. By default the scripts write to `%USERPROFILE%\Desktop\Job Posts`.

If you use `secure_move_credentials.ps1`, it will set `CREDENTIALS_FILE`, `TOKEN_GMAIL_FILE` and `TOKEN_SHEETS_FILE` at user level.

## Where outputs land
- CSV exports and backups are written to `%USERPROFILE%\Desktop\Job Posts` by default. Filenames follow the pattern `processed_jobs_export.csv` (primary) and `processed_jobs_export_YYYYMMDD-HHMMSS.csv` for timestamped fallbacks. Backups use `sheet_backup_*.csv`.

## Troubleshooting
- OAuth failures: ensure `CREDENTIALS_FILE` points to a valid OAuth client JSON and that `TOKEN_*` paths are writable.
- Empty Links/Resolved Links/Link Titles in the CSV: first check `RESOLVE_LINKS` (enable if disabled). If enabled and still empty, inspect application logs or re-run `add_role_and_sort.py` on a small sample with verbose logging to see HTTP/SSL errors.
- Intermittent Sheets API SSL errors (example seen: "EOF occurred in violation of protocol (_ssl.c:2417)"): these are typically transient network/SSL handshake issues. The script will continue; consider adding a short retry/backoff around Sheets writes if you see this often (recommended improvement). Re-running the script usually succeeds.
- Export file locked: if `processed_jobs_export.csv` is open in Excel, exporter will write a timestamped fallback file instead.
- Mojibake in older CSVs: use `tools/repair_export_encoding.py` to attempt repairs and rewrite as UTF-8 with BOM.

## Development notes and next steps
- The code now prefers BeautifulSoup for title extraction and uses a SQLite cache (`tools/link_cache.py`) to speed repeated runs.
- Suggested improvements you might want to add:
	- Add retry/backoff for Sheets API writes to handle intermittent SSL/network errors.
	- Extend title heuristics (schema.org/meta description) and better truncation of long titles.
	- Add unit tests for link resolution and CSV export and a simple CI job that runs `python -m py_compile` and the tests.

## Scripts and helpers
- `setup_venv.ps1` — create venv and install requirements.
- `secure_move_credentials.ps1` — move credentials into a secure folder and `setx` env vars.
- `run_all.ps1` — example wrapper that runs the tracker and export.
- `create_daily_task.ps1` — helper to create a scheduled task.
- `tools/repair_export_encoding.py` — repair old CSV exports.
- `tools/link_cache.py` — sqlite cache used by resolvers.

## Requirements
See `requirements.txt`. Primary runtime packages include:

- google-api-python-client
- google-auth
- google-auth-oauthlib
- requests
- googletrans (fallback translator)
- beautifulsoup4
- openpyxl

## License & contributing
Released under the [MIT License](LICENSE). Issues and pull requests are welcome; never include credentials or token files in them. Planned work is in [ROADMAP.md](ROADMAP.md).

## Prepare to push to GitHub (safety checklist)

Before making the repository public or pushing to a remote GitHub repo, follow these safety steps to avoid exposing credentials or tokens:

1. Add and commit the safety files (if not already present):

	- `.gitignore` — ignores credentials, token files, exports and `.venv`.
	- `.env.example` — documents required env vars without real secrets.

2. Check for tracked sensitive files (dry-run):

	- Run the helper to list any sensitive files still tracked by git:

```powershell
.
tools\cleanup_git_history.ps1
# If you want to remove found files from the index (keeps local copies), re-run with:
.
tools\cleanup_git_history.ps1 -RemoveFromIndex
```

3. If any secrets were ever committed, rotate/revoke them immediately:

	- Revoke OAuth client secrets, regenerate client IDs if needed, rotate API keys.
	- If a token file (pickle) was committed, delete the token and re-authenticate to get a new one.

4. Purge secrets from repository history (if necessary):

	- Use BFG Repo-Cleaner or git-filter-repo to remove sensitive files from history, then force-push the cleaned branch. Example with BFG:

```powershell
# After installing BFG (Java required)
bfg --delete-files 'credentials.json'
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

5. Push to GitHub and use GitHub Secrets for runtime credentials:

	- Create a new (private) GitHub repository, or use an existing one.
	- On GitHub, go to Settings > Secrets and variables > Actions and add secrets such as `GOOGLE_API_KEY`, or private paths if using runner-managed secrets.
	- Update your deployment / CI to read secrets from GitHub Actions secrets or your host environment variables — never store them in the repo.

6. Final verification (quick):

	- Clone the remote repository to a temp folder and run `git ls-files` to confirm no credential files are present.

If you'd like, I can run the `tools/cleanup_git_history.ps1` scan for you (dry-run) and then show the git commands to remove any discovered tracked secrets. I can also create the GitHub repo and push for you, but I'll need your confirmation and the remote URL (and you'll still need to rotate exposed credentials if any were committed previously).
