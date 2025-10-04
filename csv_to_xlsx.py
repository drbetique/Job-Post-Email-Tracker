import sys
import os
import csv
from openpyxl import Workbook

# Find newest processed_jobs_export*.csv
import glob
files = glob.glob(os.path.expanduser('~') + '/Desktop/Job Posts/processed_jobs_export*.csv')
if not files:
    print('No processed_jobs_export CSV found')
    sys.exit(1)
files.sort(key=os.path.getmtime, reverse=True)
csv_path = files[0]

wb = Workbook()
ws = wb.active
ws.title = 'Processed Jobs'

with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.reader(f)
    for r in reader:
        ws.append(r)

xlsx_path = os.path.splitext(csv_path)[0] + '.xlsx'
wb.save(xlsx_path)
print('Wrote XLSX to', xlsx_path)
