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
| **scripts/hermes/** | User scripts (netboard, overlay, queue, messaggi cron) | — |
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

## ⚠️ Pitfall: state.db leaked into the secrets bundle → GitHub push rejected

`state.db` (the session store) grows to 1GB+ on busy gateway nodes. If it
creeps into the **encrypted secrets bundle**, the resulting
`secrets/hermes-secrets.tar.gz.enc` exceeds GitHub's **100MB per-file
limit** and the push is rejected (`remote: error: GH001: Large files
detected` / `pre-receive hook declined`). The nightly cron then fails
silently — `last_status: error` in `hermes cron list`, no alert.

This actually shipped: both `scripts/generate-backup.py`
(`secret_candidates` list) AND `scripts/backup-hermes.sh` (the `for item
in ...` loop) had `state.db` in their lists, contradicting the SKILL.md
"not to backup" table above. **When debugging a failing backup, grep
BOTH scripts for `state.db` / oversized paths — the docs and the code
drift.**

Remove it from both places; a healthy bundle is a few KB (env, auth,
keys), not hundreds of MB.

### Repairing an oversized commit already in local history

If a >100MB blob was committed locally (push rejected), rewrite the last
commit so the blob never reaches the remote:

```bash
cd ~/Backups/hermes-config
# remove the offending encrypted files from disk + index
rm -f secrets/hermes-secrets.tar.gz.enc secrets/hermes-secrets.key.enc secrets/hermes-secrets.key.pub
git rm -q --cached secrets/hermes-secrets.tar.gz.enc secrets/hermes-secrets.key.enc secrets/hermes-secrets.key.pub 2>/dev/null
# squash-rewrite: reset soft to the last GOOD commit, re-stage everything, recommit
git reset --soft <last_good_sha>
git add -A
git commit -m "backup: update Hermes configuration — $(date '+%Y-%m-%dT%H:%M:%S%z')"
# verify no blob > 50MB remains in the NEW history before pushing
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3>50000000 {print $3, $4}'
git push
```

`git reset --soft` to the last good commit + recommit keeps the rest of
the changes while dropping the oversized blob from the branch head. Then
regenerate the bundle with the fixed scripts (few KB) and recommit.

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

## Cross-platform validation

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** (peer128) | ✅ Production | `hermes-config-mac.git` — daily cron since 2026-07 |
| **Linux/arm64** (peer70, Raspberry Pi) | ✅ Production | `faustothegrey/hermes-charon.git` — daily cron since 2026-07-18 |

The pattern is identical across platforms. Only platform-specific adjustments:
- On macOS, Obsidian vault may need Full Disk Access (FDA) for cron
- On Linux, `openssl` and `ssh-keygen` are preinstalled
- Both use same script set (generate-backup.py + backup-hermes.sh)

## Pitfall: state.db must NEVER be in the secrets bundle

**The bug that silently killed a nightly backup:** `state.db` (the SQLite
session store) grows to GBs over time. If it's added to the secrets
bundle, the encrypted `secrets/hermes-secrets.tar.gz.enc` balloons past
GitHub's **100 MB per-file limit** → `git push` is rejected
(`GH001: Large files detected` / `remote: error: File ... exceeds
GitHub's file size limit of 100.00 MB`) → the nightly job reports
`last_status: error` forever with no obvious cause.

This happened on peer70 (Charon): state.db was 1.18 GB → .enc was
322 MB → nightly failing since the bundle crossed the limit.

**Both scripts must exclude it** — a fix in only one is not enough:
- `scripts/generate-backup.py`: `secret_candidates` list
- `scripts/backup-hermes.sh`: the `for item in ...` loop

### Audit checklist (run when backup misbehaves)

```bash
# 1. Did the last nightly run fail?
#    cronjob action=list → look for "Nightly Hermes configuration backup"
#    with last_status: error

# 2. Is the secrets bundle oversized?
ls -la secrets/*.enc   # >100 MB = will be rejected by GitHub

# 3. Does the git history carry an oversized blob?
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3>50000000 {print $3, $4}'
```

### Recovery: rewrite history to drop the oversized blob

If a commit containing the giant .enc was already made locally (push
rejected), reset the branch to the last good commit, re-stage everything
except the blob, and recommit:

```bash
git reset --soft <last_good_commit>
git rm -q --cached secrets/hermes-secrets.tar.gz.enc secrets/hermes-secrets.key.enc secrets/hermes-secrets.key.pub
git add -A
git commit -m "backup: update Hermes configuration (fix: exclude state.db)"
# Verify no blob >50MB remains in the new history, then push
git push
```

Then re-generate the bundle WITHOUT state.db (fresh .enc should be KBs,
not MBs) and commit+push again. Verify remote HEAD moved:
`git log --oneline origin/main -1`.

## Pitfall: state.db slipped into the secrets bundle (GitHub 100MB limit)

**Symptom:** nightly backup shows `last_status: error`; manual push fails with
`remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this
exceeds GitHub's file size limit of 100.00 MB` / `GH001: Large files detected`.

**Root cause:** the deployed `scripts/backup-hermes.sh` (the `for item in ...`
loop) and `scripts/generate-backup.py` (`secret_candidates` list) had
`state.db` added at some point. state.db is the SQLite session store and can
reach 1.2GB+ on a busy gateway — tar.gz'd + AES-encrypted it still blows past
100MB. `state.db*` is explicitly in the skill's "What NOT to backup" table:
it is runtime state, not configuration.

**Fix (both files — they duplicate the list):**
- Remove `state.db` from the `for item in` loop in `backup-hermes.sh`
- Remove `"state.db"` from `secret_candidates` in `generate-backup.py`

**Clean the giant blob out of git history** (it was already committed locally):
```bash
git reset --soft <last-good-commit>     # e.g. the last pushed commit
git rm -q -r --cached .                 # unstage everything
git add -A
git commit -m "backup: ... (fix: exclude state.db)"
# Verify no blob >50MB remains in the NEW history:
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3>50000000 {print $3, $4}'
git push
```
Secrets bundle after fix: ~10KB instead of 322MB.

**Diagnostic note:** the nightly cron job's `last_status: error` (visible via
`cronjob action=list`) is the earliest signal — check it if backups stop
arriving. Also: `hermes sessions prune --older-than N --yes` + `VACUUM` keeps
state.db small in the first place (see `hermes-session-lifecycle` skill).

## See also

- `references/peer128-backup-setup.md` — Full working implementation with exact directory structure, encryption commands, and Git workflow from peer128 (macOS)
- `github-repo-management` skill — GitHub repo creation, SSH key setup, cloning
- `cron-operations` skill — Cron job lifecycle (create, update, list, remove)
