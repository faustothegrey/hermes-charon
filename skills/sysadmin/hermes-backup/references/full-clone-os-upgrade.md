# Full Hermes Agent Clone for OS Upgrade / Migration

Session 2026-08-23 (peer70/Charon, Debian 11 → 12). The nightly config backup is NOT a
full clone — it deliberately excludes the source tree with local patches, systemd units,
crontab, SSH keys, iptables, fstab, and runtime data. For an OS upgrade or hardware
migration you need the layered strategy below. Peer-reviewed 5/5 (peer58/128/136/138/141);
every pitfall marked ⚠️ was independently confirmed by ≥2 peers.

## Layer strategy (A–D)

- **A — full clone artifact:** tar.gz of `~/.hermes` + system files. This is the deliverable.
- **B — source reproducibility:** git bundle + dirty-file patch of the hermes-agent source,
  so the patched build can be reconstructed on stock upstream version (no need to ship 1.9G).
- **C — nightly GitHub config backup:** already exists (this skill); verify it's green first.
- **D — bare-metal safety net:** full SD/disk image (`dd | gzip`), gateway stopped.

## Inventory checklist (verify, don't assume)

- `~/.hermes` size + what's inside (source tree? state.db? node? bin? lsp? node_modules?)
- Hermes source git state: commits ahead of origin, dirty files, **untracked files**
- systemd user + system units (gateway, netboard), `systemctl --user is-enabled`
- crontab + Hermes cron jobs (`hermes cron list --all` — note: `cron/` dir may hold only
  a few files while the DB registers ~27 jobs)
- SSH keys, iptables (`iptables-save` + `/etc/iptables/rules.v4`), fstab, sudoers, hostname
- Off-box storage targets: check REAL free space. A FRITZ!Box NAS with ~360MB free is too
  small; a Mac/peer with 100+ GiB is right.

## ⚠️ Critical pitfalls (the ones that bite)

1. **`git diff` misses untracked files.** Reality was "5 modified + 1 untracked"
   (`.install_method`), not "5 dirty". `git diff > patch` silently drops untracked AND
   staged changes. Use `git diff HEAD > dirty.patch` + `git status --porcelain > list`,
   or `git stash -u` as a complete snapshot. Verify with `git apply --check` on a clean
   stock checkout — "the patch exists" ≠ "the patch applies".
2. **state.db must NEVER be copied hot with cp/tar.** SQLite in WAL mode under a live
   gateway = torn/corrupt backup, not "maybe". Use `sqlite3 ~/.hermes/state.db ".backup /tmp/state.db.bak"`.
   (This is the *inclusion* path — the nightly bundle still excludes state.db entirely.)
3. **`~/.ssh/id_rsa` is the single point of failure.** It decrypts the secrets envelope on
   GitHub. If the disk dies and id_rsa only lived on it, the encrypted backup is
   unrecoverable — chicken-and-egg. Copy id_rsa in CLEAR (perm 600) off-box, or into Layer D.
4. **`node_modules` inside the source tree can be ~1.1G** — exclude it from Layer A and
   document the reinstall (`npm ci` from package.json) in the restore phase.
5. **The venv/binaries are NOT portable across OS/Python bumps** (Debian 11 py3.9 → 12
   py3.11). Rebuild the venv from requirements/pyproject + smoke test; include a
   RESTORE-MANIFEST.json pinning node/lsp/dependency versions.
6. **iptables lockout at restore:** if you apply `INPUT DROP` before the LAN/SSH ACCEPT
   rules you close yourself out. Apply ACCEPT rules first, or use a rollback timer
   (`at now+5min` that flushes) when changing policy live.
7. **`loginctl enable-linger <user>`** — user systemd units (hermes-gateway.service) won't
   start at boot without it.
8. **Verify restore BEFORE touching the OS** (mandatory, not optional): dry-run restore on a
   scratch dir, `git bundle verify`, clone the bundle + `git apply --check` on stock, and
   test-decrypt the secrets envelope — all on scratch, never on the live box. A restore
   that was never tested is a useless backup.
9. **Clean snapshot for Layer D:** `dd` of a mounted root FS is not crash-consistent — stop
   the gateway/services first. Stream `dd | gzip | ssh target 'cat > img.gz'` to avoid
   filling local disk.

