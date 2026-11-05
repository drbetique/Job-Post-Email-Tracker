import argparse
import csv
import pickle
import os
import sys
import time
import shutil
from typing import Optional
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
try:
    from googletrans import Translator
except Exception:
    Translator = None
try:
    import requests
except Exception:
    requests = None
try:
    from tools.link_cache import get_cached, set_cached
except Exception:
    get_cached = lambda u: None
    set_cached = lambda u, f, t: None

# Use same spreadsheet id as job-tracker.py
SHEET_ID = os.environ.get('SHEET_ID', '')
if not SHEET_ID:
    raise SystemExit(
        "SHEET_ID is not set. Set it to the spreadsheetId from your Google Sheet URL "
        "(https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit), "
        "for example in PowerShell: setx SHEET_ID <SPREADSHEET_ID>"
    )
TOKEN_FILE = os.environ.get('TOKEN_SHEETS_FILE', 'token_sheets.pickle')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
BACKUP_CSV = os.environ.get('BACKUP_CSV', 'sheet_backup.csv')
PROCESSED_SHEET_NAME = os.environ.get('PROCESSED_SHEET_NAME', 'Processed Jobs')

# High-priority roles are checked first (per user request)
ROLE_PRIORITY = [
    'system specialist', 'it support', 'embedded system programming'
]

ROLE_KEYWORDS = [
    'embedded','embedded system','embedded systems','embedded systems engineer','embedded system programming',
    'system specialist','system specialist','system engineer',
    'it support','support','helpdesk','service desk',
    'data scientist','data engineer','engineer','developer','frontend','backend','fullstack',
    'manager','analyst','designer','lead','architect','consultant','product','qa','tester',
    'intern','director','sales','marketing'
]

DEFAULT_HEADERS = ['MessageID','Timestamp','Subject (EN)','Sender','Date','Snippet (EN)','Links','Resolved Links','Link Titles','Role']


