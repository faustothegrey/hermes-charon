---
name: hermes-backup
category: sysadmin
description: Automate backup of Hermes Agent configuration to GitHub — scripts, envelope encryption, and cron scheduling for config, skills, plugins, memories, and secrets across peers.
version: 1.0.0
author: agent
created_by: agent
platforms: [linux, macos]
triggers:
  - backup hermes
  - hermes configuration backup
  - backup github
  - automate backup
  - encrypt secrets
  - cron backup
  - nightly backup
  - hermes config save
tags:
  - hermes
  - backup
  - github
  - automation
  - cron
  - encryption
  - secrets
  - sysadmin
---

# Hermes Configuration Backup

Pattern for automated backup of Hermes Agent configuration to a private GitHub repository, with envelope encryption of sensitive secrets.

## Architecture

```
schedule: 0 23 * * * (Hermes native cron, no_agent: true)
  └── hermes-config-backup-nightly.sh
        └── scripts/backup-hermes.sh
              ├── scripts/generate-backup.py  (copy + redact directories)
              └── OpenSSL envelope encrypt secrets
                    └── git add + commit + push to GitHub
```

## What to backup

| Directory | Contents | Redaction |
|---|---|---|
| **config/** | config.yaml, SOUL.md, YAML/JSON configs | `<REDACTED>` on secret-looking values |
| **skills/** | All SKILL.md and support files | — |
| **cron/** | Cron job definitions | — |
| **plugins/** | Installed plugins (e.g. HMP) | — |
| **memories/** | Persistent memories | — |
| **hooks/** | Hook scripts | — |
| **profiles/** | Hermes profiles | Without .env, auth.json, state.db*, bin/, sessions/ |
| **inventory/** | `hermes config check`, `hermes tools list`, etc. | Fresh snapshot every run |

## Secrets encryption (envelope)

Sensitive files (.env, auth.json, keys, tokens) are NOT pushed in plaintext:

1. Bundle files into a temp dir → `.tar.gz`
2. Generate random AES-256 key → encrypt the archive (`openssl enc -aes-256-cbc`)
3. Encrypt the AES key with the user's SSH public key RSA (`openssl pkeyutl -encrypt`)
4. Store both `.tar.gz.enc` + `.key.enc` in `secrets/` directory

Decryption requires the matching SSH private key (`~/.ssh/id_rsa`). If lost, secrets are unrecoverable.

## What NOT to backup (in .gitignore)

- `.env`, `auth.json`
- `google_token.json`, `google_client_secret.json`
- `gateway_state.json`, `pairing`
- `state.db*`, sessions/, cache/
- SSH/GPG/API private keys
- `.git/` artifacts, `__pycache__/`, `.pyc`

## Scripts needed

| Script | Purpose |
|--------|---------|
| `scripts/backup-hermes.sh` | Shell wrapper: generate-backup.py → encrypt → git commit → push |
| `scripts/generate-backup.py` | Python: copy dirs, redact configs, generate inventory snapshot |
| `scripts/restore-hermes.sh` | Restore procedure from backup (copies files back + decrypt secrets) |
| `hermes-config-backup-nightly.sh` | Cron wrapper: cd repo → run backup-hermes.sh (lives in ~/.hermes/scripts/) |

## Cron setup

```bash
cronjob action=create \
  name="Nightly Hermes configuration backup" \
  schedule="0 23 * * *" \
  script="hermes-config-backup-nightly.sh" \
  deliver=local \
  no_agent=true
```

- `deliver=local`: saves to filesystem, no notifications
- `no_agent=true`: script-only execution, zero LLM tokens
- The wrapper script simply `cd`s to the repo and runs `scripts/backup-hermes.sh`

## Prerequisites

1. A private GitHub repository (e.g. `hermes-config-peer70`)
2. SSH key on GitHub already configured (`git@github.com:<user>/<repo>.git`)
3. `openssl` (preinstalled on Linux and macOS)
4. `~/.ssh/id_rsa[.pub]` for envelope encryption

## First-time setup

```bash
mkdir -p ~/Backups/hermes-config
cd ~/Backups/hermes-config
git init
git remote add origin git@github.com:<user>/hermes-config-peer70.git
# Copy scripts/ into repo
# Run first backup manually: bash scripts/backup-hermes.sh
# Then set up cron
```

## See also

- `references/peer128-backup-setup.md` — Full working implementation with exact directory structure, encryption commands, and Git workflow from peer128 (macOS)
- `github-repo-management` skill — GitHub repo creation, SSH key setup, cloning
- `cron-operations` skill — Cron job lifecycle (create, update, list, remove)
