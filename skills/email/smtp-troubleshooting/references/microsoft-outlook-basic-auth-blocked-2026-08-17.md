# Hotmail/Outlook.com basic-auth blocked — 5.7.139 session (17/08/2026)

Sessione reale: tentativo di collegare `fausto.lelli@hotmail.com` via himalaya.
Esito: **impossibile con password e app password — solo OAuth2 funziona**.
Rilevante per QUALSIASI account Outlook.com/Hotmail consumer dal 2024.

## Sintomi osservati (in ordine)

1. `himalaya envelope list --account hotmail` → `cannot authenticate to IMAP
   server using LOGIN mechanism` / `AUTHENTICATE failed.` (warning: mechanism=Plain)
2. Al secondo tentativo: `login not supported` — il server rifiuta il meccanismo
   LOGIN a monte.
3. App password (2FA attivo) → stesso `AUTHENTICATE failed`.

## Raw probe che ha isolato la causa (IMAP, porta 993)

```
greeting: * OK Microsoft Exchange IMAP4 service ready. ... (tcpproxy/...)
a1 LOGIN fausto.lelli@hotmail.com <pw>        → a1 NO AUTHENTICATE failed.
a1 AUTHENTICATE PLAIN <b64>                    → a1 NO AUTHENTICATE failed.
```

Nessun codice specifico su IMAP — "AUTHENTICATE failed" secco.

## SMTP che ha dato la diagnosi definitiva

`smtp.office365.com:587` + STARTTLS + AUTH LOGIN (banner, EHLO, STARTTLS,
wrap TLS, EHLO, AUTH LOGIN base64):

```
pass: 535 5.7.139 Authentication unsuccessful, basic authentication is
disabled. [MI1PEPF000008CB.ITAP293.PROD.OUTLOOK.COM ...]
```

**`5.7.139` = basic auth disabilitato a livello tenant/account.** L'app
password di Microsoft viaggia ANCORA sul basic auth (solo con token diverso)
→ viene rifiutata allo stesso modo. Il 2FA attivo non cambia nulla.

## Lezione operativa

- Non perdere tempo con password/app-password su Outlook.com/Hotmail consumer:
  il server risponde `NO AUTHENTICATE failed` (IMAP) e `535 5.7.139` (SMTP).
- Unica via: **OAuth2/XOAUTH2** (client-id Azure AD + refresh token). himalaya
  lo supporta (`backend.auth.type = "oauth2"` con access-token/refresh-token cmds).
- Da NON salvare nei log: le password/app-password passate in chiaro dal
  canale di messaggistica vanno trattate come potenzialmente compromesse
  (suggerire rotazione all'utente).

## Config himalaya multi-account usata (pattern)

```toml
[accounts.hotmail]
email = "fausto.lelli@hotmail.com"
backend.type = "imap"
backend.host = "outlook.office365.com"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "fausto.lelli@hotmail.com"
backend.auth.type = "password"
backend.auth.cmd = "/home/fausto/.config/himalaya/hotmail-password"
# ... message.send.backend per smtp.office365.com:587 start-tls ...
folder.aliases.sent = "Sent"
folder.aliases.trash = "Deleted Items"
```

Password via wrapper script (come virgilio):
`~/.config/himalaya/hotmail-password` = `#!/usr/bin/env sh` + `cat hotmail.pass`
(entrambi chmod 600/executable). Nota: himalaya usa `-a <account>` DOPO il
subcomando (`himalaya message send -a libero`), non prima.

## Esito finale sessione

- Virgilio: OK (invariato, default)
- **Libero (fausto.lelli72@libero.it): OK** — IMAP+SMTP con password normale,
  test invio verso Gmail riuscito (`Message successfully sent!`). Alias folder:
  `sent = "outbox"`, `drafts = "draft"`, `trash = "trash"` (i nomi reali Libero)
- Hotmail: bloccato (questo doc)
- Yahoo (fausto.lelli@yahoo.com): `AUTHENTICATE Invalid credentials` con
  password normale → probabile app password richiesta (2FA)
