import os
import pickle
import re
import base64
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
try:
    from googletrans import Translator
except Exception:
    Translator = None
import os
try:
    import requests
except Exception:
    requests = None
try:
    from tools.link_cache import get_cached, set_cached
except Exception:
    get_cached = lambda u, ttl=None: None
    set_cached = lambda u, f, t: None

# === CONFIGURATION - CHANGE THIS LINE ===
# Use only the spreadsheetId (the long ID from the sheet URL)
# Example sheet URL: https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
SHEET_ID = os.environ.get('SHEET_ID', '')
if not SHEET_ID:
    raise SystemExit(
        "SHEET_ID is not set. Set it to the spreadsheetId from your Google Sheet URL "
        "(https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit), "
        "for example in PowerShell: setx SHEET_ID <SPREADSHEET_ID>"
    )
# Name of the sheet/tab where processed rows will be placed
PROCESSED_SHEET_NAME = 'Processed Jobs'
DEFAULT_HEADERS = ['MessageID','Timestamp','Subject (EN)','Sender','Date','Snippet (EN)','Links','Resolved Links','Link Titles','Role']

# Configuration: resolve redirects and fetch titles (set RESOLVE_LINKS=0 to disable)
RESOLVE_LINKS = os.environ.get('RESOLVE_LINKS', '1') not in ('0', 'false', 'False')
MAX_LINKS_PER_MESSAGE = int(os.environ.get('MAX_LINKS_PER_MESSAGE', '3'))
TITLE_MAX_BYTES = int(os.environ.get('TITLE_MAX_BYTES', '16384'))
HEAD_TIMEOUT = float(os.environ.get('HEAD_TIMEOUT', '6.0'))
GET_TIMEOUT = float(os.environ.get('GET_TIMEOUT', '8.0'))
LINK_WORKERS = int(os.environ.get('LINK_WORKERS', '5'))
# =======================================

# Gmail search query to find relevant job emails
GMAIL_QUERY = "from:insinooriliitto@duunitori.fi"

def authenticate(service_name, scopes, token_file):
    """Get authenticated service for Gmail or Sheets"""
    creds = None
    
    # Load existing token if it exists (token_file can be a path from env)
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use credentials file (path may be supplied via env var CREDENTIALS_FILE)
            cred_path = os.environ.get('CREDENTIALS_FILE', 'credentials.json')
            flow = InstalledAppFlow.from_client_secrets_file(
                cred_path, scopes
            )
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for next time (token file path may be controlled by env)
        try:
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
        except Exception:
            # If token_file has no directory component, ignore
            pass
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    
    # Build and return the service
    version = 'v1' if service_name == 'gmail' else 'v4'
    return build(service_name, version, credentials=creds)


def sheets_execute_with_retry(request_fn, max_retries=3, initial_backoff=1.0):
    """Execute a Google Sheets request (callable returning a request) with retries/backoff.

    request_fn: zero-arg callable that returns a prepared Google API request (e.g. lambda: svc.spreadsheets().values().get(...))
    """
    import time
    backoff = initial_backoff
    for attempt in range(max_retries):
        try:
            req = request_fn()
            return req.execute()
        except Exception as e:
            # On last attempt, re-raise so caller can handle/log
            if attempt >= max_retries - 1:
                raise
            # Sleep with exponential backoff and retry
            time.sleep(backoff)
            backoff *= 2


def _extract_all_urls(text: str) -> list:
    if not text:
        return []
    urls = re.findall(r"https?://[^\s'\">)]+", text)
    if not urls:
        urls = re.findall(r"www\.[^\s'\">)]+", text)
    # Normalize: ensure http prefix for www links
    normalized = []
    for u in urls:
        if u.startswith('www.'):
            normalized.append('http://' + u)
        else:
            normalized.append(u)
    return normalized


