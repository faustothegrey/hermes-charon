# Observe-channel core patch workflow (v0.3.0+, 2026-08-15)

## Structure (security rule 2026-08-15)

Core patches NEVER travel inside the skill sync (zip/rsync/validator refuses
archives containing `capability-reuse/patches/*`). They live in
`~/.hermes/patches-core/` (`CAPREUSE_PATCHES_DIR` for override).

Files:
- `observe-channel-core-<core_ver>.patch` — MUST carry a header comment:
  `# patchset / target_core / patch_version / base_commit / changelog`.
- `patch-manifest.json` — variants per core with `file`, `sha256`,
  `base_commit`; plus `validation.commands` (validator + smoke).
- `patch-state.json` — applied state: `patch_version`, `state`, `patch_sha256`,
  `core_commit_before` (captured BEFORE `git apply`), `core_commit_after`.
- `SHA256SUMS`, `validate-observe-channel-bundle.py` (fail-closed validator),
  `observe-channel-single-fire-smoke.py` (runtime single-fire evidence).

`apply-core-patch.sh` contract (v0.17.1+):
- `--check`: sha vs manifest + git apply reverse/forward + **base_commit pin**
  (FAIL exit 3 if HEAD does not descend from declared base).
- `--apply` (default), `--smoke` (real gate via core venv, fake observe hooks,
  string AND dict), `--gate` = check + smoke, `--list`, `--status`.
- Exit codes: 0 OK · 2 PRONTA (not applied but applicable — BLOCKING) ·
  3 CONFLICT (regenerate — BLOCKING) · 4 SMOKE FAIL · 5 internal.
- Search order: `CAPREUSE_PATCHES_DIR` env → `~/.hermes/patches-core` →
  legacy `skill/patches/` (transition only, drop once all peers migrated).
- Smoke import must fall back across core versions: `_delivery_manager()`
  (0.20.1+) vs `get_plugin_manager()` (0.17.x) — both expose `_hooks`.

## Review-gate checklist (2 REJECT cycles distilled)

1. **Cumulative patch, not incremental**: regenerate as
   `git diff <base_commit>..HEAD -- <files>`. Incremental patches are
   unreviewable.
2. **Verify on a clean UPSTREAM clone** at the release tag (preimage/postimage
   sha), not only your local repo — local-only commits (observe feature
   commits, typing fixes) may not exist upstream; the reviewer tests there.
3. **Bundle must be self-verifying**: include the script + validator + smoke
   inside the bundle (fail-closed must be reviewable IN the bundle).
4. **Single-fire needs runtime evidence**: `observe-channel-single-fire-smoke.py`
   (7 cases: each hook fired exactly once with exact counts, sanitize assert,
   block→observe ordering, approval).
5. **Sanitization covers ALL feedback paths**: string AND dict, tab→space,
   unicode format chars removed (zero-width U+200B-200F, BOM U+FEFF, soft
   hyphen U+00AD, U+2028/2029, U+2060-2064); second defense
   `_sanitize_bubble_text` in gateway/run.py rendering.
6. **Dead code gets flagged**: zero-caller helpers/params/sinks must be
   removed (`get_pre_tool_call_feedback`, `pre_tool_call_feedback_sink` param,
   dead `_harness_feedback_sink` defs) or the cumulative patch carries them
   forever. After removing a param, check for orphaned imports (dead
   `Callable` import in model_tools) — remove those too so the file returns
   to upstream and drops out of the patch entirely.

## PITFALL: identical code blocks + fuzzy diff = wrong block removed

Three `_harness_feedback_sink` defs (real dispatch, spinner path, quiet path)
are byte-identical. An increment generated with fuzzy context matched the
REAL def instead of a dead one → def removed while the usage at
`feedback_sink=_harness_feedback_sink` remained → **NameError at runtime** in
the sequential dispatch path. `py_compile` does NOT catch it, and the
single-fire smoke uses a stub sink so it doesn't catch it either.

Verification after ANY increment that deletes code — count symbols, don't
trust compile:
```bash
grep -n "def _harness_feedback_sink\|feedback_sink=_harness_feedback_sink" agent/tool_executor.py
# expect def BEFORE usage, exactly 1 def + 1 usage
./venv/bin/python -c "import agent.tool_executor as te, inspect; \
src=inspect.getsource(te.execute_tool_calls_sequential); \
assert src.count('def _harness_feedback_sink')==1"
```
Apply increments on a clone of your HEAD and verify apply+reverse+compile
BEFORE touching the real tree.

## PITFALL: manifest/sha sync discipline

- `patch-manifest.json` / `SHA256SUMS` / `patch-state.json` must ALWAYS match
  the actual file sha — update all three in the SAME step as the patch file.
  A stale declared sha makes the fail-closed script REFUSE (by design).
- When a peer syncs files, verify file sha vs declared sha BEFORE use
  (received 0.17.0 file was `206240f0` while manifest declared `bf4b95b0`;
  actual 0.20.1 file was `5e065b78`, not the stated `4fd3b2db`).
- Regenerate the cumulative patch from YOUR committed state and treat it as
  authoritative; `diff` against the synced file to catch gaps (a synced
  "cumulative" lacked model_tools.py hunks entirely — incomplete on a clean
  clone).

## PITFALL: verify-before-apply for peer-proposed fixes

A proposed "fix 1" (single gate invocation) for 0.17.0 turned out ALREADY
satisfied: the sequential path dispatches via
`handle_function_call(skip_pre_tool_call_hook=True)` (NOT `invoke_tool`), and
the single-fire contract is documented in `model_tools.py:1050`. Empirical
hook-fire counting proved 1 fire per path. When a proposed fix doesn't apply
to your tree, verify and report honestly instead of fabricating a change.

## Per-core-version adaptation

0.17.0 (peer70) vs 0.20.1 (peer141) differ structurally: gate function names
(`get_pre_tool_call_block_message` vs `_get_pre_tool_call_directive_details`),
dispatch (`handle_function_call` vs `invoke_tool`), line numbers, TurnRunner
layout. Adapt SEMANTICS, not line numbers; when delegating adaptation, give
the other peer anchor points (file:line + flag names such as
`pre_tool_block_checked` / `skip_pre_tool_call_hook`).

## E2E trace_id chain (HMP)

Resolution chain in `retriever.py`: explicit `trace_id`/`chat_id` →
`sender_id` (when `platform=hmp`) → requester dict / flat
`requester_peer_id`/`source_peer_id`/`hmp_requester_peer_id` (when
`channel=hmp` and sender_id missing) → `session_id` fallback. The A-reversed
case showed `sender_id` can be ABSENT for sessions whose kwargs carry the
requester dict instead — without the requester fallback the chain splits
(adapter trace=`peer58` vs plugin trace=`<session_id>`) and point-4 fails.
Verify the whole chain: adapter observer events AND plugin retrieval must
share trace_id; `review.trace_id == retrieval.trace_id`;
`review.retrieval_event_id_ref == event_id`. Verify the caller's claims too —
a peer's "trace=peer58 su tutta la catena" was wrong (only the adapter events
carried it).
