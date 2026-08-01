# Hermes configuration backup — Raspberry Pi (peer70)

This repository backs up the relevant configuration for the Hermes Agent installation on peer70 (Raspberry Pi).

## What is included

- `config/config.yaml` with secret-looking values redacted
- `config/SOUL.md` and other small Hermes config sidecars
- `skills/` for installed and agent-created Hermes skills
- `cron/` for Hermes scheduled jobs
- `profiles/` without per-profile plaintext secrets, runtime state, or installed binaries
- `plugins/`, `memories/`, `hooks/` when present
- `obsidian-vault/`, a copy of the local Obsidian vault
- `inventory/` command outputs useful during restore/debugging
- `scripts/backup-hermes.sh`, `scripts/generate-backup.py`, and `scripts/restore-hermes.sh`
- `scripts/hermes/` user scripts (netboard, overlay, queue, messaggi)
- `secrets/*.enc`, encrypted secret/state bundle

## What is not committed in plaintext

- `~/.hermes/.env`
- `~/.hermes/auth.json`
- Google OAuth token/client-secret files
- gateway/pairing state
- `state.db`
- private SSH/GPG/API keys

Secrets can be committed only as encrypted artifacts under `secrets/*.enc`.
The current backup uses OpenSSL envelope encryption to the local SSH public key when `scripts/backup-hermes.sh` is run and an RSA SSH public key is available.

Important: if the machine crashes and the matching SSH private key is lost, encrypted secrets cannot be decrypted. Keep an offline copy of the private key, or migrate this repo to a long-term age/GPG recipient.

## Routine backup

```bash
cd ~/Backups/hermes-config
scripts/backup-hermes.sh
```

## Restore

See `RESTORE.md` for the complete restore procedure.
