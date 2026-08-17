#!/usr/bin/env python3
"""Send G0 bundle v7 zip via Libero SMTP to Hotmail (subject [DEV])."""
import smtplib, ssl, sys, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

ZIP_PATH = os.path.expanduser('~/.hermes/g0-bundle-pre-holdout-v7.zip')

def main():
    if not os.path.exists(ZIP_PATH):
        print(f"ERROR: zip not found at {ZIP_PATH}", file=sys.stderr)
        return 1

    with open(os.path.expanduser('~/.config/himalaya/libero.pass')) as f:
        password = f.read().strip()

    msg = MIMEMultipart()
    msg['Subject'] = '[DEV] G0 FINAL v7 — G2b CLOSED su entrambi i core (remediation review completa), pre-holdout'
    msg['From'] = 'fausto.lelli72@libero.it'
    msg['To'] = 'fausto.lelli@hotmail.com'
    msg['X-Mailer'] = 'Hermes Agent HMP (peer70)'

    body = """📦 Bundle: g0-bundle-pre-holdout-v7.zip
sha 2b940e63f64f8f1029f04e3ed0dbaf7b87f39dc827157b7aaaa9eb375f86dc51
+ sidecar esterno .sha256 (non ricorsivo)

G2b CLOSED su entrambi i core — remediation review completa.

Contenuto dello zip:
- adapter.py (v0.1.4-g0-g2b): UUID v4 per richiesta + _capability_context (provenance esplicita + 22 marker, mai inferiti)
- core-patches/g0-g2b-core-0.17.0-charon-full.patch: CUMULATIVA G0+G2b (sha 29c536a0..., base 0.17.0 @ 7cbae02)
- core-patches/g0-g2b-core-0.20.1-peer141-cumulative.patch: CUMULATIVA G0+G2b (sha 456488eb..., base 0.20.1 @ ddf5763)
- manifest.json: SHA256 di ogni componente, base commit, status
- evidence/g2b/: charon cross-smoke (trace 9c03caf7) + peer141 resmoke (trace 5edabded, post-fix stringa pura)
- test_g0_adapter.py 30/30 + test_g0_plumbing_output.txt 5/5
- report-g0.md v7: remediation completa (3 punti review)

Esito:
- G0 trace/deployment gate: CLOSED
- G2b provenance plumbing peer70/0.17: PASS
- G2b provenance plumbing peer141/0.20.1: PASS (post-fix: stringa pura, root cause dict->str)
- Capability Reuse 2.6.0: ACCEPT preserved (zero modifiche)
- Sealed Phase 1a organic holdout: pronto per GO (decisione Fausto/reviewer)

— peer70 (Charon), 2026-08-17
"""
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(ZIP_PATH, 'rb') as f:
        part = MIMEApplication(f.read(), _subtype='zip')
        part.add_header('Content-Disposition', 'attachment', filename='g0-bundle-pre-holdout-v7.zip')
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.libero.it', 465, context=context, timeout=20) as srv:
        srv.login('fausto.lelli72@libero.it', password)
        srv.send_message(msg)

    print("EMAIL_SENT_OK")
    return 0

if __name__ == '__main__':
    sys.exit(main())
