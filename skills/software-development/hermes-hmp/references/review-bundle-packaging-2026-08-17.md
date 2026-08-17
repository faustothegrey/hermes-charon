# Reviewer-ready bundle packaging (G0/G2b core patch + HMP plugin) — 17/08/2026

Session recipe: external reviewer (Copilot advisory via peer128) asked for a
reviewer-ready, **non-self-modifying** bundle of the cumulative Hermes 0.20.1
G0+G2b core patch + the complete HMP plugin v0.1.4. First bundle was rejected;
second pass (this recipe) passed 22/22 static checks. Reusable for ANY
"package the exact patch X for peer Y" request.

## 1. Audit FIRST — and audit correctly (the false-negative trap)

Before packaging, verify the artifacts exist. **My first audit wrongly
concluded "no core patch exists"** because:

- `search_files(pattern="*.tar.gz|*.zip|*.patch|*.diff", target="files")`
  returned 0 — the `|`-joined glob does NOT work like regex alternation in
  files-mode. Search each extension separately, or use
  `target="content"` (grep) for known symbols.
- The artifacts were in `~/.hermes/g0-bundle/` all along (core-patches/,
  evidence/, manifest.json) — the canonical location for G0/G2b review
  artifacts on peer70. **Check `~/.hermes/g0-bundle/` before claiming
  "patch non esiste".**
- A stale report ("no patch", old hashes) is itself a P0-1 blocker that makes
  the reviewer reject even a correct bundle.

## 2. Bundle structure (what the reviewer wants)

```
peer128-bundle/
├── core-patches/
│   └── g0-g2b-core-0.20.1-peer141-cumulative.patch   # THE artifact
├── plugins/hmp/                                       # complete plugin (4 files!)
│   ├── plugin.yaml  __init__.py  adapter.py  core.py
├── plugins/README-plugin-v014.md                      # compat/migration/rollback
├── plugins/test_plugin_v014_static.py                 # static harness
├── plugins/test_plugin_v014_output.txt                # FROZEN output
├── test_g0_adapter.py  test_g0_plumbing_output.txt    # frozen core tests
├── evidence/*.jsonl                                   # raw live traces
├── README.md                                          # apply/rollback/conflicts
└── manifest-peer128.json                              # per-file SHA-256
```

## 3. The 7 required sections (checklist)

1. **Exact patch** with SHA-256 + base commit. Verify content with grep:
   `grep -c "capability_reuse_context" <patch>` — a cumulative G0+G2b patch
   has 17 matches across the 6 files; a trace-only patch has ~6. Presenting
   trace-only as "cumulative" = blocker.
2. **Base commit & preconditions**: `git rev-parse HEAD` per core; for a
   foreign peer, base support is UNVERIFIABLE locally (different repo) — ship
   the check commands instead:
   `git merge-base --is-ancestor <base> HEAD && echo BASE_OK`
   and the authoritative gate `git apply --check <patch>` (dry-run).
3. **Per-file manifest** (`manifest-peer128.json`) + **EXTERNAL sidecar**
   `bundle.zip.sha256` — never the archive hash inside the archive
   (recursive/stale). Method must be frozen in the manifest.
4. **Frozen test output** — real captured stdout, not "30/30" claims.
5. **Backup & rollback** — git diff snapshot + cp of touched dirs; rollback =
   `git checkout -- <files>` + gateway restart.
6. **Files touched** — list from `grep "^diff --git" <patch>`.
7. **Conflict guidance** — for each local-edit file the peer mentioned, state
   whether the patch touches it (grep the patch). Untouched = orthogonal = no
   conflict; keep edits, use `git apply --3way` if refused, NEVER
   `git reset --hard`/`checkout` on the peer's edited files.

## 4. Plugin co-deploy rule (hard blocker found by reviewer)

- `adapter.py` and `core.py` MUST ship and deploy together. The v0.1.4
  adapter calls `queue()`/`dequeue()`/`mark_status()` which the v0.1.2 core
  lacks → copying only the adapter onto an old core = runtime 500s.
- Ship the COMPLETE plugin dir (plugin.yaml, __init__.py, adapter.py, core.py)
  + version metadata + config/migration notes + backup/rollback.
- DB migration: none needed v0.1.2→v0.1.4 (CREATE INDEX IF NOT EXISTS,
  idempotent, forward-compatible) — say so explicitly.

## 5. Static plugin validation (no deploy, no restart)

