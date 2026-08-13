# Virgilio / Libero (IOL) SMTP — concrete findings

Session detail from 2026-08-01 diagnosis of `fausto.lelli@virgilio.it`
send failures. IOL = Italia Online, the shared backend for virgilio.it
and libero.it (`smtp-*.iol.local` in banners).

## Endpoint behavior (verified)

| Endpoint | Port | Result |
|---|---|---|
| `smtp.virgilio.it` | 465 (implicit TLS) | ❌ Connection reset by peer |
| `smtp.virgilio.it` | 587 | ❌ Connection reset |
| `smtp.libero.it` | 465 | ❌ Connection reset |
| `smtp.libero.it` | 587 (STARTTLS) | ✅ `220 smtp-*.iol.local ESMTP server ready` |
| `imap.virgilio.it` | 993 | ❌ Connection reset (that day) |

**Rule**: use `smtp.libero.it:587` + STARTTLS, even for virgilio.it
accounts. The TLS cert is `CN=*.libero.it` (Sectigo, Italiaonline
S.p.a.) — clients validating `smtp.virgilio.it` against it fail with
"certificate not valid for name". Same backend, so login is the virgilio
account credentials.

> ⚠️ **Endpoint behavior is VOLATILE day-to-day.** The table above is
> from 2026-08-01. On **2026-08-02** the exact opposite was observed
> from peer70: `smtp.libero.it:465` (implicit TLS) returned
> `535 Invalid User or Password [LIB_300]` while `smtp.virgilio.it:465`
> (implicit TLS) **worked** and sent the message. IMAP
> (`imap.virgilio.it:993`) worked both days — so credentials were never
> the problem. Conclusion: **do not hard-code one "working" IOL host
> from a single day's diagnosis.** If a host gives 535/connection-reset,
> try the sibling host and both ports (465 TLS, 587 STARTTLS) before
> concluding the credentials are wrong.

## Config diff (himalaya config.toml)

```toml
# Before (broken):
message.send.backend.host = "smtp.virgilio.it"
message.send.backend.port = 465
message.send.backend.encryption.type = "tls"

# Working:
message.send.backend.host = "smtp.libero.it"
message.send.backend.port = 587
message.send.backend.encryption.type = "start-tls"
```

## Error sequence observed (in order)

1. `550 User Disabled [smtp-*.iol.local; VIR_440]` — SMTP service
   disabled on the account (user had to re-enable it in webmail). The
   ~100 auto-retries himalaya burned while disabled are what likely
   triggered the rate-limit ban afterwards.
2. `535 Invalid User or Password [LIB_300]` — after re-enablement,
   credentials rejected → actually the anti-bruteforce ban from step 1's
   retries (server reports "invalid" instead of "banned").
3. `454 ... authentication failure : try again` — explicit rate-limit
   response on subsequent attempts.
4. `Unparseable SMTP reply` (himalaya) / `SMTPServerDisconnected`
   (smtplib) — both clients failed even on a healthy server; raw
   openssl ladder worked end-to-end (EHLO 250, AUTH LOGIN 334s).

Lesson: after `550` or `535`, STOP retrying. Wait ≥ 30 min, single
attempt, or test from another host to separate IP-ban from account-ban.

## Working Python fallback (smtplib, 587 + STARTTLS)

```python
import smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formatdate

password = open("~/.config/himalaya/virgilio.pass").read().strip()
m = MIMEText(body, _charset="utf-8")
m["From"] = "fausto.lelli@virgilio.it"
m["To"] = "fausto.lelli@gmail.com"
m["Subject"] = subject
m["Date"] = formatdate(localtime=True)

s = smtplib.SMTP("smtp.libero.it", 587, timeout=30)
s.ehlo(); s.starttls(context=ssl.create_default_context()); s.ehlo()
s.login("fausto.lelli@virgilio.it", password)
s.sendmail("fausto.lelli@virgilio.it", ["fausto.lelli@gmail.com"], m.as_string())
s.quit()
```

Note: this exact script also hit `SMTPServerDisconnected` while the ban
was active — run rung 3 of the ladder first to confirm the ban has
cleared before assuming the code is wrong.
