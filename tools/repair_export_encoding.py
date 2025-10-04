import os
import shutil
import datetime
import sys

# Paths
desktop = os.path.expandvars(r"%USERPROFILE%\\Desktop\\Job Posts")
orig = os.path.join(desktop, 'processed_jobs_export.csv')

if not os.path.exists(orig):
    print('ERROR: processed_jobs_export.csv not found at', orig)
    sys.exit(2)

# backup
ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
bak = os.path.join(desktop, f'processed_jobs_export_backup_{ts}.csv')
shutil.copy2(orig, bak)
print('Backed up original to', bak)

# Read raw bytes
with open(orig, 'rb') as f:
    data = f.read()

# Try: is file already valid UTF-8 and "looks good"?
repaired = None
try:
    text_utf8 = data.decode('utf-8')
    # Heuristic: if we see common mojibake markers, attempt repair anyway
    mojibake_markers = ['Ã', 'â', '\ufffd']
    if any(m in text_utf8 for m in mojibake_markers):
        print('UTF-8 decode OK but mojibake markers found; attempting reinterpretation...')
        # reinterpret: encode as cp1252 then decode as utf-8
        try:
            repaired_try = text_utf8.encode('cp1252', errors='replace').decode('utf-8')
            repaired = repaired_try
            print('Reinterpretation succeeded (utf8->cp1252->utf8)')
        except Exception as e:
            print('Reinterpretation failed:', e)
            repaired = text_utf8  # use utf8 as-is
    else:
        print('File already valid UTF-8 and no mojibake markers detected — no change made.')
        repaired = text_utf8
except UnicodeDecodeError:
    # Not valid utf-8; try decode as cp1252 then reinterpret as utf-8
    try:
        text_cp = data.decode('cp1252')
        try:
            repaired_try = text_cp.encode('cp1252', errors='replace').decode('utf-8')
            repaired = repaired_try
            print('Repaired by decoding as cp1252 then decoding bytes as utf-8')
        except Exception as e:
            print('Failed strict re-decode, doing relaxed replace:', e)
            repaired = text_cp.encode('cp1252', errors='replace').decode('utf-8', errors='replace')
    except Exception as e:
        print('Unexpected error decoding as cp1252:', e)
        # final fallback: try latin-1
        try:
            text_l1 = data.decode('latin-1')
            repaired = text_l1.encode('latin-1', errors='replace').decode('utf-8', errors='replace')
            print('Fallback latin-1->utf-8 used')
        except Exception as ex:
            print('All decoding attempts failed:', ex)
            sys.exit(3)

# Write repaired content back as UTF-8 with BOM (utf-8-sig) to help Excel
with open(orig, 'w', encoding='utf-8-sig', newline='') as out:
    out.write(repaired)

print('Wrote repaired file (utf-8-sig) to', orig)

# Print first 40 lines as a quick check
lines = repaired.splitlines()
print('\n=== First 40 lines of repaired CSV ===')
for i, line in enumerate(lines[:40], 1):
    print(f'{i:03d}:', line)

print('\nDone.')
