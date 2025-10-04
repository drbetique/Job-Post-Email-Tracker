import os
import importlib.util
import pprint

# Load job-tracker.py as a module
jt_path = os.path.join(os.getcwd(), 'job-tracker.py')
spec = importlib.util.spec_from_file_location('job_tracker_mod', jt_path)
job_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_mod)

print('Runtime settings:')
print(' RESOLVE_LINKS =', os.environ.get('RESOLVE_LINKS', 'unset'), '->', job_mod.RESOLVE_LINKS)
print(' MAX_LINKS_PER_MESSAGE =', os.environ.get('MAX_LINKS_PER_MESSAGE', 'unset'), '->', job_mod.MAX_LINKS_PER_MESSAGE)
print(' LINK_WORKERS =', os.environ.get('LINK_WORKERS', 'unset'), '->', job_mod.LINK_WORKERS)
print(' LINK_CACHE_TTL_DAYS =', os.environ.get('LINK_CACHE_TTL_DAYS', 'unset'))
print()

# Authenticate to Gmail
try:
    print('Authenticating to Gmail...')
    gmail = job_mod.authenticate('gmail', ['https://www.googleapis.com/auth/gmail.readonly'], os.environ.get('TOKEN_GMAIL_FILE', 'token_gmail.pickle'))
except Exception as e:
    print('Gmail auth failed:', e)
    raise

# List recent matching messages
print('\nListing messages (GMAIL_QUERY):', getattr(job_mod, 'GMAIL_QUERY', 'not-found'))
res = gmail.users().messages().list(userId='me', q=job_mod.GMAIL_QUERY, maxResults=10).execute()
msgs = res.get('messages', [])
print('Found', len(msgs), 'messages')

# Inspect first up to 5 messages
for i, m in enumerate(msgs[:5]):
    mid = m.get('id')
    print('\n--- Message', i+1, 'id=', mid)
    try:
        details = job_mod.get_email_details(gmail, mid)
        print(' get_email_details returned', len(details), 'fields')
        labels = ['msg_id','timestamp','subject','sender','date','snippet','links','resolved','titles']
        for lab, val in zip(labels, details):
            print(f'  {lab}:', repr(val)[:400])
    except Exception as e:
        print(' Error running get_email_details:', e)

print('\nDiagnostic done.')