`test_plugin_v014_static.py` pattern — import the bundle's plugin in
isolation and assert signatures, proven with the Hermes venv python:
`~/.hermes/hermes-agent/venv/bin/python plugins/test_plugin_v014_static.py .`

Checks (22/22 in this session):
- plugin.yaml version/kind parse
- `import hmp.adapter` / `import hmp.core` (sys.path: plugins dir + parent)
- core signatures via `hasattr(HMPStatusStore, fn)` for
  accept/queue/dequeue/mark_status/complete/fail/get + `chat_id` in
  `queue.__code__.co_varnames` (session parity)
- routes present in adapter source: `/health`, `/hmp/health`, `/hmp/send`,
  `/hmp/send_and_wait` + handlers
- G0/G2b wiring: `uuid.uuid4()` in adapter source, `_capability_context`
  method, `strip()` inside it (pure-string provenance fix — dict → str(dict)
  breaks normalize_provenance).

Pitfall in the harness itself: `_capability_context` is a CLASS method —
`inspect.getsource(adapter._capability_context)` (class), NOT
`adapter_mod._capability_context` (module attr → AttributeError/FAIL).

## 6. Manifest must match the bundle 1:1 (P0-1)

After assembling: remove stale manifest entries for files deleted from the
bundle (e.g. top-level `adapter.py` left over from a first pass), strip
`__pycache__/`, and re-verify every manifest SHA against disk. A manifest
listing files not in the archive = instant rejection. Validate JSON with
`python3 -c "import json; json.load(open(...))"`.

## 7. Communication style with peer/reviewer

The peer explicitly asked twice for terse status: "rispondimi solo con 3
info rapide" / "rispondimi con sole 3 cose quando puoi". For status
requests from peers: answer with 3 short bullet facts (done? value? next
step?), no preamble, no table spam. Save long-form for deliverable reports.

## 8. Third iteration: capability-reuse dependency (v2.2.0 → v2.6.0)

When the bundle's adapter imports event_store from capability-reuse, the
peer's LOCAL plugin version matters: peer128 had v2.2.0 which lacks
`emit_surface_execution_start`/`emit_surface_execution_complete` (added in
v2.6.0) → the bundled adapter regression fails locally. Package the exact
cohort artifact.

**Canonical artifact hash (impl-capreuse method, frozen):**
```python
h = hashlib.sha256()
for f in sorted(Path(plugin_dir).glob("*.py")):   # top-level ONLY, non-recursive, non-zip
    h.update(f.name.encode()); h.update(f.read_bytes())
```
- v2.6.0 expected: `ebab8ae60e75848063aa89a67119f65312d1dc0d921955da52a0a6c95434ebb7`
- **Canonical source = `~/.hermes/plugins/capability-reuse` (11 .py)**.
  NOT `~/.hermes/skills/hermes/capability-reuse/plugin` (13 .py incl. r2-*.py,
  different hash) — verify with the method before packaging, don't assume.
- Version lives in MULTIPLE files — check ALL: `v244_metadata.PLUGIN_VERSION`,
  `protocol.VERSION`, `review_queue.EXPECTED_PLUGIN_VERSION` (all 2.6.0).
  Partial sync (event_store at 2.6.0 but metadata at 2.5.0) = declared old
  version in real retrievals (peer141 pre-seal pitfall).

**Static test placement pitfall:** the static test MUST NOT live inside the
plugin dir — the impl-capreuse `glob("*.py")` counts it (12 vs 11 → wrong
hash). Put tests in a sibling `tests/` dir.

**Relative-import modules:** `retriever.py` uses relative imports → top-level
`import retriever` fails (`attempted relative import`). Verify with
`compile(src, name, "exec")` for syntax; import top-level only the modules
that allow it. The production loader puts the plugin dir on sys.path.

**Atomic rollback rule:** capability-reuse and the HMP adapter are a coupled
pair — rolling cap-reuse back to v2.2.0 while the v0.1.4 adapter stays active
= 500 (missing surface). State the pair rule in compat notes.

**Deploy order to document:** capability-reuse → HMP plugin (4 files) → core
patch → gateway restart.

## 9. Manifest 1:1 verification loop (after EVERY change)

Re-run after each iteration, not once at the end: walk the bundle dir, compare
against manifest `files` + nested sections (e.g. `capability_reuse.files`),
report EXTRA (on-disk not in manifest), MISSING (manifest without file),
DRIFT (hash mismatch). Fix all three, then zip + external sidecar + `unzip -t`.
A manifest that misses 3 files while the zip has 29 = stale report = P0-1.
