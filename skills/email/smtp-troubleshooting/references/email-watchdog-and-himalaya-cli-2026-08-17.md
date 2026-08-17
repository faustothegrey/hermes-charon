# Email watchdog & himalaya CLI quirks — 2026-08-17

Sessione reale: setup multi-account himalaya (Virgilio + Libero + Hotmail +
Yahoo), test di invio, e un cron watchdog "agente attivo" per la casella
Libero. Dettaglio operativo che non sta nel corpo della skill.

## Account working (Libero) — config himalaya

`~/.config/himalaya/config.toml`, sezione `[accounts.libero]`:

```toml
[accounts.libero]
email = "fausto.lelli72@libero.it"
display-name = "Fausto Lelli"

backend.type = "imap"
backend.host = "imap.libero.it"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "fausto.lelli72@libero.it"
backend.auth.type = "password"
backend.auth.cmd = "/home/fausto/.config/himalaya/libero-password"

message.send.backend.type = "smtp"
message.send.backend.host = "smtp.libero.it"
message.send.backend.port = 465
message.send.backend.encryption.type = "tls"
message.send.backend.login = "fausto.lelli72@libero.it"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "/home/fausto/.config/himalaya/libero-password"

# Libero: il folder \Sent si chiama "outbox" (vedi `himalaya folder list`)
folder.aliases.inbox = "INBOX"
folder.aliases.sent = "outbox"
folder.aliases.drafts = "draft"
folder.aliases.trash = "trash"
```

Pattern password (stesso per ogni account): file `~/.config/himalaya/<acct>.pass`
con la password pura (chmod 600) + wrapper eseguibile `<acct>-password`:

```sh
#!/usr/bin/env sh
cat /home/fausto/.config/himalaya/<acct>.pass
```

⚠️ Se himalaya invia ma poi fallisce con `cannot add IMAP message` /
`stream error`, è l'alias del folder `sent` sbagliato (non trova "Sent").
Libero usa `outbox`. L'email in realtà è stata INVIATA (SMTP è già passato)
— è solo il salvataggio della copia che fallisce. Correggere l'alias, non
ritentare l'invio (duplicherebbe l'email).

## himalaya CLI — sintassi e flag (verificati 2026-08-17)

- **`-a/--account` va DOPO il subcomando**, non prima:
  - ✅ `himalaya envelope list -a libero "not flag seen"`
  - ✅ `himalaya message send -a libero` (con messaggio via stdin)
  - ✅ `himalaya flag add -a libero <ID> seen`
  - ❌ `himalaya -a libero ...` / `himalaya --account libero ...` → "unexpected argument"
- **Query "non lette"**: `"not flag seen"` (⚠️ `"not seen"` fallisce con
  "cannot parse search emails query").
- **Leggere senza marcare come letta**: `himalaya message read -a libero --preview <ID>`.
  `message read` SENZA `--preview` applica il flag `seen` automaticamente.
- **Marcare come letta**: `himalaya flag add -a libero <ID> seen`.
- **Output strutturato**: `--output json` su `envelope list` → array con
  `id`, `flags`, `subject`, `from.addr`, `date`, `has_attachment`.
- Controllo account: `himalaya account list` (nome + backends + default).

## Pattern watchdog email "agente attivo" (cron)

Obiettivo: leggere le email non lette, INTERPRETARLE, agire di conseguenza
(es. registrare un verdetto, eseguire un'azione), poi marcarle come lette.
Silenzioso quando non c'è nulla.

### 1. Script raccoglitore (`~/.hermes/scripts/watchdog-libero-mail.sh`)

Stampa SOLO se ci sono email non lette (stdout vuoto = silenzio):

```bash
#!/usr/bin/env bash
set -u
UNREAD=$(himalaya envelope list -a libero --output json "not flag seen" 2>/dev/null)
if [ -z "$UNREAD" ] || [ "$UNREAD" = "[]" ]; then exit 0; fi
echo "UNREAD_COUNT=$(echo "$UNREAD" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
echo "$UNREAD" | python3 -c "
import json, sys
for e in json.load(sys.stdin):
    print(f\"ID={e['id']} | SUBJECT={e.get('subject','')} | FROM={e.get('from',{}).get('addr','?')} | DATE={e.get('date','')}\")
"
echo "---FULL TEXT---"
for ID in $(echo "$UNREAD" | python3 -c "import json,sys; print(' '.join(str(e['id']) for e in json.load(sys.stdin)))"); do
  echo "=== EMAIL ID $ID ==="
  himalaya message read -a libero --preview "$ID" 2>/dev/null   # --preview: NON marca seen
  echo
done
```

### 2. Cron job LLM (non `no_agent`)

- `schedule: every 10m`, `script: watchdog-libero-mail.sh` (stdout iniettato
  nel prompt), `deliver: origin`.
- Prompt (essenziale, self-contained):
  - se lo stdout è vuoto → rispondere solo `—` e fermarsi;
  - se ci sono email → leggere, interpretare, AGIRE (es. "verdetto
    registrato" nel report/stato di progetto), poi marcare come letta con
    `himalaya flag add -a libero <ID> seen`;
  - riepilogo conciso in italiano: quante, da chi, oggetto, azione eseguita;
  - sicurezza: mai provenance organic_live per traffico creato per raccogliere
    evidence; azioni ambigue/rischiose → riportare a Fausto senza eseguire.
- `--preview` nel raccoglitore è CRITICO: senza, lo script marcherebbe le
  email come lette prima che l'agente le veda/agisca.

## Diagnosi rapida credenziali (riepilogo 2026-08-17)

| Provider | Risultato | Causa |
|---|---|---|
| Virgilio | ✅ funziona | password plain, IOL backend |
| Libero | ✅ funziona (test invio OK) | password plain, alias sent=outbox |
| Hotmail | ❌ `535 5.7.139` / `AUTHENTICATE failed` | basic auth disabilitato → solo OAuth2 |
| Yahoo | ❌ `AUTHENTICATE Invalid credentials` | app password se 2FA (o password diversa) |