def translate_subject(text: str, prefer_cloud: bool = True) -> str:
    """Translate Finnish->English. Prefer Google Cloud Translate when GOOGLE_API_KEY is set and `requests` is available.

    Falls back to `googletrans` if installed. If no translator available, returns original text.
    """
    if not text:
        return ''

    api_key = os.environ.get('GOOGLE_API_KEY')
    if prefer_cloud and api_key and requests:
        try:
            url = f'https://translation.googleapis.com/language/translate/v2'
            params = {
                'q': text,
                'source': 'fi',
                'target': 'en',
                'format': 'text',
                'key': api_key,
            }
            r = requests.post(url, data=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data['data']['translations'][0]['translatedText']
        except Exception:
            # Fall through to local translator
            pass

    if Translator is None:
        return text
    try:
        t = Translator()
        res = t.translate(text, src='fi', dest='en')
        return res.text
    except Exception:
        return text


def _extract_first_url_from_text(text: str) -> str:
    import re
    if not text:
        return ''
    urls = re.findall(r"https?://[^\s'\">)]+", text)
    if not urls:
        urls = re.findall(r"www\.[^\s'\">)]+", text)
    normalized = []
    for u in urls:
        if u.startswith('www.'):
            normalized.append('http://' + u)
        else:
            normalized.append(u)
    return ';'.join(normalized)


# Optional: resolve links and fetch titles
RESOLVE_LINKS = os.environ.get('RESOLVE_LINKS', '1') not in ('0', 'false', 'False')
MAX_LINKS_PER_MESSAGE = int(os.environ.get('MAX_LINKS_PER_MESSAGE', '3'))
TITLE_MAX_BYTES = int(os.environ.get('TITLE_MAX_BYTES', '16384'))
HEAD_TIMEOUT = float(os.environ.get('HEAD_TIMEOUT', '6.0'))
GET_TIMEOUT = float(os.environ.get('GET_TIMEOUT', '8.0'))
LINK_WORKERS = int(os.environ.get('LINK_WORKERS', '5'))

def _resolve_links_and_titles(links_semicolon: str):
    if not RESOLVE_LINKS or not links_semicolon:
        return '', ''
    try:
        import requests, re
    except Exception:
        return '', ''
    links = links_semicolon.split(';') if links_semicolon else []
    resolved = []
    titles = []
    to_resolve = links[:MAX_LINKS_PER_MESSAGE]
    resolved = [None] * len(to_resolve)
    titles = [None] * len(to_resolve)

    def _resolve_one(idx_link):
        idx, link = idx_link
        final = ''
        title = ''
        # Check cache with TTL
        try:
            ttl = int(os.environ.get('LINK_CACHE_TTL_DAYS', '30'))
        except Exception:
            ttl = None
        try:
            cached = get_cached(link, ttl)
            if cached:
                return idx, cached[0] or '', cached[1] or ''
        except Exception:
            pass
        try:
            r = requests.head(link, timeout=HEAD_TIMEOUT, allow_redirects=True, headers={'User-Agent':'JobTrackerBot/1.0'})
            final = r.url
            ctype = r.headers.get('Content-Type', '')
            want_title = ('html' in ctype.lower())
            if not want_title:
                want_title = True
            if want_title:
                try:
                    g = requests.get(final or link, timeout=GET_TIMEOUT, stream=True, allow_redirects=True, headers={'User-Agent':'JobTrackerBot/1.0'})
                    chunks = []
                    read = 0
                    for chunk in g.iter_content(chunk_size=1024):
                        if not chunk:
                            break
                        chunks.append(chunk)
                        read += len(chunk)
                        if read >= TITLE_MAX_BYTES:
                            break
                    content = b''.join(chunks).decode('utf-8', errors='ignore')
                    # Try BeautifulSoup OG/twitter/meta/title extraction
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(content, 'html.parser')
                        title_tag = None
                        og = soup.find('meta', property='og:title')
                        if og and og.get('content'):
                            title_tag = og.get('content')
                        if not title_tag:
                            tw = soup.find('meta', attrs={'name': 'twitter:title'})
                            if tw and tw.get('content'):
                                title_tag = tw.get('content')
                        if not title_tag:
                            meta_title = soup.title
                            if meta_title and meta_title.string:
                                title_tag = meta_title.string
                        if title_tag:
                            title = title_tag.strip()
                    except Exception:
                        import re
                        m = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                        if m:
                            title = m.group(1).strip()
                    if title:
                        try:
                            set_cached(link, final or link, title)
                        except Exception:
                            pass
                except Exception:
                    title = ''
        except Exception:
            final = ''
            title = ''
        return idx, final, title

    if to_resolve:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=LINK_WORKERS) as ex:
            futures = [ex.submit(_resolve_one, (i, to_resolve[i])) for i in range(len(to_resolve))]
            for fut in as_completed(futures):
                try:
                    i, f, t = fut.result()
                    resolved[i] = f
                    titles[i] = t
                except Exception:
                    pass
    resolved = [u for u in resolved if u]
    titles = [t for t in titles if t]
    return ';'.join(resolved), ';'.join(titles)


def authenticate_gmail(token_file='token_gmail.pickle', scopes=None):
    if scopes is None:
        scopes = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'wb') as f:
            pickle.dump(creds, f)
    return build('gmail', 'v1', credentials=creds)


def _gather_message_text(payload) -> str:
    """Recursively gather text content from Gmail message payload parts."""
    parts = []
    if not payload:
        return ''
    if 'parts' in payload:
        for p in payload['parts']:
            parts.append(_gather_message_text(p))
    else:
        body = payload.get('body', {}).get('data')
        if body:
            try:
                import base64
                decoded = base64.urlsafe_b64decode(body + '==').decode('utf-8', errors='ignore')
                parts.append(decoded)
            except Exception:
                pass
    return '\n'.join([p for p in parts if p])


def _extract_all_urls(text: str) -> str:
    import re
    if not text:
        return ''
    urls = re.findall(r"https?://[^\s'\">)]+", text)
    if not urls:
        urls = re.findall(r"www\.[^\s'\">)]+", text)
    normalized = []
    for u in urls:
        if u.startswith('www.'):
            normalized.append('http://' + u)
        else:
            normalized.append(u)
    return ';'.join(normalized)


