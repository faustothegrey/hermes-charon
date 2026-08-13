# Secrets bundle bloat: state.db must NEVER be in the secrets bundle

## Symptom

`git push` from the backup repo fails with:

```
remote: error: File secrets/hermes-secrets.tar.gz.enc is 322.36 MB; this exceeds GitHub's file size limit of 100.00 MB
remote: error: GH001: Large files detected.
! [remote rejected] main -> main (pre-receive hook declined)
```

The nightly backup cron shows `last_status: error` for days without anyone
noticing (the failure is silent unless the backup-monitor checks the push).

## Root cause

`state.db` (Hermes session store) grows to 1+ GB. Both scripts included it in
the secrets bundle:

- `scripts/generate-backup.py`: `secret_candidates = [".env", "auth.json", ..., "state.db"]`
- `scripts/backup-hermes.sh`: `for item in .env auth.json ... state.db; do`

The tar.gz.enc of a 1.18 GB state.db is ~320 MB — over GitHub's per-file limit.
This contradicts the skill's own "What NOT to backup" rule (state.db* is runtime
state, not config).

## Fix

1. Remove `state.db` from BOTH scripts (generate-backup.py `secret_candidates`
   and backup-hermes.sh `for item in ...` loop).
2. The giant `.enc` is already committed locally → rewrite history to drop it:
   ```bash
   git reset --soft <last-good-commit>
   git rm -q -r --cached .
   git add -A
   git commit -m "backup: fix — exclude state.db from secrets bundle"
   # verify no blob >50MB remains in history:
   git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'
   git push
   ```
3. Verify the new bundle is small: `ls -la secrets/*.enc` → expect KBs, not MBs.
4. Re-run the nightly cron once (`cronjob action='run'`) and confirm
   `last_status: ok`.

## Lesson

- Anything derived from `state.db`/sessions (runtime state) bloats the encrypted
  bundle. Config-only backup should stay in the low-MB range.
- A cron job whose failure mode is "push rejected" is invisible unless something
  checks `last_status`. After any backup-related change, force a run and verify
  the push landed (`git log --oneline origin/main -1`).
