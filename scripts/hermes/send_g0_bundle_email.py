#!/usr/bin/env python3
"""Send G0 bundle zip via Virgilio SMTP to Gmail."""
import smtplib, ssl, sys, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

ZIP_PATH = os.path.expanduser('~/.hermes/g0-bundle-review.zip')

def main():
    if not os.path.exists(ZIP_PATH):
        print(f"ERROR: zip not found at {ZIP_PATH}", file=sys.stderr)
        return 1

    with open(os.path.expanduser('~/.config/himalaya/virgilio.pass')) as f:
        password = f.read().strip()

    msg = MIMEMultipart()
    msg['Subject'] = 'G0 bundle review — HMP trace_id chain (Charon 0.17.0 + peer141 0.20.1)'
    msg['From'] = 'fausto.lelli@virgilio.it'
    msg['To'] = 'fausto.lelli@gmail.com'
    msg['X-Mailer'] = 'Hermes Agent HMP (peer70)'

    body = """G0 bundle per review — request-unique trace_id (P0-10) end-to-end.

Contenuto dello zip:
- adapter.py (v0.1.4-g0): UUID v4 per richiesta nel consumer_loop, propagato a MessageEvent.trace_id
- core-patches/g0-core-0.17.0-charon.patch: 5 file core, 22 inserzioni
  (MessageEvent.trace_id + AIAgent._trace_id + kwargs pre_llm_call + agent-cache refresh)
- manifest.json: SHA256 di ogni componente, compat core, trace live test
- test_g0_adapter.py: regressione 30/30 PASS + plumbing 4/4 PASS
- report-g0.md: report completo

Test live (entrambi i core):
- Charon: feb389c2-fc48-4e29 / b16e9a29-5c4b-42ff — stesso UUID in HMP ingress e capability-reuse retrieval
- peer141: 96accdbf-7da3-46ab — stesso UUID in tutta la catena

Note:
- capability-reuse 2.6.0 NON modificata (ACCEPT preservata)
- Patch 0.20.1 applicata da peer141 con ancoraggi diversi (nessun file core scambiato)
- Shadow, niente active rollout
- zip sha256: 0547ee9dcccded526526d7de81595ce1bb2ecb69c03bc172c38cd471527a460f

— peer70 (Charon), 2026-08-16
"""
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(ZIP_PATH, 'rb') as f:
        part = MIMEApplication(f.read(), _subtype='zip')
        part.add_header('Content-Disposition', 'attachment', filename='g0-bundle-review.zip')
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.virgilio.it', 465, context=context, timeout=20) as srv:
        srv.login('fausto.lelli@virgilio.it', password)
        srv.send_message(msg)

    print("EMAIL_SENT_OK")
    return 0

if __name__ == '__main__':
    sys.exit(main())