def authenticate_sheets(token_file=TOKEN_FILE, scopes=SCOPES):
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'wb') as f:
            pickle.dump(creds, f)
    return build('sheets', 'v4', credentials=creds)


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


def detect_role(text: str) -> str:
    if not text:
        return 'Other'
    t = text.lower()
    # Check priority list first
    for p in ROLE_PRIORITY:
        if p in t:
            return p.title()
    for kw in ROLE_KEYWORDS:
        if kw in t:
            # Normalize some names
            val = kw.title()
            if 'Embedded' in val:
                return 'Embedded System Programming'
            if val.lower() in ('support', 'it support'):
                return 'IT Support'
            return val
    return 'Other'


def backup_sheet(sheets_service, spreadsheet_id: str, csv_path: str):
    # Read entire first sheet (A:Z) and write CSV
    resp = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range='A:Z'))
    values = resp.get('values', [])
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            for row in values:
                w.writerow(row)
        print(f'Backed up {len(values)} rows to {csv_path}')
    except Exception as e:
        print(f'Failed to write backup CSV: {e}')
    return values


def update_sheet_with_roles(sheets_service, spreadsheet_id, values):
    if not values:
        print('No values to update')
        return
    # Ensure the processed sheet exists
    meta = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id))
    sheet_names = [s['properties']['title'] for s in meta.get('sheets', [])]
    if PROCESSED_SHEET_NAME not in sheet_names:
        add_sheet_body = {
            'requests': [
                {'addSheet': {'properties': {'title': PROCESSED_SHEET_NAME}}}
            ]
        }
        sheets_execute_with_retry(lambda: sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=add_sheet_body))

    # Build processed rows using DEFAULT_HEADERS order
    processed_rows = [DEFAULT_HEADERS]
    seen = set()
    # Prepare gmail client once (for resolving message bodies when MessageID present)
    gmail_service = None
    try:
        gmail_service = authenticate_gmail()
    except Exception:
        gmail_service = None

    # If the incoming values have a header row, use it to map columns robustly
    header_row = values[0] if values and isinstance(values[0], list) else []
    header_map = {h: i for i, h in enumerate(header_row)} if header_row else {}

    def get_col(row, name, fallback_index=None):
        # Return value from row using header_map if available, otherwise fallback index
        if name in header_map:
            idx = header_map[name]
            return row[idx] if idx < len(row) else ''
        if fallback_index is not None and fallback_index < len(row):
            return row[fallback_index]
        return ''

    # Iterate data rows (skip header if present)
    data_rows = values[1:] if header_row else values
    for row in data_rows:
        subj = get_col(row, 'Subject (EN)', 1)
        # Some sheets might have original Subject instead: try 'Subject' too
        if not subj:
            subj = get_col(row, 'Subject', 1)
        snippet = get_col(row, 'Snippet (EN)', 5)
        if not snippet:
            snippet = get_col(row, 'Snippet', 5)

        # Attempt to read message id if present somewhere (prefer header 'MessageID' then column 0)
        msgid = get_col(row, 'MessageID', 0)
        # Validate that msgid looks like a Gmail message id (avoid timestamps accidentally stored in MessageID column)
        # Gmail message ids are typically opaque short hex-like strings without spaces; timestamps contain spaces/colons
        import re
        if msgid and (re.search(r"\s", msgid) or re.search(r"[:\\-/]", msgid)):
            # looks like a date/time or not an id -> ignore
            msgid = ''
        # If no msgid, try to create a pseudo-id using subject+snippet (best-effort)
        if not msgid:
            msgid = (subj + '|' + snippet).strip()
        if msgid in seen:
            continue
        seen.add(msgid)

        role = detect_role((subj + ' ' + snippet))
        subj_en = translate_subject(subj)
        snippet_en = translate_subject(snippet)

        # If there's a MessageID and gmail auth worked, fetch message body to extract links
        if msgid and gmail_service:
            try:
                msg = gmail_service.users().messages().get(userId='me', id=msgid, format='full').execute()
                body_text = _gather_message_text(msg.get('payload'))
                link = _extract_all_urls(body_text)
            except Exception:
                link = _extract_first_url_from_text(subj + ' ' + snippet)
        else:
            link = _extract_first_url_from_text(subj + ' ' + snippet)

        # Optionally resolve links and fetch titles
        resolved_links, link_titles = _resolve_links_and_titles(link)

        # Preserve existing link columns from the input if resolver produced nothing
        existing_links = get_col(row, 'Links', 6)
        existing_resolved = get_col(row, 'Resolved Links', 7)
        existing_titles = get_col(row, 'Link Titles', 8)
        if not link and existing_links:
            link = existing_links
        if not resolved_links and existing_resolved:
            resolved_links = existing_resolved
        if not link_titles and existing_titles:
            link_titles = existing_titles

        # Read other columns (timestamp, sender, date) via header mapping or fallback positions
        timestamp = get_col(row, 'Timestamp', 1)
        sender = get_col(row, 'Sender', 2)
        date = get_col(row, 'Date', 3)

        # Build final row matching DEFAULT_HEADERS:
        final_row = [
            msgid,
            timestamp,
            subj_en,
            sender,
            date,
            snippet_en,
            link or '',
            resolved_links or '',
            link_titles or '',
            role,
        ]
        processed_rows.append(final_row)

    # Sort by Role
    header = processed_rows[0]
    body_rows = processed_rows[1:]
    role_idx = DEFAULT_HEADERS.index('Role')
    body_rows.sort(key=lambda r: (r[role_idx] if len(r) > role_idx else ''))
    final_values = [header] + body_rows

    # Write to the Processed Jobs sheet
    sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=f'{PROCESSED_SHEET_NAME}!A:Z'))
    sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{PROCESSED_SHEET_NAME}!A1',
        valueInputOption='USER_ENTERED',
        body={'values': final_values}
    ))
    print(f'Wrote {len(final_values)-1} processed rows to {PROCESSED_SHEET_NAME}')
    # Move backup CSV to Desktop\Job Posts with timestamp
    try:
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        dest_dir = os.path.join(desktop, 'Job Posts')
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.exists(BACKUP_CSV):
            ts = time.strftime('%Y%m%d-%H%M%S')
            dst = os.path.join(dest_dir, f'sheet_backup_{ts}.csv')
            shutil.move(BACKUP_CSV, dst)
            print(f'Moved backup CSV to {dst}')
    except Exception as e:
        print(f'Error moving backup CSV: {e}')


