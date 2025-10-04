import os, importlib.util
jt_path = os.path.join(os.getcwd(), 'job-tracker.py')
spec = importlib.util.spec_from_file_location('job_mod', jt_path)
job_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_mod)

gmail = job_mod.authenticate('gmail', ['https://www.googleapis.com/auth/gmail.readonly'], os.environ.get('TOKEN_GMAIL_FILE','token_gmail.pickle'))
res = gmail.users().messages().list(userId='me', q=job_mod.GMAIL_QUERY, maxResults=5).execute()
msgs = res.get('messages', [])
for m in msgs:
    d = job_mod.get_email_details(gmail, m['id'])
    subj = d[2] if len(d) > 2 else ''
    snippet = d[5] if len(d) > 5 else ''
    role = job_mod.detect_role_from_text(f"{subj} {snippet}")
    subj_en = job_mod.translate_subject(subj)
    snippet_en = job_mod.translate_text(snippet)
    final_row = [
        d[0], d[1], subj_en, d[3], d[4], snippet_en,
        d[6] if len(d) > 6 else '', d[7] if len(d) > 7 else '', d[8] if len(d) > 8 else '', role
    ]
    print('FINAL ROW:')
    for i, v in enumerate(final_row):
        print(i, repr(v)[:200])
    print('---')
