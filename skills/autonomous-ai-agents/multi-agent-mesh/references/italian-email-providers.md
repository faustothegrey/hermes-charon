# Italian Email Provider Configuration (Virgilio)

Covers provider-specific settings for Italian email services (Virgilio, Libero, TIM, etc.) when configuring Himalaya email client.

## Virgilio (ItalyMail / Telecom Italia Mail)

### SMTP: Port 465 (Direct TLS), NOT 587 (STARTTLS)

Virgilio's SMTP server (`smtp.virgilio.it`) uses **direct TLS on port 465**, not STARTTLS on port 587. The himalaya config must reflect this:

```toml
message.send.backend.type = "smtp"
message.send.backend.host = "smtp.virgilio.it"
message.send.backend.port = 465
message.send.backend.encryption.type = "tls"          # NOT "start-tls"!
message.send.backend.login = "fausto.lelli@virgilio.it"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "/home/fausto/.config/himalaya/virgilio-password"
```

### IMAP: Standard

```toml
backend.type = "imap"
backend.host = "imap.virgilio.it"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "fausto.lelli@virgilio.it"
backend.auth.type = "password"
backend.auth.cmd = "/home/fausto/.config/himalaya/virgilio-password"
```

### Italian Folder Names

Virgilio uses localized Italian folder names:

```toml
folder.aliases.inbox = "INBOX"
folder.aliases.sent = "Posta Inviata"
folder.aliases.drafts = "Bozze"
folder.aliases.trash = "Cestino"
```

Without these aliases, `himalaya message send` will fail after SMTP delivery because it cannot save the sent message to the default `Sent` folder (which doesn't exist on the server).

## Password Storage (Wrapper Script Pattern)

When `pass` or system keyring aren't available, use a two-file pattern:

### 1. Password file (plaintext, restricted permissions)

Path: `~/.config/himalaya/<account>.pass`

```
Risocotto10!
```

Permissions: `chmod 600`

### 2. Shell script wrapper (reads and prints password)

Path: `~/.config/himalaya/<account>-password`

```sh
#!/usr/bin/env sh
set -eu
pw_file="/home/fausto/.config/himalaya/<account>.pass"
if [ ! -r "$pw_file" ]; then
  echo "Password file not found: $pw_file" >&2
  exit 1
fi
IFS= read -r pw < "$pw_file" || true
printf '%s' "$pw"
```

Permissions: `chmod +x`

Referenced in config.toml as:
```toml
backend.auth.cmd = "/home/fausto/.config/himalaya/<account>-password"
```

## SMTP Rate-Limit Trap

Virgilio SMTP enforces aggressive rate-limiting. When himalaya sends to an invalid domain (e.g. `gmail.dom`), it retries 20+ times, causing the server to issue:

```
451 too many invalid recipients [smtp-45.iol.local; VIR_660]
```

This bans the **entire source IP** for 30+ minutes. All subsequent sends fail, even to valid addresses. IMAP (read) is unaffected.

**Recovery:** wait 30-60 minutes for the IP-level ban to expire; sending from a different peer with a different public IP also works.
**Prevention:** validate recipient domain before sending with `host -t MX <domain>`. If the MX lookup fails, the domain is invalid and sending would trigger the ban.

## SMTP Port 587 STARTTLS Certificate Warning

Virgilio's `smtp.virgilio.it` on port 587 (STARTTLS) presents a certificate valid for `*.libero.it` and `libero.it`, NOT for `smtp.virgilio.it`. Himalaya (and any client doing strict hostname verification) will reject the connection:

```
TLS error: invalid peer certificate: certificate not valid for name "smtp.virgilio.it";
certificate is only valid for DnsName("*.libero.it") or DnsName("libero.it")
```

**Fix:** Use port 465 (direct TLS) instead. The certificate on 465 correctly matches `*.virgilio.it`.

## smtp.libero.it vs smtp.virgilio.it — Separate Endpoints

Despite serving the same underlying infrastructure (Italiaonline), `smtp.libero.it` and `smtp.virgilio.it` resolve to **different IP addresses** and use **separate authentication realms**:

| Hostname | IP | Auth Realm | Cert Name |
|----------|-----|------------|-----------|
| `smtp.virgilio.it` | 213.209.1.145 | Virgilio accounts | `*.virgilio.it` |
| `smtp.libero.it` | 213.209.1.144 | Libero accounts | `*.libero.it` |

Virgilio credentials (`fausto.lelli@virgilio.it`) will fail with `535 Invalid User or Password` on `smtp.libero.it`. Always use the server matching your email domain.