def _gather_message_text(payload) -> str:
    """Recursively gather text content from message payload parts."""
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
                decoded = base64.urlsafe_b64decode(body + '==').decode('utf-8', errors='ignore')
                parts.append(decoded)
            except Exception:
                pass
    return '\n'.join([p for p in parts if p])


def get_email_details(gmail_service, msg_id):
    """Extract key info from an email (includes HTML/plain body parsing for links)."""
    # Fetch full message to access body
    msg = gmail_service.users().messages().get(
        userId='me',
        id=msg_id,
        format='full'
    ).execute()

    # Extract headers
    headers = msg.get('payload', {}).get('headers', [])
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')

    # Snippet still available on message
    snippet = msg.get('snippet', '')[:300]

    # Try to gather any text/html parts and extract first URL
    body_text = _gather_message_text(msg.get('payload'))
    if not body_text:
        # fallback to snippet
        body_text = snippet
    links = _extract_all_urls(body_text)
    links_joined = ';'.join(links)

    resolved_joined = ''
    titles_joined = ''
    if RESOLVE_LINKS and links:
        # Resolve links in parallel (limited by MAX_LINKS_PER_MESSAGE and LINK_WORKERS)
        to_resolve = links[:MAX_LINKS_PER_MESSAGE]
        resolved = [None] * len(to_resolve)
        titles = [None] * len(to_resolve)

        def _resolve_one(idx_link):
            idx, link = idx_link
            final_url = ''
            title = ''
            # Check cache first (respect TTL from env)
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
                resp = requests.head(link, timeout=HEAD_TIMEOUT, allow_redirects=True, headers={'User-Agent': 'JobTrackerBot/1.0'})
                final_url = resp.url
                ctype = resp.headers.get('Content-Type', '')
                want_title = ('html' in ctype.lower())
                if not want_title:
                    want_title = True
                if want_title:
                    try:
                        g = requests.get(final_url or link, timeout=GET_TIMEOUT, stream=True, allow_redirects=True, headers={'User-Agent': 'JobTrackerBot/1.0'})
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
                        # Try to parse OpenGraph / meta tags first using BeautifulSoup if available
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
                            m = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                            if m:
                                title = m.group(1).strip()
                        if title:
                            try:
                                set_cached(link, final_url or link, title)
                            except Exception:
                                pass
                    except Exception:
                        title = ''
            except Exception:
                final_url = ''
                title = ''
            return idx, final_url, title

        with ThreadPoolExecutor(max_workers=LINK_WORKERS) as ex:
            futures = [ex.submit(_resolve_one, (i, to_resolve[i])) for i in range(len(to_resolve))]
            for fut in as_completed(futures):
                try:
                    i, u, t = fut.result()
                    resolved[i] = u
                    titles[i] = t
                except Exception:
                    pass
        resolved_joined = ';'.join([u for u in resolved if u])
        titles_joined = ';'.join([t for t in titles if t])

    return [
        msg_id,                      # Message ID (for deduplication)
        datetime.now().isoformat(),  # Timestamp: When we processed it
        subject,                     # Email subject
        sender,                      # Who sent it
        date,                        # When it was sent
        snippet,                     # Preview of job description
        links_joined,                # Semicolon-separated URLs (or empty)
        resolved_joined,             # Resolved final URLs (semicolon-separated)
        titles_joined                # Link titles (semicolon-separated)
    ]


def detect_role_from_text(text):
    """Simple keyword-based role detection; extend keywords as needed."""
    if not text:
        return 'Other'
    text = text.lower()
    # Prioritize specific roles requested by user
    prioritized = [
        'system specialist',
        'it support',
        'embedded system', 'embedded systems', 'embedded system programming'
    ]
    for kw in prioritized:
        if kw in text:
            # Normalize names
            if 'system specialist' in kw:
                return 'System Specialist'
            if 'it support' in kw:
                return 'IT Support'
            return 'Embedded System Programming'

    # General keywords
    keywords = [
        'data scientist', 'data engineer', 'engineer', 'developer', 'frontend', 'backend',
        'fullstack', 'manager', 'analyst', 'designer', 'lead', 'architect', 'consultant',
        'product', 'qa', 'tester', 'support', 'intern', 'director', 'sales', 'marketing'
    ]
    for kw in keywords:
        if kw in text:
            return kw.title()
    return 'Other'


