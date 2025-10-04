import os
import re
import subprocess
import glob
import csv

def find_latest_csv():
    files = glob.glob(os.path.expanduser('~') + '/Desktop/Job Posts/processed_jobs_export*.csv')
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

csv_path = find_latest_csv()
if not csv_path:
    print('No processed_jobs_export CSV found')
    raise SystemExit(1)

print('Checking', csv_path)

# Read header to find column indices
with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
    lines = f.read().splitlines()

if not lines:
    print('CSV empty')
    raise SystemExit(1)

header = lines[0].split(',')
# Trim quotes
header = [h.strip().strip('"') for h in header]

# Required columns
cols = {name: idx for idx, name in enumerate(header)}
needed = ['Links','Role']
for n in needed:
    if n not in cols:
        print('CSV missing column', n)
        raise SystemExit(1)

# Look for rows where subject/snippet likely contains a URL but Links is empty or Role is empty
url_re = re.compile(r'https?://|www\.')
problems = []
for ln in lines[1:]:
    try:
        cols_values = list(csv.reader([ln]))[0]
    except Exception:
        cols_values = ln.split(',')
    # Find subject/snippet in typical positions (Subject at idx 2, Snippet at idx 5) fallback
    subj = cols_values[2] if len(cols_values) > 2 else ''
    snippet = cols_values[5] if len(cols_values) > 5 else ''
    links_val = cols_values[cols['Links']] if cols['Links'] < len(cols_values) else ''
    role_val = cols_values[cols['Role']] if cols['Role'] < len(cols_values) else ''
    if url_re.search(subj + ' ' + snippet) and (not links_val.strip() or not role_val.strip()):
        problems.append((cols_values[0] if cols_values else '<no-id>', subj[:80], snippet[:80], links_val, role_val))

if not problems:
    print('No problems found. Export looks good.')
    raise SystemExit(0)

print('Found', len(problems), 'rows with missing Links/Role. Re-running update and export...')
# Re-run the update pipeline
subprocess.check_call(['python', 'add_role_and_sort.py'])
subprocess.check_call(['python', 'export_processed_jobs.py'])
print('Re-exported. Please re-run verifier to confirm or check the new CSV.')
