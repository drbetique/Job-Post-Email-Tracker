import os
import importlib.util

jt_path = os.path.join(os.getcwd(), 'job-tracker.py')
spec = importlib.util.spec_from_file_location('job_mod', jt_path)
job_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_mod)

sheets = job_mod.authenticate('sheets', ['https://www.googleapis.com/auth/spreadsheets.readonly'], os.environ.get('TOKEN_SHEETS_FILE', 'token_sheets.pickle'))
resp = sheets.spreadsheets().values().get(spreadsheetId=job_mod.SHEET_ID, range=f"{job_mod.PROCESSED_SHEET_NAME}!A1:Z50").execute()
vals = resp.get('values', [])
print('Rows fetched:', len(vals))
for i, row in enumerate(vals[:10]):
    print(f'Row {i}:')
    for j in range(10):
        val = row[j] if j < len(row) else ''
        print(f'  Col{j} ({job_mod.DEFAULT_HEADERS[j] if j < len(job_mod.DEFAULT_HEADERS) else j}):', repr(val)[:200])
    print('---')
