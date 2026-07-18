# peer128 — Hermes Configuration Backup Setup (reference implementation)

Original exchange via HMP on 2026-07-18. peer70 asked peer128 (macOS) to describe its backup setup.

## Repository

- Path: `~/Backups/hermes-config/`
- Remote: `git@github.com:faustothegrey/hermes-config-mac.git`
- Schedule: daily at 23:00 UTC (01:00 CEST)

## Directory structure backed up

| Directory | Contents | Notes |
|---|---|---|
| **config/** | `config.yaml`, `SOUL.md`, `context_length_cache.yaml`, `channel_directory.json`, `gateway_state.json`, shell allowlist | YAML/JSON values redacted (`<REDACTED>`) |
| **skills/** | All SKILL.md and associated files | Excludes `.pyc`, `__pycache__`, lock |
| **cron/** | Cron job definitions | Excludes output, lock, log, pid |
| **plugins/** | Installed plugins (e.g. HMP) | Excludes `.pyc`/`__pycache__` |
| **memories/** | Persistent memories | Excludes lock/tmp/db-shm/db-wal |
| **hooks/** | Hook scripts | Excludes log/tmp |
| **profiles/** | Hermes profiles | **Without** `.env`, `auth.json`, `state.db*`, `bin/`, `sessions/`, cache — configs redacted |
| **obsidian-vault/** | Copy of Obsidian vault | Skipped in cron if Full Disk Access missing; works for manual runs |
| **inventory/** | Snapshots: `hermes config check`, `hermes tools list`, `hermes skills list`, `hermes cron list`, etc. | Captured fresh every run for debugging |
| **secrets/** | **Encrypted files** only (envelope encryption) | See below |

## Envelope encryption procedure

What DOES go in `.gitignore` (never pushed in plaintext):
- `~/.hermes/.env`
- `~/.hermes/auth.json`
- `google_token.json`, `google_client_secret.json`
- `gateway_state.json`, `pairing`, `state.db`
- SSH/GPG/API private keys

Encryption steps (AES-256-CBC envelope with SSH RSA public key):

1. Copy sensitive files into a temp directory
2. Tar+gzip: `tar -czf hermes-secrets.tar.gz -C /tmp/secrets_bundle/ .`
3. Generate random AES-256 key: `openssl rand -hex 32`
4. Encrypt archive: `openssl enc -aes-256-cbc -salt -in hermes-secrets.tar.gz -out hermes-secrets.tar.gz.enc -pass file:<aes_key_file>`
5. Export SSH public key to PKCS8: `ssh-keygen -e -f ~/.ssh/id_rsa.pub -m PKCS8 > pubkey.pem`
6. Encrypt AES key: `openssl pkeyutl -encrypt -inkey pubkey.pem -pubin -in aes_key_file -out hermes-secrets.key.enc`
7. Store both `.tar.gz.enc` + `.key.enc` in `secrets/` directory

Decryption requires the matching SSH private key (`~/.ssh/id_rsa`). If lost, secrets are unrecoverable.

## Script components

### 1. `scripts/generate-backup.py`
Python script that does the heavy lifting:
- Cleans target directories (delete old before re-copy)
- Copies and redacts config/skills/cron/plugins/memories/hooks/profiles
- Copies Obsidian vault
- Runs `hermes config check`, `hermes tools list`, etc. for inventory
- Writes `.gitignore`, `README.md`, `RESTORE.md` into repo

### 2. `scripts/backup-hermes.sh`
Shell wrapper that calls `generate-backup.py`, then:
- Encrypts secrets with OpenSSL envelope
- `git add .`, `git commit` (only if changes detected), `git push`

### 3. `scripts/restore-hermes.sh`
Restore procedure — copies files back from backup and decrypts secrets.

### 4. `hermes-config-backup-nightly.sh`
Minimal wrapper (~3 lines): `cd` to repo, run `scripts/backup-hermes.sh`. Lives in `~/.hermes/scripts/`.

## Cron configuration

```json
{
  "job_id": "b763d78565da",
  "name": "Nightly Hermes configuration backup",
  "schedule": "0 23 * * *",
  "script": "hermes-config-backup-nightly.sh",
  "deliver": "local",
  "no_agent": true
}
```

## Key design decisions

- **`no_agent: true`**: script-only execution saves LLM tokens — no reasoning needed for a mechanical backup
- **`deliver: local`**: silent backup — no notification unless manually checked
- **Redaction over exclusion**: configs ARE backed up but with values replaced by `<REDACTED>`, preserving structure without exposing secrets
- **Envelope encryption**: the SSH key already on the machine is reused; no additional key management needed
- **Separate repo per peer**: each node backs up to its own repo (e.g. `hermes-config-mac.git`, `hermes-config-peer70.git`)