def translate_subject(text):
    """Translate subject from Finnish to English if possible. Falls back to original text."""
    if not text:
        return ''
    if Translator is None:
        return text
    try:
        trans = Translator()
        res = trans.translate(text, src='fi', dest='en')
        return res.text
    except Exception:
        return text


def translate_text(text, src='fi', dest='en'):
    if not text:
        return ''
    # Prefer Google Cloud Translation API if API key provided
    api_key = os.environ.get('GOOGLE_API_KEY')
    if api_key and requests is not None:
        try:
            url = f'https://translation.googleapis.com/language/translate/v2'
            params = {
                'q': text,
                'source': src,
                'target': dest,
                'format': 'text',
                'key': api_key,
            }
            resp = requests.post(url, data=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data['data']['translations'][0]['translatedText']
        except Exception:
            pass
    # Fallback to googletrans if available
    if Translator is None:
        return text
    try:
        trans = Translator()
        res = trans.translate(text, src=src, dest=dest)
        return res.text
    except Exception:
        return text

def add_to_sheet(sheets_service, sheet_id, row_data):
    """Add a row to Google Sheets"""
    # Keep a tiny retry/backoff in case of transient quota errors
    import time

    max_retries = 3
    backoff = 1
    for attempt in range(max_retries):
        try:
            return sheets_service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range='A1',                  # Start from column A
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row_data]}  # Wrap row in list
            ).execute()
        except Exception as e:
            # If it's a rate limit error, wait and retry
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise

