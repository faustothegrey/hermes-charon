# Email provider quirks (himalaya multi-account) — verified 17/08/2026

Setup reale su peer70: `~/.config/himalaya/config.toml` con account
`virgilio` (default), `libero`, `hotmail`, `yahoo`. Password in
`~/.config/himalaya/<acct>.pass` (chmod 600), lette da uno script
`<acct>-password` che fa `cat <acct>.pass` (pattern: script eseguibile
+ file password separato, come virgilio).

## Stato account (verificato live)

| Account | IMAP | SMTP | Esito |
|---------|------|------|-------|
| virgilio (default) | ✅ imap.virgilio.it:993 | ✅ smtp.virgilio.it:465 SSL | OK, invariato |
| libero `fausto.lelli72@libero.it` | ✅ imap.libero.it:993 | ✅ smtp.libero.it:465 SSL | OK, funzionante |
| hotmail `fausto.lelli@hotmail.com` | ❌ | ❌ | **basic auth disabilitato** |
| yahoo `fausto.lelli@yahoo.com` | ❌ | — | credenziali rifiutate |

## Microsoft / Outlook / Hotmail — basic auth disabilitato (5.7.139)

- IMAP `outlook.office365.com:993` raggiungibile, greeting OK, ma
  `a1 LOGIN ...` → `NO AUTHENTICATE failed` e `AUTHENTICATE PLAIN` idem.
- SMTP `smtp.office365.com:587` (STARTTLS! non SSL diretto) → dopo
  `AUTH LOGIN` + user + pass: `535 5.7.139 Authentication unsuccessful,
  basic authentication is disabled`.
- Da settembre 2024 Microsoft disabilita il basic auth per i consumer;
  anche le **app password** vengono rifiutate se il tenant/account ha
  basic auth spento (l'app password usa comunque basic auth).
- **Unica via: OAuth2 (XOAUTH2)** — registrare app in Azure AD con
  `https://outlook.office.com/IMAP.AccessAsUser.All` + `SMTP.Send`,
  configurarlo in himalaya come `backend.auth.type = "oauth2"`.
- Nota: un account consumer "Pippo Baudo <fausto.lelli@hotmail.com>" può
  comunque fungere da **destinatario** del reviewer (invio da altro account).

## Yahoo

- IMAP `imap.mail.yahoo.com:993` OK, supporta `AUTH=PLAIN AUTH=XOAUTH2
  AUTH=OAUTHBEARER`; login con password normale →
  `NO [AUTHENTICATIONFAILED] AUTHENTICATE Invalid credentials`.
- Serve app password (2FA) o OAuth2.

## Libero — folder aliases (pitfall sent-folder)

- Il folder \Sent si chiama **`outbox`** (non "Posta Inviata"!). Senza
  alias corretto, `message send` fallisce con `cannot add IMAP message /
  stream error / unexpected tag in command completion result` DOPO aver
  già inviato l'email (duplicato se si ritenta!). Aliases corretti:
  `sent = "outbox"`, `drafts = "draft"`, `trash = "trash"`.
- Invio di test riuscito: `himalaya message send -a libero` con body
  piped (From/To/Subject + corpo).

## Flag/opzioni himalaya utili

- **Leggere senza marcare come letta**: `himalaya message read -a <acct>
  --preview <ID>` — senza `--preview` la lettura applica il flag `seen`
  automaticamente (rompe il pattern raccolta→azione→mark).
- **Marcare come letta**: `himalaya flag add -a <acct> <ID> seen`.
- **Filtro non lette**: `himalaya envelope list -a <acct> --output json
  "not flag seen"` (la sintassi `not seen` non funziona).
- **Posizione flag account**: `-a <acct>` va DOPO il subcomando
  (`himalaya message send -a libero`); `himalaya -a libero message send`
  fallisce con `unexpected argument`. `envelope list` accetta `--account`
  prima o dopo indifferentemente.
- **Connettività SMTP**: porta 587 = STARTTLS (non SSL diretto); porta
  465 = SSL diretto. Script python di test: dopo `STARTTLS` va
  ri-creato il socket SSL con `server_hostname`.
- Verifica connettività senza credenziali: `echo QUIT | openssl
  s_client -connect <host>:993` per IMAP.

## Sicurezza

- Le password passate in chiaro su Telegram (es. `Risocotto10!` usata per
  più account) vanno considerate compromesse → consigliare cambio o app
  password. Le password vanno solo nel file `.pass` chmod 600, mai nei log.
