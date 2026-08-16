# Observe-channel review rounds 3→5, v2.5.0 vertical slice & runtime-proof drivers (2026-08-16)

Session lessons from the external-review cycle of the observe-channel core
patchset (v0.3.0, rounds 3→5 + post-release P1s) and the capability-reuse
v2.5.0 slice (plugin uses the observe channel). Applies to ANY future
core-patch / plugin release submitted to the external reviewer.

## Review-round traps (each was a real reviewer P0/P1)

1. **Cumulative patches only.** The reviewer rejected an incremental patch
   (base_commit points at a commit that does not contain the earlier hunks).
   Regenerate the FULL patch from the base: `git diff <base>..HEAD -- <files>`.
   `--check` on the clean base worktree (`git worktree add /tmp/clean <base>`),
   apply, `py_compile` the touched files, `git apply --check -R` (reverse OK).

2. **Base commit may be LOCAL-ONLY.** `f860492` (0.17.0 base) was NOT reachable
   from `origin/main` (`git merge-base --is-ancestor f860492 origin/main` fails).
   The reviewer cannot check out a local commit. Mitigation: declare the 3
   preimage blob shas (`git rev-parse <base>:<file>`) in `patch-manifest.json`
   and make the bundle validator verify patch `index` lines match the declared
   preimages. Verify postimage shas with `git hash-object <file>` (NOT
   `git rev-parse :file` — that reads the index, which `git apply` does not
   update). Fallback if reviewer rejects: rebase onto an upstream tag.

3. **Identical code blocks → the increment patch can delete the WRONG def.**
   Three `def _harness_feedback_sink` closures (dispatch real / spinner /
   quiet path) were byte-identical; a removal increment matched the REAL
   dispatch def and deleted it, leaving a `NameError` at runtime (usage at
   line 939 without def). The reviewer's own smoke used a stub sink and did
   not catch it. After ANY increment that removes one of several identical
   blocks: grep `def X` vs usage count and assert 1 def + 1 usage in the
   real path before committing.

4. **Dead-code residue classes the reviewer flags:** zero-caller helper
   functions (`get_pre_tool_call_feedback`), dead `feedback_sink` params and
   their now-unused `Callable` imports (model_tools kept `from typing import
   ..., Callable` with zero uses after the param was removed), dead sink
   closures. Grep both patches for the dead symbol: 0 occurrences in CODE
   (occurrences inside the changelog header are fine).

5. **Sanitization must cover BOTH feedback shapes.** `_sanitize_observe_text`
   applied only to dict `text` was a P1 — string feedback was unsanitized.
   Also: tab → space, control chars removed, zero-width U+200B-200F / BOM
   U+FEFF / soft hyphen U+00AD / U+2028-2029 / U+2060-2064 REMOVED (not
   spaced), `\r\n` → space, collapse, strip. Second defense:
   `_sanitize_bubble_text` in `gateway/run.py` rendering (str AND dict).

6. **Ordering rule (reviewer constraint):** in the gate loop, `block` wins but
   the `observe` feedbacks of the same hook pass are still delivered in BOTH
   orders. `observe` requires an explicit `feedback_sink` — skip explicitly if
   absent, never side-effect block/approve. Single sink point at the real
   dispatch; other gate call sites skip via flags (`pre_tool_block_checked` /
   `skip_pre_tool_call_hook`) — verify empirically with a hook-fire counter.

7. **Base anchoring:** `--check` must FAIL-CLOSED on a forged/missing
   base_commit (forge test: manifest base → `deadbeef` → expect non-zero rc;
   note rc may be 3 or 5 depending on script version — align script and doc).

8. **SHA256SUMS must cover ALL bundle artifacts** (2 patches + manifest +
   validator + smoke + installer + README + evidence files), not just the
   patches. `validation.evidence` entries (gate-evidence-*.txt) also need
   their shas listed. `patch-state.json` is node-local → validator refuses it
   in the release bundle, `--allow-state` for the operational path.

## Core 0.17.x vs 0.20.1+ compatibility (drivers/smokes)

The real-gateway dispatch proof driver must be **version-aware**:

