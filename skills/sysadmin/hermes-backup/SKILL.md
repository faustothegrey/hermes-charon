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

> ⚠️ **Pitfall:** `state.db` has crept into `secret_candidates` (generate-backup.py)
> and the `for item in ...` loop (backup-hermes.sh) before — a 1GB+ state.db
> makes `secrets/*.tar.gz.enc` exceed GitHub's 100MB per-file limit and the
> nightly push fails silently (`last_status: error`). Keep it OUT of both
> scripts. Full diagnosis + history rewrite: `references/secrets-bundle-state-db-bloat.md`.

## ⚠️ Pitfall: state.db crept into the secrets bundle and broke the nightly

`~/.hermes/state.db` (the session store) can reach 1+ GB. If it ends up in the
encrypted secrets bundle (it did on peer70 — someone added it to
`secret_candidates` and the shell `for item in ...` loop), the tar.gz.enc becomes
hundreds of MB, **exceeds GitHub's 100 MB per-file limit, and every nightly push
fails with `GH001: Large files detected` / `pre-receive hook declined`** while
`last_status: error` in the cron list. `state.db` is runtime state, not a secret
— it must stay out of the bundle.

**Diagnosis when the nightly fails:** check the backup repo for large blobs:
`git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000 {print $3, $4}'`
and inspect `secrets/*.enc` sizes.

**Fix:** remove `state.db` from BOTH places (`generate-backup.py`
`secret_candidates` list AND the `for item in` loop in `backup-hermes.sh`), then
purge the oversized blob from git history before the next push:
`git reset --soft <last-good-commit> && git rm -q -r --cached . && git add -A && git commit -m "fix: exclude state.db"`.
Verify no >50 MB blob remains, then re-encrypt the bundle (it should drop from
~300 MB to ~10 KB) and push. Re-run the cron job manually to confirm
`last_status: ok`.

## Scripts needed

`state.db` cresce fino a 1GB+ dopo mesi di sessioni. Se finisce nei
`secret_candidates` (generate-backup.py) O nel loop `for item in ...`
(backup-hermes.sh), il `hermes-secrets.tar.gz.enc` supera il limite
GitHub di **100MB/file** → il push viene rifiutato con
`GH001: Large files detected` e il nightly fallisce silenziosamente
(`last_status: error`). Il file .enc è AES-encrypted quindi NON si
comprime nel pack — 322MB di input restano 322MB.

**Verifica dopo ogni modifica agli script** — grep per `state.db` in
ENTRAMBI i file:
```bash
grep -n "state.db" ~/Backups/hermes-config/scripts/generate-backup.py \
                   ~/Backups/hermes-config/scripts/backup-hermes.sh
```
Il secrets bundle sano è pochi KB, non centinaia di MB. Il manifest
(`secrets/MANIFEST.json`) deve elencare solo `.env`, `auth.json`,
`google_token.json`, `google_client_secret.json`, `gateway_state.json`,
`pairing`.

**Recupero dopo un push fallito** — il commit locale contiene già il blob
enorme; riscrivi la history PRIMA di ripushare:
```bash
git reset --soft <ultimo-commit-valido>      # es. il primo commit del repo
git rm -q -r --cached .                       # untrack tutto
git add -A && git commit -m "..." && git push
# verifica che non restino blob >50MB:
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3>50000000 {print $3, $4}'
```

## ⚠️ Pitfall critico: state.db nel secrets bundle → backup nightly rotto

`state.db` (SQLite delle sessioni) può crescere a **>1GB** (sessioni HMP
enormi, sessioni Telegram vecchie). Se finisce nel secrets bundle, il
`secrets/hermes-secrets.tar.gz.enc` supera il **limite GitHub di 100MB/file**
e il push fallisce con `GH001: Large files detected`. Sintomo: il cron
nightly mostra `last_status: error` ma non c'è alcun alert all'utente.

**Controllo rapido**: `ls -la ~/Backups/<repo>/secrets/*.enc` → se il
`.tar.gz.enc` è centinaia di MB, è rotto (sano = KB).

