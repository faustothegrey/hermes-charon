# Capability Reuse — conformance integration harness notes (2026-07-27)

## Trigger
Use this note when extending or auditing the `capability-reuse` conformance suite after live-shadow/plugin-hook work.

## Lesson captured
The remaining skipped conformance tests can be converted into deterministic local integration probes without requiring a live LLM turn by using a small fake Hermes plugin context and a simulated tool-dispatch path. This gives a real regression gate for hook contracts while preserving the distinction from true end-to-end CLI/gateway/delegation testing.

## Pattern
1. Build a `_FakeCtx` that records `register_tool(...)` and `register_hook(name, fn)` calls.
2. Register the plugin twice when needed:
   - `CAPABILITY_REUSE_MODE=shadow`: assert `invoke_capability` is hidden and `pre_llm_call` returns no injection.
   - `CAPABILITY_REUSE_MODE=active`: assert `invoke_capability` is visible/callable, but active dispatch still returns explicit non-success until the real dispatcher exists.
3. Provide harness helpers:
   - `_plugin_context(mode)` — imports plugin and calls `register(ctx)` under an explicit mode.
   - `_hook_map(ctx)` / `_invoke_ctx_hook(ctx, hook_name, **kwargs)` — invokes captured hook callbacks directly.
   - `_simulate_tool_dispatch(ctx, tool_name, args, result, session_id, task_id, tool_call_id, blocked=False)` — fires `pre_tool_call`, applies first `{action: "block"}` directive, then fires `post_tool_call` with either real or synthetic blocked result.
   - `_clear_event_log()` / `_read_events()` — reset and inspect JSONL evidence.
4. Convert live-runtime skips into executable probes for:
   - tool visibility/callability
   - `pre_llm_call` single-fire + correlated retrieval event + no shadow injection
   - `pre_tool_call` single-fire for `execute_code`
   - `post_tool_call` success/failure/plugin-blocked outcomes
   - stable `session_id`/`task_id`/`tool_call_id`
   - CLI/gateway/delegation-shaped extra kwargs tolerance
   - exact kwargs preservation
   - injection seam reachability and user-message position
   - degraded/fallback-token double-pass semantics
5. Add an outer unittest gate that runs:
   `python3 scripts/conformance-suite.py --profile full-required`
   and asserts exit code 0 plus `Results: 15 passed, 0 failed, 0 skipped / 15 total`.

## Caveat to preserve in reports
This harness proves plugin hook contracts and simulated dispatch behavior. It is not a substitute for a true live end-to-end run through real LLM, CLI, gateway, and delegation surfaces. Do not claim Phase 1B active dispatch safety until the real dispatcher and live surface tests exist.