# === MAIN PROGRAM ===
if __name__ == "__main__":
    print(" Checking for job postings from insinooriliitto@duunitori.fi...")
    
    # Authenticate with Gmail (read-only metadata)
    # Use readonly scope so we can use the `q` parameter with messages.list
    gmail_service = authenticate(
        'gmail',
        ['https://www.googleapis.com/auth/gmail.readonly'],
        'token_gmail.pickle'
    )
    
    # Authenticate with Google Sheets (full access)
    sheets_service = authenticate(
        'sheets',
        ['https://www.googleapis.com/auth/spreadsheets'],
        'token_sheets.pickle'
    )
    
    # Search for matching emails
    results = gmail_service.users().messages().list(
        userId='me',
        q=GMAIL_QUERY
    ).execute()

    messages = results.get('messages', [])

    if not messages:
        print(" No new job postings found.")
        exit()

    print(f" Found {len(messages)} job posting(s)!")

    # Ensure the processed sheet exists and read existing message IDs for deduplication
    sheets_metadata = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().get(spreadsheetId=SHEET_ID))
    sheet_names = [s['properties']['title'] for s in sheets_metadata.get('sheets', [])]
    if PROCESSED_SHEET_NAME not in sheet_names:
        # Create the sheet/tab
        add_sheet_body = {
            'requests': [
                {'addSheet': {'properties': {'title': PROCESSED_SHEET_NAME}}}
            ]
        }
        sheets_execute_with_retry(lambda: sheets_service.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=add_sheet_body))

    # Read existing message IDs from the processed sheet (column A)
    existing = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{PROCESSED_SHEET_NAME}!A:A"
    ))
    existing_ids = set(r[0] for r in existing.get('values', []) if r)

    # Ensure headers exist; if the processed sheet header row is empty, write DEFAULT_HEADERS
    header_check = sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{PROCESSED_SHEET_NAME}!A1:Z1"
    ))
    if not header_check.get('values'):
        sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"{PROCESSED_SHEET_NAME}!A1",
            valueInputOption='USER_ENTERED',
            body={'values': [DEFAULT_HEADERS]}
        ))

    # Collect rows and append in a single batched call to reduce write quota usage
    rows_to_write = []

    for msg in messages:
        try:
            if msg['id'] in existing_ids:
                print(f" Skipping already-processed message {msg['id']}")
                continue
            details = get_email_details(gmail_service, msg['id'])
            # detect role from Subject + Snippet
            subj = details[2] if len(details) > 2 else ''
            snippet = details[5] if len(details) > 5 else ''
            role = detect_role_from_text(f"{subj} {snippet}")
            # Translate subject and snippet (best-effort)
            subj_en = translate_subject(subj)
            snippet_en = translate_text(snippet)
            # Prepare final row matching DEFAULT_HEADERS order:
            # ['MessageID','Timestamp','Subject (EN)','Sender','Date','Snippet (EN)','Links','Resolved Links','Link Titles','Role']
            # Details returned by get_email_details are:
            # [msg_id, timestamp, subject, sender, date, snippet, links_joined, resolved_joined, titles_joined]
            final_row = [
                details[0],            # MessageID
                details[1],            # Timestamp
                subj_en,               # Subject (EN)
                details[3],            # Sender
                details[4],            # Date
                snippet_en,            # Snippet (EN)
                details[6] if len(details) > 6 else '',  # Links
                details[7] if len(details) > 7 else '',  # Resolved Links
                details[8] if len(details) > 8 else '',  # Link Titles
                role
            ]
            rows_to_write.append(final_row)
            print(f" Prepared: {subj} -> Role: {role} -> Subject(EN): {subj_en}")
        except Exception as e:
            print(f" Error processing email {msg['id']}: {str(e)}")

    if rows_to_write:
        try:
            # Append rows to the named sheet
            sheets_execute_with_retry(lambda: sheets_service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range=f"{PROCESSED_SHEET_NAME}!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': rows_to_write}
            ))
            print(f" Added {len(rows_to_write)} rows to the '{PROCESSED_SHEET_NAME}' sheet.")
        except Exception as e:
            print(f" Error writing to sheet: {str(e)}")
        # Export the processed sheet to CSV
        try:
            resp = sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=f"{PROCESSED_SHEET_NAME}!A:Z").execute()
            vals = resp.get('values', [])
            import csv
            # Write directly to the user's Desktop\Job Posts folder with UTF-8 BOM
            desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
            dest_dir = os.path.join(desktop, 'Job Posts')
            os.makedirs(dest_dir, exist_ok=True)
            export_path = os.path.join(dest_dir, 'processed_jobs_export.csv')
            # Use utf-8-sig so Excel/Windows opens with correct UTF-8 encoding
            with open(export_path, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                for r in vals:
                    w.writerow(r)
            print(f'Exported Processed Jobs to {export_path}')
        except Exception as e:
            print(f'Error exporting CSV: {e}')
        # Move CSV to Desktop\Job Posts
        try:
            import shutil
            desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
            dest_dir = os.path.join(desktop, 'Job Posts')
            os.makedirs(dest_dir, exist_ok=True)
            src = os.path.join(os.getcwd(), 'processed_jobs_export.csv')
            dst = os.path.join(dest_dir, 'processed_jobs_export.csv')
            shutil.move(src, dst)
            print(f'Moved CSV to {dst}')
        except Exception as e:
            print(f'Error moving CSV: {e}')
    
    print("All done! Check your Google Sheet.")

    # Post-run: verify export, re-export if needed, and convert to XLSX
    try:
        print('Running post-run verification and conversion...')
        import subprocess
        subprocess.call(['python', 'verify_and_fix_export.py'])
        subprocess.call(['python', 'csv_to_xlsx.py'])
        print('Post-run verification and conversion complete.')
    except Exception as e:
        print('Post-run steps failed:', e)