**Fix**:
1. Rimuovere `state.db` da `secret_candidates` in `scripts/generate-backup.py`
   E dalla lista `for item in ...` in `scripts/backup-hermes.sh` — **entrambi**
   i file la contengono e si desincronizzano facilmente
2. Riscrivere la history git per eliminare il blob gigante (il push fallito
   lascia il commit locale con il blob):
   ```bash
   git reset --soft <ultimo-commit-valido>
   git rm -q -r --cached . && git add -A && git commit -m "backup: fix exclude state.db"
   ```
3. Verificare che non restino blob >50MB: `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'`
4. Rigenerare il bundle secrets (senza state.db → pochi KB), commit, push
5. Test end-to-end: `cronjob action='run'` sul nightly → `last_status: ok`

**Regola**: `state.db` è runtime state, NON un segreto — non va MAI nel
bundle crittografato né nel repo. La config (che è il vero valore) è già
coperta da config/, skills/, plugins/, memories/.

### ⚠️ Pitfall: state.db creeps back into the secrets bundle

`state.db` (the Hermes session store, SQLite+FTS5) can reach **1+ GB**.
It is documented as NOT-to-backup, but it has been found in
`secret_candidates` in BOTH `generate-backup.py` AND the `for item in
...` loop of `backup-hermes.sh` — someone added it later as a "session
backup" idea. Consequence: the encrypted bundle becomes
`hermes-secrets.tar.gz.enc` of **322 MB**, GitHub rejects the push
(`GH001: File ... exceeds GitHub's file size limit of 100.00 MB`), the
nightly cron shows `last_status: error`, and NO backup happens — for
days, silently (deliver=local hides the failure).

**Checklist when the nightly backup fails or the .enc file is huge:**

1. `ls -la ~/Backups/hermes-config/secrets/*.enc` — if > 100 MB, this pitfall.
2. `grep -n "state.db" scripts/generate-backup.py scripts/backup-hermes.sh`
   — remove it from both `secret_candidates` and the `for item in` loop.
3. Verify no blob > 50 MB in the history:
   `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'`
4. If the oversized commit was already committed locally (push rejected),
   rewrite: `git reset --soft <last-good-commit>`, `git rm -r --cached .`,
   `git add -A`, re-commit, then push.
5. Re-run the cron job (`cronjob action=run`) and confirm `last_status: ok`.
6. Optionally add a `backup-monitor` job that greps for `.enc` size and
   alerts if > 50 MB.

`state.db` and `sessions/` are runtime state — they regenerate. The
config (config.yaml, skills, plugins, memories, secrets) is what a
restore actually needs.

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

## ⚠️ Pitfall: nightly cron paused = backups silently become manual

The nightly job can be **paused** (e.g. a mass pause of ~20 cron jobs, as happened
on peer70 2026-08-02) while the repo still looks healthy. Result: no automated
backups for weeks, only manual ones (`git log` shows sparse commits), **no alert
to the user** — `deliver=local` hides everything.

**Check when backups seem sparse:** `cronjob action=list` → the
"Nightly Hermes configuration backup" job must show `state: scheduled` /
`enabled: true` with a future `next_run_at`. If `state: paused`, resume:
`cronjob action=resume job_id=<id>`.

**Manual fallback** (always safe): `cd ~/Backups/hermes-config && bash scripts/backup-hermes.sh`
— regenerates snapshot, encrypts secrets, commits, pushes. Confirmed working
2026-08-14 (push `106c3c1..6fe0181 main -> main`, secrets bundle ~10 KB).

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

## ⚠️ Pitfall: recent git log ≠ nightly cron actually running

A fresh commit in the backup repo does NOT mean the nightly cron is active —
manual `backup-hermes.sh` runs also commit. On peer70 the nightly job
(`Nightly Hermes configuration backup`) sat **paused since 2026-08-02** while
`git log` showed commits from Aug 13 (manual runs); backups had silently
become manual-only. Diagnostic trap: `cronjob action=list` shows
`state: paused` with a stale `last_status: ok` from the last pre-pause run —
the ok status hides the pause.

