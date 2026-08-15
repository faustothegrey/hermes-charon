# Observe-channel core patch — state model v0.3.0 (multi-version fleet)

One skill version across peers, one Hermes CORE patch per core version.
Patches NEVER travel inside the skill sync (security rule, Fausto 2026-08-15):
they live in `~/.hermes/patches-core/` (env override `CAPREUSE_PATCHES_DIR`).
Validators refuse archives containing `capability-reuse/patches/*`.

## Files in ~/.hermes/patches-core/
- `observe-channel-core-<ver>.patch` — one per core version (0.17.0, 0.20.1)
- `patch-manifest.json` — patchset name/version + variants
  `{core_ver: {file, sha256, base_commit, target_core}}`
- `patch-state.json` — applied state: patch_version, state (applied), target_core,
  patch_sha256, core_commit_before/after
- `SHA256SUMS` — sha256 per patch file
- `README.md` — mapping table + regeneration commands

## Script semantics (apply-core-patch.sh, v0.3.0)
- Version resolution: EXACT core match from patch-manifest variants
  (0.20.1 → 0.20.1; 0.20.2 → UNSUPPORTED, fail-closed). Legacy prefix fallback
  only for unmigrated nodes (emits WARN).
- Modes: apply (default) · `--check` · `--smoke` · `--gate` · `--list` · `--status`
- Exit contract: 0=OK · 2=PRONTA (not applied but applicable — BLOCKING in gates) ·
  3=CONFLICT / sha mismatch (BLOCKING) · 4=SMOKE FAIL · 5=internal/unsupported
- `--check`: sha vs manifest + git apply reverse-check (already applied) /
  forward-check (applicable) / conflict
- `--smoke`: functional gate test — `get_pre_tool_call_block_message` with fake
  observe hooks (string AND dict) against a stub sink. Manager resolution:
  `_delivery_manager()` (0.20.1+) with fallback `get_plugin_manager()` (0.17.x);
  both expose `_hooks[hook_name]` for direct registration.
- `--gate` = `--check` + `--smoke`; any non-zero blocks the release.

## Regeneration flow (per node, after core changes)
1. Apply/commit changes in `~/.hermes/hermes-agent`
2. `git diff <base_commit>..HEAD -- agent/tool_executor.py gateway/run.py hermes_cli/plugins.py model_tools.py > ~/.hermes/patches-core/observe-channel-core-<ver>.patch`
   (base_commit from patch-manifest; for the 0.17.0 line it is f860492 =
   parent of the first observe commit 00b1115)
3. UPDATE `patch-manifest.json` + `patch-state.json` + `SHA256SUMS` IN THE SAME STEP
4. `bash scripts/apply-core-patch.sh --gate` → must exit 0
5. ONE manual restart (never cron restart jobs — kill-loop, cron 'once' bug)

## Pitfalls
- **Manifest-sync mismatch**: a new patch file arriving without updated
  manifest/state/SHA256SUMS makes the fail-closed sha check DIE (mismatch).
  Verify with `--gate`, never by eye. Regenerate + update the three state files
  atomically.
- **Single-fire contract — do not assume parity between core versions**:
  `pre_tool_call` must fire exactly once per tool call. On 0.20.1 the gate is
  invoked from execute_tool_calls_concurrent (no sink) + execute_tool_calls_sequential
  (with sink) + invoke_tool (extra, when pre_tool_block_checked=False) → double
  fire + lost bubble. On 0.17.0 the sequential path dispatches via
  `handle_function_call(skip_pre_tool_call_hook=True)` (model_tools.py, single-fire
  contract documented at ~line 1050) — NOT invoke_tool — so the double-fire does
  NOT exist. VERIFY empirically (count hook fires: gate+sink = 1, dispatch skip =
  still 1) before "fixing" something that is already correct on your tree.
- Test isolation for the live event log: see the v2.4.18 spec reference
  (`CAPABILITY_REUSE_EVENT_DIR` env override, never unlink the live events.jsonl).