def sort_by_role(sheets_service, spreadsheet_id):
    # Sort by column (A=1). We'll find Role column index first by reading header
    resp = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range='1:1'))
    headers = resp.get('values', [[]])[0]
    if 'Role' not in headers:
        print('Role column not present; skipping sort')
        return
    role_col = headers.index('Role') + 1  # 1-based
    # Use batchUpdate with a SortRangeRequest
    # Find the sheetId for the processed sheet and sort that range
    meta = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id))
    sheet_id = None
    for s in meta.get('sheets', []):
        if s['properties'].get('title') == PROCESSED_SHEET_NAME:
            sheet_id = s['properties'].get('sheetId')
            break
    if sheet_id is None:
        print('Processed sheet not found; skipping sort')
        return
    body = {
        'requests': [
            {
                'sortRange': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 1,
                        'startColumnIndex': 0,
                    },
                    'sortSpecs': [
                        {'dimensionIndex': role_col - 1, 'sortOrder': 'ASCENDING'}
                    ]
                }
            }
        ]
    }
    sheets_execute_with_retry(lambda: sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body))
    print('Sorted sheet by Role (ascending)')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='Do not write changes; just print what would be done')
    return p.parse_args()


def main():
    args = parse_args()
    svc = authenticate_sheets()
    vals = backup_sheet(svc, SHEET_ID, BACKUP_CSV)
    if args.dry_run:
        print('Dry-run mode: processed rows would be computed but not written.')
        # We still compute processed rows to show counts
        # Reuse update_sheet_with_roles but avoid writing by mocking sheets_service with None
        update_sheet_with_roles(svc, SHEET_ID, vals)
        print('Dry-run complete')
        return
    update_sheet_with_roles(svc, SHEET_ID, vals)
    sort_by_role(svc, SHEET_ID)
    print('Done')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'Fatal error: {e}', file=sys.stderr)
        raise