**Check the cron state, not the git log**, when asked whether backups are
automated:
```bash
# 1. Is the job enabled and scheduled?
cronjob action=list   # look for state: scheduled (NOT paused) on the backup job
# 2. Is the last run actually recent? (paused job keeps old last_run_at)
# 3. Repo health: git log -1 + secrets/*.enc size (healthy = KB)
```
If paused: `cronjob action=resume` — and note that the pause may be
deliberate (a mass-pause of jobs happened 2026-08-02); confirm with the user
before resuming.

## ⚠️ Pitfall: state.db must NEVER go into the secrets bundle

`state.db` (the canonical SQLite session store) can grow to **1GB+** — it holds
every session/message. If it sneaks into the encrypted secrets tarball, the
`.tar.gz.enc` exceeds **GitHub's 100MB per-file limit** and the push is
rejected:

```
remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this exceeds GitHub's file size limit of 100.00 MB
remote: error: GH001: Large files detected.
 ! [remote rejected] main -> main (pre-receive hook declined)
```

The nightly cron then fails silently (`last_status: error`) for days while the
config backup stops being pushed. **Detection:** after a failed push, check the
secrets bundle size — a healthy bundle is KBs, not hundreds of MB.

**state.db is runtime state, NOT configuration** — it is regenerable and is
listed in "What NOT to backup". Restore of config/skills/memories does not need
it. Exclude it in BOTH places (they are separate and both were wrong in 2026-08):

1. `scripts/generate-backup.py` → `secret_candidates` list
2. `scripts/backup-hermes.sh` → the `for item in ...` loop

```bash
# verify no large blobs remain in the repo history
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3>50000000 {print $3, $4}'
```

### Purge a large blob already committed

If the oversized `.enc` was committed locally (push rejected), rewrite the
history before the next push — otherwise git keeps trying to upload the blob:

```bash
# find the last good commit on the remote, then squash-replace everything after it
git reset --soft <last_good_remote_commit>
git rm -q -r --cached . 2>/dev/null
git add -A
git commit -m "backup: rebuild without oversized secrets bundle"
git push
```

Then regenerate the secrets bundle (now KBs) and commit again. Verify with the
`git rev-list` check above that no blob >50MB remains.

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

## ⚠️ Pitfall: state.db sneaks into the secrets bundle → push rejected (GH001)

The skill's "What NOT to backup" table lists `state.db*` — but the
deployed scripts can silently drift from that rule. On peer70 the
`secret_candidates` list in BOTH `generate-backup.py` AND `backup-hermes.sh`
contained `state.db` (1.18GB SQLite session store). Result: the encrypted
bundle `secrets/hermes-secrets.tar.gz.enc` grew to **322MB**, exceeding
GitHub's **100MB per-file limit**, and every `git push` was rejected:

```
remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this exceeds GitHub's file size limit of 100.00 MB
remote: error: GH001: Large files detected.
! [remote rejected] main -> main (pre-receive hook declined)
```

The nightly cron showed `last_status: error` — silently failing for days.

**Fix checklist (when the bundle is too big):**

1. Remove `state.db` from `secret_candidates` in `generate-backup.py`
   AND from the `for item in ...` loop in `backup-hermes.sh` (both places —
   they are maintained separately).
2. Purge the giant blob from git history:
   ```bash
   cd ~/Backups/hermes-config
   rm -f secrets/hermes-secrets.tar.gz.enc secrets/*.key.enc secrets/*.key.pub
   git reset --soft <last_good_commit>
   git rm -q -r --cached . ; git add -A
   git commit -m "backup: fix — exclude state.db from secrets bundle"
   ```
3. Regenerate the bundle WITHOUT state.db (should be KBs, not MBs):
   ```bash
   python3 scripts/generate-backup.py
   # then re-run the openssl envelope-encrypt block from backup-hermes.sh
   ```
