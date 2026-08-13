---
name: smtp-troubleshooting
description: "Diagnose SMTP send failures end-to-end: raw TCP/STARTTLS/AUTH probing with openssl, SMTP error-code decoding (550/535/454), client-vs-provider fault isolation, and Italian ISP (Virgilio/Libero/IOL) quirks."
version: 1.0.0
author: agent
created_by: agent
platforms: [linux, macos]
triggers:
  - email not sending
  - smtp error
  - cannot send email
  - 550 user disabled
  - 535 invalid user
  - 454 try again
  - virgilio smtp
  - libero smtp
  - smtp rate limit
tags:
  - email
  - smtp
  - troubleshooting
  - italian-isp
---

# SMTP Troubleshooting

Ladder for "email won't send" that separates **client bugs** from
**provider problems** from **credential problems** — without guessing.

Related: `himalaya` skill is the CLI tool manual; this skill is the
diagnosis path. On Italian ISP accounts (Virgilio/Libero — same IOL
infrastructure) the provider quirks below are essential.

## The debug ladder (isolate client vs server vs credentials)

Do NOT debug from the mail client alone. Walk up the ladder — each rung
narrows the fault:

### Rung 1 — raw TCP banner (is the port even open?)

```bash
timeout 15 bash -c 'exec 3<>/dev/tcp/smtp.example.com/587 && head -1 <&3'
# expect: 220 ... ESMTP server ready
# "Connection reset by peer" / "No route to host" = provider blocks the port
```

Test multiple ports: **465** (implicit TLS), **587** (STARTTLS), and
IMAP **993** for comparison. If IMAP works but SMTP resets, the provider
is blocking SMTP specifically.

### Rung 2 — EHLO + STARTTLS via openssl (server capability + cert)

```bash
timeout 40 openssl s_client -starttls smtp -connect smtp.example.com:587 -quiet -crlf <<EOF
EHLO test.local
QUIT
EOF
# Expect 250-... lines listing AUTH mechanisms and STARTTLS
```

Certificate check: `CN=*.libero.it` on a `smtp.virgilio.it` hostname is a
**cert-name mismatch** — clients abort with "certificate not valid for
name". Fix: point the client at the host the cert is valid for
(e.g. `smtp.libero.it` even for virgilio.it accounts — same backend).

### Rung 3 — full AUTH via openssl (credentials valid?)

```bash
U64=$(printf '%s' 'user@example.com' | base64)
P64=$(printf '%s' "$PASSWORD" | base64)
timeout 45 bash -c '
exec 3<>/dev/tcp/smtp.example.com/587
IFS= read -t 10 line <&3
printf "EHLO test.local\r\n" >&3; sleep 1
while IFS= read -t 2 r; do case "$r" in *"250 OK"*) break;; esac; done <&3
printf "AUTH LOGIN\r\n" >&3; sleep 1; IFS= read -t 5 r <&3
printf "$U64\r\n" >&3; sleep 1; IFS= read -t 5 r <&3
printf "$P64\r\n" >&3; sleep 2; IFS= read -t 8 r <&3; echo "AUTH REPLY: $r"
printf "QUIT\r\n" >&3'
```

This bypasses ALL client code. If AUTH succeeds here, the client is the
problem. If it fails, the server rejects the credentials.

## SMTP error code decoding

| Code | Meaning | Action |
|---|---|---|
| `550 User Disabled [VIR_440]` | Account's SMTP service disabled by provider | User must re-enable in webmail settings; webmail login works independently of SMTP |
| `535 Invalid User or Password [LIB_300]` | Credentials rejected OR client-side fault | See below — check the **client config before blaming the password**: wrong SMTP host for the account, wrong port/encryption, or a trailing newline in the password file |
| `454 ... authentication failure : try again` | **Anti-bruteforce rate-limit** | Too many failed attempts → IP/account temporarily banned. Wait 20-30 min, then ONE clean attempt |
| `421`/connection reset on 465 | Provider blocks implicit-TLS port | Use 587 + STARTTLS instead |

### Fast isolation: IMAP OK + SMTP 535 → credentials are FINE, fault is client config

If IMAP login succeeds with the same credentials (`himalaya envelope list`
works) but SMTP AUTH returns 535, the account password is **valid** — the
problem is SMTP-specific and almost always in the client config. Check in
order:

1. **Trailing newline in the password file** (most common with himalaya):
   `auth.cmd = "cat ~/.config/himalaya/pass"` pipes the file's trailing
   `\n` into AUTH → server sees password+newline → 535. Fix: use a wrapper
   that strips it:
   ```sh
   #!/usr/bin/env sh
   IFS= read -r pw < /path/to/passfile || true
   printf '%s' "$pw"
   ```
   Point `auth.cmd` at that script (both IMAP and SMTP backends).
2. **Wrong SMTP host for the account**: providers with sibling domains
   (e.g., virgilio.it/libero.it on the same IOL backend) may reject auth
   on one hostname and accept on the other. If 535 persists after the
   newline fix, switch to the sibling host (and try both 465 TLS and
   587 STARTTLS). See `references/virgilio-iol-smtp.md` — endpoint
   behavior is volatile across days.
3. **Rate-limit ban in disguise**: only if auth ALSO fails via raw openssl
   rung 3 from a different host. A 535 that turns into success on the next
   attempt (seconds later, same IP) is NOT a ban — bans last 20-30 min.

A 535 that resolves on the immediate next attempt after a config change
(host/port/password-format) was a client-side fault, not a ban.

⚠️ **Rate-limit self-inflicted**: every retry loop (client auto-retry,
agent retrying on non-zero exit) burns a failed auth and extends the ban.
After `550`/`535`, STOP and investigate — do not hammer. One clean
attempt after cooldown.

### Reactivation ≠ unban (the 550 → 535/454 trap)

Observed on Virgilio: user gets `550 User Disabled`, re-enables SMTP in
webmail, but the next attempt returns `535` then `454 try again`. The
reactivation fixes the account flag — it does NOT clear an in-flight
anti-bruteforce ban accumulated from earlier failed attempts. Also, the
port that was reset before reactivation (465) may still be reset
afterward — the working path can be 587 + STARTTLS + sibling host.
Sequence to expect: `550` (disabled) → re-enable → `535` (still
rate-limited or stale config) → `454` (confirmed ban). Wait out the
cooldown, then ONE clean attempt with the corrected config
(port 587 + `smtp.libero.it` + password file without trailing newline).

## Webmail works but SMTP fails → what it means

Webmail login is a separate service from SMTP relay. "I can send in
webmail" proves account+password for webmail — NOT for SMTP. Possible:
- SMTP service disabled (550) or password is an SMTP-app-specific one
- IP banned by rate-limit (454) — see above
- Provider blocks the port (Rung 1)

## Client-side pitfalls observed

- `himalaya` on some providers fails with `Unparseable SMTP reply` /
  `peer closed connection without sending TLS close_notify` even though
  the server is healthy (verified via ladder rungs 1-3). Fallback:
  Python `smtplib` (same failure possible), then raw openssl, then a
  tiny `smtplib` script that works even when the CLI client doesn't.
- `smtplib.SMTPServerDisconnected` right after connect can also be the
  anti-bruteforce ban in disguise — check rung 3 before blaming the code.

## Distinguish IP-ban vs account-ban

Test the same credentials from a DIFFERENT host (another peer on the
LAN). Works there → the first IP is banned (temporary, cooldown). Fails
too → account-level problem.

## References

- `references/virgilio-iol-smtp.md` — Virgilio/Libero (IOL) concrete
  session detail: port behavior, cert, config diff, and the working
  `smtplib` fallback.
