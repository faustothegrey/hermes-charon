#!/usr/bin/env python3
"""Send harness-first email via Virgilio SMTP - robust version."""
import smtplib, ssl, sys, os
from email.mime.text import MIMEText

def main():
    # Read body file
    body_path = '/tmp/harness_first_email_to_fausto.txt'
    if not os.path.exists(body_path):
        print(f"ERROR: body file not found at {body_path}", file=sys.stderr)
        return 1

    with open(body_path) as f:
        raw = f.read()

    # Read password
    pass_path = os.path.expanduser('~/.config/himalaya/virgilio.pass')
    with open(pass_path) as f:
        password = f.read().strip()

    # Extract body (skip To/Subject headers)
    lines = raw.split('\n')
    blank_idx = next(i for i, l in enumerate(lines) if l.strip() == '')
    body = '\n'.join(lines[blank_idx+1:])

    subject = "Hermes harness-first / stable-operation-first — piano condiviso"

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = 'fausto.lelli@virgilio.it'
    msg['To'] = 'fausto.lelli@gmail.com'
    msg['X-Mailer'] = 'Hermes Agent HMP (peer70)'

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.virgilio.it', 465, context=context, timeout=15) as srv:
        srv.login('fausto.lelli@virgilio.it', password)
        srv.send_message(msg)

    print("EMAIL_SENT_OK")
    return 0

if __name__ == '__main__':
    sys.exit(main())
