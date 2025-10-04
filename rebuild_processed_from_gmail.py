import os
import csv
from datetime import datetime
import importlib.util

jt_path = os.path.join(os.getcwd(), 'job-tracker.py')
spec = importlib.util.spec_from_file_location('job_mod', jt_path)
job_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_mod)

sheets = job_mod.authenticate('sheets', ['https://www.googleapis.com/auth/spreadsheets'], os.environ.get('TOKEN_SHEETS_FILE','token_sheets.pickle'))

gmail = job_mod.authenticate('gmail', ['https://www.googleapis.com/auth/gmail.readonly'], os.environ.get('TOKEN_GMAIL_FILE','token_gmail.pickle'))

# Back up existing sheet
resp = sheets.spreadsheets().values().get(spreadsheetId=job_mod.SHEET_ID, range=f"{job_mod.PROCESSED_SHEET_NAME}!A:Z").execute()
vals = resp.get('values', [])
backup_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'Job Posts')
os.makedirs(backup_path, exist_ok=True)
backup_file = os.path.join(backup_path, f'sheet_backup_rebuild_{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv')
with open(backup_file, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    for r in vals:
        w.writerow(r)
print('Backed up current processed sheet to', backup_file)

# Build fresh rows from Gmail
results = gmail.users().messages().list(userId='me', q=job_mod.GMAIL_QUERY).execute()
messages = results.get('messages', [])
rows = [job_mod.DEFAULT_HEADERS]
count = 0
for m in messages:
    d = job_mod.get_email_details(gmail, m['id'])
    if not d:
        continue
    subj = job_mod.translate_subject(d[2])
    snippet = job_mod.translate_text(d[5])
    role = job_mod.detect_role_from_text(f"{subj} {snippet}")
    final_row = [
        d[0], d[1], subj, d[3], d[4], snippet,
        d[6] if len(d) > 6 else '', d[7] if len(d) > 7 else '', d[8] if len(d) > 8 else '', role
    ]
    rows.append(final_row)
    count += 1
print('Built', count, 'rows from Gmail')

# Write into sheet (overwrite)
sheets.spreadsheets().values().clear(spreadsheetId=job_mod.SHEET_ID, range=f'{job_mod.PROCESSED_SHEET_NAME}!A:Z').execute()
sheets.spreadsheets().values().update(spreadsheetId=job_mod.SHEET_ID, range=f'{job_mod.PROCESSED_SHEET_NAME}!A1', valueInputOption='USER_ENTERED', body={'values': rows}).execute()
print('Wrote fresh rows to Processed Jobs')