4. Verify no blob >50MB remains in the rewritten history:
   ```bash
   git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
     | awk '$1=="blob" && $3>50000000 {print $3, $4}'
   ```
5. `git push` → confirm `b6f4043..<new>  main -> main` succeeds.
6. Re-run the nightly cron job (`cronjob action='run'`) and check
   `last_status: ok`.

**Rule:** `state.db` is runtime state (sessions/messages — recreatable),
NOT config. Never include it in the secrets bundle; if the user wants it
archived, keep it local-only or in a separate LFS repo.

## Pitfall: state.db in the secrets bundle breaks GitHub pushes (100MB limit)

**Symptom:** nightly backup cron reports `last_status: error`; manual
`git push` fails with:
```
remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this exceeds GitHub's file size limit of 100.00 MB
```

**Root cause:** `state.db` (the SQLite session store, can reach 1GB+)
had been added to the secrets bundle. The encrypted bundle
`secrets/hermes-secrets.tar.gz.enc` bloated past GitHub's 100MB per-file
limit → every push rejected. The backup had been silently failing for
days.

**Fix — `state.db` must NEVER be in the secrets bundle** (it's runtime
state, not a secret; the skill's own "What NOT to backup" list already
excludes `state.db*`). Remove it from BOTH places:

1. `scripts/generate-backup.py` → `secret_candidates` list
2. `scripts/backup-hermes.sh` → the `for item in ...` copy loop

Then clean the oversized `.enc` from git history (the bad commit is
usually unpushed — the push was rejected):
```bash
rm -f secrets/hermes-secrets.tar.gz.enc secrets/hermes-secrets.key.enc secrets/hermes-secrets.key.pub
git reset --soft <last-good-commit> && git rm -q -r --cached . 2>/dev/null
git add -A && git commit -m "backup: fix — exclude state.db from secrets bundle"
git push
# Verify no blob > 50MB remains in the new history:
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'
```

After the fix, a healthy `secrets/hermes-secrets.tar.gz.enc` is a few KB
(only .env, auth.json, tokens), not hundreds of MB.

**Verification habit:** after any backup change, check the cron job's
`last_status` (was `error` before the fix, `ok` after) and confirm the
remote HEAD moved:
```bash
git -C ~/Backups/hermes-config log --oneline origin/main -1
```

## Pitfall: state.db nel secrets bundle → push fallito (GitHub 100MB limit)

`state.db` (SQLite session store) può crescere a **1GB+** (sessioni vecchie, indici
FTS). Se compare in `secret_candidates` (generate-backup.py) o nel loop di
backup-hermes.sh, il bundle cifrato supera il **limite GitHub di 100MB/file**:

**Sintomo**: `git push` fallisce con
`remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this exceeds
GitHub's file size limit of 100.00 MB` e il nightly resta `last_status: error`.

**Fix**:
1. Rimuovere `state.db` da `secret_candidates` in `generate-backup.py` E dalla
   `for item in ...` loop in `backup-hermes.sh` (è runtime state ricreabile, non un segreto)
2. Riscrivere la history git per eliminare il blob gigante già committato:
   `git reset --soft <ultimo-push-ok>` → `git rm -r --cached .` → `git add -A` →
   nuovo commit → push
3. Verifica: `git rev-list --objects --all | git cat-file --batch-check='%(objecttype)
   %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'` → nessun blob >50MB
4. Testare il nightly: `cronjob(action='run')` sul job backup → `last_status: ok`

**Controllo rapido** se il bundle è gonfio prima del push: `ls -la secrets/*.enc`
(un bundle sano è ~10KB, non centinaia di MB).

## See also

- `references/peer128-backup-setup.md` — Full working implementation with exact directory structure, encryption commands, and Git workflow from peer128 (macOS)
- `github-repo-management` skill — GitHub repo creation, SSH key setup, cloning
- `cron-operations` skill — Cron job lifecycle (create, update, list, remove)