- `hermes_cli.plugins._delivery_manager()` exists 0.20.1+; 0.17.x uses
  `get_plugin_manager()` — `try: mgr = hp._delivery_manager()
  except AttributeError: mgr = hp.get_plugin_manager()` (both expose
  `_hooks[hook_name] = [callbacks]`).
- The gate+sink location differs: on 0.20.1+ `_run_agent_tool_execution_middleware`
  contains the gate with the internal `_harness_feedback_sink`; on 0.17.x the
  middleware has NO gate — the sink-carrying real dispatch is
  `execute_tool_calls_sequential` (gate at ~line 939). Driver branch:
  `_core_is_ge_020()` (parse `hermes_cli.__version__`) → middleware route
  (with `display_index=` kwarg, 0.20-only signature) vs sequential route.
- The 0.17 sequential dispatch reads many agent attrs; a fake Agent needs
  `_interrupt_requested`, `_context_engine_tool_names`, `_recent_tools`,
  `tool_delay`, `tool_complete_callback`, `_append_guardrail_observation`,
  plus a benign `__getattr__` for `_subdirectory_hints`
  (`check_tool_call() -> []`), `_tool_result_content_for_active_model`,
  `_apply_pending_steer_to_tool_results`.
- Drivers that import `hermes_cli`/`gateway.run` must run with the CORE venv
  python (`~/.hermes/hermes-agent/venv/bin/python`), not system python3.

## kind-filter rule for observe proofs (bit BOTH nodes)

When harness-feedback (or any per-tool observe plugin) is installed, the
dispatch sink receives `kind=generic` ⚙️ bubbles for EVERY tool call
(legitimate, per-tool) alongside the per-envelope `kind=retrieval` 🔍 bubble.
Any single-fire assertion must filter `isinstance(feedback, dict) and
feedback.get("kind") == "retrieval"` — counting ALL `tool.considered` events
fails on nodes with the dummy plugin (peer141's "PASS" was luck: its run
replaced `mgr._hooks` with only the capability-reuse hook). Filter by kind,
not by plugin identity (the dummy can be renamed).

## v2.5.0 vertical-slice design (plugin uses the observe channel)

- `_remember_retrieval` stores capability_id/score/latency + `candidates` +
  `observe_shown` under 6 scope keys (session/episode/turn combos).
- `consume_retrieval_observe(session, episode, turn)`: STRONG match on
  (session, turn) only — exact key `(session, episode, turn)` with fallback
  to `(session, "", turn)` if episode is absent in hook kwargs; single-fire
  via `observe_shown` set ONLY when observe actually returns; fail-open
  (no capability/score → None WITHOUT consuming).
- Shadow mode: result `capability_id` is empty — fallback to
  `candidates[0]` (capability_id + score) or the bubble never emerges.
- Hook: `on_pre_tool_call` non-execute_code branch returns
  `{"action":"observe","feedback":{"kind":"retrieval","text":"<cap> · score <s>","duration_ms":<lat>}}`
  wrapped in try/except (log the exception with `exc_info` — silent fail-open
  hides bugs the reviewer will flag).
- Session vs episode: the gate's hook kwargs carry NO `episode_id` — consume
  must handle `episode=""` (this is why the fallback key exists).

## Test-staleness on version bump (recurring class)

Old tests hardcode the version: fixtures with `plugin_version: "2.4.19"`,
cohort labels `v2.4.19_live`, and REASON STRINGS WITH UNDERSCORES
(`plugin_version_not_2_4_19`). A `sed 's/2\.4\.19/2.5.0/g'` misses the
underscore form (`2_4_19`). After ANY version bump: grep the whole tests/
tree for both dot and underscore forms of the old version and the cohort
label; bump `review_queue.py` EXPECTED_* AND `cohort.json` together.

## Sync hygiene

- Test files belong in `tests/` ONLY. A `test_*.py` landing in `plugin/`
  (skill or runtime) breaks the `diff -r` IDENTICAL check and keeps coming
  back if the other peer's sync includes it — remove it from the peer's
  source too.
- After syncing skill↔runtime: `diff -r --exclude=__pycache__ --exclude=*.pyc`
  must be IDENTICAL before running the suite/gate.
- Skill SKILL.md `version:` must match `v244_metadata.PLUGIN_VERSION` — the
  scp sync often updates only the plugin files.
