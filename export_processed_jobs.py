import os
import csv
import importlib.util

# job-tracker.py contains `authenticate`; load it by path (hyphen prevents normal import)
jt_path = os.path.join(os.getcwd(), 'job-tracker.py')
spec = importlib.util.spec_from_file_location('job_tracker_mod', jt_path)
job_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_mod)
# authenticate function available as job_mod.authenticate
auth_func = getattr(job_mod, 'authenticate')

SHEET_ID = os.environ.get('SHEET_ID', '1lhWIUbdSYepoz0zPZskHPglcRB78Rq2HyiL1wzgkAxE')
PROCESSED_SHEET_NAME = 'Processed Jobs'

if __name__ == '__main__':
    # Create a disposable sheets service
    sheets_service = auth_func('sheets', ['https://www.googleapis.com/auth/spreadsheets.readonly'], 'token_sheets.pickle')
    def sheets_execute_with_retry(request_fn, max_retries=3, initial_backoff=1.0):
        import time
        backoff = initial_backoff
        for attempt in range(max_retries):
            try:
                req = request_fn()
                return req.execute()
            except Exception:
                if attempt >= max_retries - 1:
                    raise
                time.sleep(backoff)
                backoff *= 2

    resp = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=f"{PROCESSED_SHEET_NAME}!A:Z"))
    vals = resp.get('values', [])

    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    dest_dir = os.path.join(desktop, 'Job Posts')
    os.makedirs(dest_dir, exist_ok=True)
    export_path = os.path.join(dest_dir, 'processed_jobs_export.csv')
    try:
        with open(export_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            for r in vals:
                w.writerow(r)
        print('Wrote export to', export_path)
    except PermissionError:
        # If file is locked (e.g., opened in Excel), write to a timestamped filename instead
        import time
        ts = time.strftime('%Y%m%d-%H%M%S')
        alt = os.path.join(dest_dir, f'processed_jobs_export_{ts}.csv')
        with open(alt, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            for r in vals:
                w.writerow(r)
        print('Wrote export to', alt)
