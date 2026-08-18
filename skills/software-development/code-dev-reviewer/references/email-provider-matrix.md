# Email provider matrix (testato 17-18/08/2026)

## ✅ Libero.it (fausto.lelli72@libero.it) — mittente del review loop
- IMAP: imap.libero.it:993 TLS · SMTP: smtp.libero.it:465 TLS
- Auth: password normale OK (nessun blocco basic auth)
- **Folder alias critico**: il folder \Sent si chiama **`outbox`**. Senza
  `folder.aliases.sent = "outbox"` l'invio va a buon fine ma il salvataggio
  copia fallisce ("cannot add IMAP message").
- Altri alias: drafts=`draft`, trash=`trash`

## ⚠️ Hotmail/Outlook.com (fausto.lelli@hotmail.com) — SOLO destinatario reviewer
- IMAP: outlook.office365.com:993 TLS · SMTP: smtp.office365.com:587 STARTTLS
- **Basic auth disabilitato**: LOGIN e AUTH PLAIN → `NO AUTHENTICATE failed`;
  SMTP → `535 5.7.139 basic authentication is disabled`
- **Le app password NON funzionano** quando il basic auth è spento (usano
  comunque il protocollo basic) — non generarne altre
- Unica via: OAuth2/XOAUTH2 (app Azure AD, scope IMAP.AccessAsUser.All +
  SMTP.Send). MAI usare hotmail per inviare.

## ⚠️ Yahoo (fausto.lelli@yahoo.com) — credenziali rifiutate
- IMAP: imap.mail.yahoo.com:993 · SMTP: smtp.mail.yahoo.com:465
- Password normale → `[AUTHENTICATIONFAILED] Invalid credentials`
- Con 2FA serve app password da Account Security

## Sintassi himalaya (errori frequenti)
- **Ordine flag**: `himalaya message send -a <account>` (flag DOPO il
  subcomando). `himalaya -a ...` o `--account` prima falliscono con
  "unexpected argument"
- Non lette: `himalaya envelope list -a <account> "not flag seen"` (+
  `--output json`)
- **`himalaya message read` marca come letta** → usare `--preview` negli
  script di raccolta
- Marcare letta: `himalaya flag add -a <account> <ID> seen`
- Auth: file password `chmod 600` + wrapper eseguibile `cat <file>.pass`

## Pattern watchdog (review loop)
- Raccolta con `--preview` (non marca), output compatto (JSON + testo)
- Cron LLM ogni 10m: stdout vuoto → risposta `—` (silenzioso); email →
  leggi, interpreta (verdict), azione, POI `flag add seen`, idempotenza via
  file processed-IDs