## Peer-review-via-HMP workflow

- Broadcast the plan brief to all online peers via `/hmp/send`, one unique message_id each.
- **Poll each peer on ITS OWN IP** (`http://<peer-ip>:18643/hmp/poll/{id}`) — polling the
  wrong host returns `not_found` even when the message was accepted.
- Peers verify facts on the box via read-only SSH and return grounded reviews; consolidate
  corrections into the plan (REV 2 pattern). Note: peers without SCP access to your vault
  can only review the summary you POST, not the full file.

## ⚠️ Verifying a snapshot actually restores you (existence ≠ restorable)

Session 2026-08-23 (peer70). A user challenge — "is it really verified restorable?" —
exposed a real gap in a NAS snapshot that had been labelled "verified". The lesson:
**an archive can be byte-integrity-clean yet still not reproduce the running agent.**

### The trap: stale-generation patch

The first snapshot shipped `patches-core/observe-channel-core-0.17.0.patch` and the
live `git status` list, and I called it "verified" because checksums matched and files
existed after extraction. But that stored patch was an **OLDER generation**: it touched
`agent/tool_executor.py` + `hermes_cli/plugins.py` (already committed upstream), while the
CURRENT dirty state was a different set of 5 files (`agent/agent_init.py`,
`agent/turn_context.py`, `gateway/platforms/base.py`, `gateway/run.py`, `run_agent.py`).
`git apply --check` FAILED. The snapshot had captured the file *list* but not the
*content* of the current diff — a restore would have brought back the wrong, broken patch.

**Rule:** `patches-core/*.patch` may be a historical generation. At snapshot time ALWAYS
regenerate the current diff (`git diff HEAD > hermes-current-dirty.patch`) and ship THAT
plus `git status --porcelain` (for untracked like `.install_method`, content = the literal
string `git`) plus base hashes (`git rev-parse HEAD` / `origin/main`). Put it in a
dedicated `source-patches/` dir, and document in the manifest which patch is the restore
source — the older one is a trap.

### The verification battery (all on scratch, never live)

1. **Archive integrity:** `tar -tzf` (reads every member; 0 errors) + `gzip -t`.
2. **Byte-compare identity files vs live** with the CORRECT path mapping. My first pass
   compared `agent-core/memories/MEMORY.md` against `$HOME/.hermes/memories/MEMORY.md`
   (missing the `agent-core/` prefix) → false "MISSING" for everything. Map
   `snapshot/agent-core/X` → `~/.hermes/X`, `snapshot/ssh/X` → `~/.ssh/X`.
   `md5sum` both; expect IDENTICAL for config.yaml/.env/MEMORY.md/registry.json.
3. **auth.json legitimately differs** (OAuth `access_token`/`agent_key` refresh every
   ~30min) — not corruption. Both must be valid JSON with the same *structure*; only the
   token fields and `expires_at`/`obtained_at` churn. On restore the app re-auths.
4. **THE key test — patch reproduces state, not just applies:** `git apply --check` the
   snapshot patch on a clean committed tree, then `git apply` it and `md5sum` each file
   against the LIVE dirty file. All 5 must MATCH. `apply --check` clean alone proves
   applicability; the byte-compare proves it reproduces the running state.
5. **Scope honesty:** this verifies the DATA + PATCH restore path. It is NOT a boot
   rehearsal on a clean OS — that needs a test machine. Say so explicitly; do not call a
   scratch-extract rehearsal a proof of boot.

### Sizing note: identity snapshot fits a small NAS

The compact "clone-me" set (skills 35M, plugins, cron, memories, scripts, registry,
patches-core, data, exchange, peer-network, netboard, state, config/.env/auth) is ~78 MB
raw → **~28 MB gzipped**, so it DOES fit a FRITZ!Box NAS (~335MB free after). Only the
runtime (hermes-agent source 1.9G, state.db 644M, node/bin/lsp) needs the off-box target.
So for NAS snapshots, ship identity+patches (fits); for the full clone use the off-box plan.

## Off-box target choice

peer128 (Mac, 111 GiB free) confirmed as target with a **PULL-model rsync** (target inits
`rsync` from source over SSH — no need to open sshd on the target). Check `df -h` on the
target first; the FRITZ!Box NAS (~360MB free) is a drop-point, not a clone target.
