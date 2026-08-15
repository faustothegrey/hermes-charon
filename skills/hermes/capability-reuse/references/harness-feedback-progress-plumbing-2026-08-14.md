# Harness-feedback plumbing — tool progress streaming map (2026-08-14)

Design note from the session where Fausto asked for a short mid-turn feedback:
"ho considerato l'azione del prompt e ho valutato se applicare o non applicare
un harness dedicato" (dummy version first, just to prove the plumbing).

Goal: when Hermes is about to act on a prompt, show the user a brief visible
bubble stating the action was considered and whether a dedicated harness
(capability-reuse) was applied or not. Today capability-reuse decides this
internally (retriever → intervene or not) but is invisible to the user.

## How tool progress streaming works today (verified in code)

```
tool.started → progress_callback(event_type, tool_name, preview, args)
             → progress_queue → bubble "💻 terminal: cmd" (Telegram/CLI)
```

- `progress_callback` lives in `gateway/run.py` (~line 15479). Handles
  `tool.started` events only (ignores `tool.completed`, `reasoning.available`),
  plus a special `_thinking` relay gated on `display.thinking_progress`.
- Wired to the agent as `agent.tool_progress_callback = progress_callback`
  when `needs_progress_queue` (tool_progress OR thinking_progress enabled).
- Config: `display.tool_progress` = `all` | `new` | `off`
  (env fallback `HERMES_TOOL_PROGRESS_MODE`), plus
  `display.tool_progress_grouping` = `accumulate` | `separate`.
  Resolved per-platform in `gateway/run.py` ~15349-15407.
- Rendering: `agent.display.get_tool_emoji(tool_name)` for the emoji;
  terminal commands render as fenced code blocks on adapters with
  `supports_code_blocks` (Telegram), capped at `tool_preview_length`.

## The plugin hook contract (where "consideration" happens)

`pre_tool_call` plugin hooks fire exactly once per tool execution via
`hermes_cli.plugins.get_pre_tool_call_block_message()` (~line 1982), which
calls `invoke_hook("pre_tool_call", tool_name=..., args=..., task_id=...,
session_id=..., tool_call_id=..., turn_id=..., api_request_id=...)`.

**Current return contract (only these are honored):**
- `{"action": "block", "message": "..."}` → first valid block wins, tool is
  blocked, message shown to user.
- `{"context": "..."}` (pre_llm_call) → injected into the user message,
  ephemeral, never persisted. NOT visible as a standalone bubble.
- Anything else → silently ignored (observer-only hooks unaffected).

**Gap:** there is NO non-blocking "informative feedback" return today. A
plugin cannot emit a visible mid-turn bubble without either blocking the tool
or injecting invisible context. `get_pre_tool_call_block_message()` only
returns a block message; other results are discarded.

## Other visible-message channels that exist

- `interim_assistant_callback` / `agent._emit_interim_assistant_message()`
  (`run_agent.py` ~4286; called from `conversation_loop.py` ~4042/4304/4731):
  real mid-turn assistant commentary, gated on
  `display.interim_assistant_messages` (default true in gateway). This is
  the natural channel for "assistant says something short mid-turn".
- `status_callback` / `_emit_status()` (`run_agent.py` ~786): lifecycle
  status messages, both CLI and gateway.
- `PluginContext.inject_message(content, role="user")`
  (`hermes_cli/plugins.py` ~420): injects INTO the conversation (starts a new
  turn / interrupts) — too invasive for a lightweight feedback bubble.

## Proposed extension for the dummy feedback

Add a new non-blocking return to the pre_tool_call hook contract:

```python
def on_pre_tool_call(tool_name, args, **kwargs):
    return {
        "action": "observe",          # new: NON-blocking feedback
        "feedback": "🔍 azione considerata · harness non applicato (dummy)",
    }
```

Implementation points (from the code map):
1. `hermes_cli/plugins.py::get_pre_tool_call_block_message()` — currently
   drops non-block results. Either generalize it to also return a feedback
   list, or add a sibling `get_pre_tool_call_feedback()`.
2. `model_tools.py` (~line 1049-1059) — where the hook is invoked for the
   tool dispatch; collect feedback and pass it up.
3. `run_agent.py` / `gateway/run.py` — surface the feedback through the
   existing `progress_queue` (progress_callback) so it renders as a bubble
   exactly like tool progress; or through interim_assistant_callback.

Design constraint: do NOT break the single-fire contract — pre_tool_call
must still fire exactly once per tool execution (capability-reuse hooks
depend on it). The feedback path must be fail-open (plugin exception → no
bubble, tool proceeds).

## ✅ IMPLEMENTED (same session, 2026-08-14) — dummy v0.1.0

The observe contract is now live on peer70. **Final implementation differs
from the proposal AND from the first attempt** — see the three pitfalls
below; they are the durable lessons.

**Files changed (peer70 checkout):**

1. `hermes_cli/plugins.py` — `get_pre_tool_call_block_message()` gained an
   optional `feedback_sink: Callable[[str], None] = None` parameter. On the
   SAME single-fire `invoke_hook("pre_tool_call", ...)` pass it now: returns
   the first `{"action": "block", ...}` message AND, for every
   `{"action": "observe", "feedback": "..."}` result, delivers the string to
   `feedback_sink` (fail-open: sink exceptions swallowed). This keeps the
   single-fire contract — **never call the hook a second time for feedback**.

2. `agent/tool_executor.py` — the REAL dispatch path (the pre-execution
   `_block_msg = get_pre_tool_call_block_message(...)` gate at ~line 958,
   the one that runs before `handle_function_call(..., skip_pre_tool_call_hook=True)`)
   passes a `_harness_feedback_sink(fb)` closure that fires
   `agent.tool_progress_callback("tool.considered", function_name, fb,
   function_args)` when `agent.tool_progress_callback` is present.

3. `gateway/run.py` progress_callback (~line 15530) — new branch BEFORE the
   `tool.started` filter:
   ```python
   if event_type == "tool.considered":
       if preview and isinstance(preview, str) and preview.strip():
           progress_queue.put(f"🔍 {preview.strip()}")
       return
   ```
   Renders as a normal progress bubble (🔍 prefix), never blocks.

4. New plugin `~/.hermes/plugins/harness-feedback/` (plugin.yaml v0.1.0 +
   `__init__.py`) — dummy `on_pre_tool_call` returns
   `{"action": "observe", "feedback": f"azione considerata · harness
   {applicato|non applicato} (dummy)"}`. Dummy rule: harness applied for
   `{terminal, execute_code, web_extract, image_generate}`, else not.
   `HARNESS_FEEDBACK_MODE=dummy` env gate (any other value → no feedback).

**Test (unit, venv python):**
```python
# must use the hermes venv python (~/.hermes/hermes-agent/venv/bin/python3),
# NOT system python3 (3.9 lacks X|Y → hermes_constants import fails)
collected = []
def sink(fb): collected.append(fb)
mgr = plugins.get_plugin_manager()
mgr._hooks.setdefault("pre_tool_call", []).append(fake_observe_hook)
plugins.get_pre_tool_call_block_message("terminal", {...}, feedback_sink=sink)
# → block=None AND collected == [feedback line] in ONE call (single pass)
mgr._hooks["pre_tool_call"].remove(fake_observe_hook)
```
PASS: block=None, one feedback collected from a single invocation.

### Pitfall 1 — feedback collection must ride the EXISTING single-fire call

First attempt added a separate `get_pre_tool_call_feedback()` call right
after the block check. Two problems discovered live:
- **Double-fire risk**: `invoke_hook("pre_tool_call")` would run again →
  capability-reuse's observer hooks fire twice per tool call (duplicate
  events, broken exactly-once assumptions).
- **Wrong branch**: the first patch landed in the `execute_tool_calls_concurrent`
  branch (~line 396-430), which is NOT the path real tool calls take. The
  actual dispatch calls `handle_function_call(..., skip_pre_tool_call_hook=True)`
  because the hook ALREADY fired in the pre-execution gate at ~line 958.
  Lesson: when adding behavior to the pre_tool_call hook, extend
  `get_pre_tool_call_block_message()` itself (sink param) and wire the sink
  at the ~958 gate where `agent` is in scope — not in a parallel function,
  not in the concurrent branch.

### Pitfall 2 — a new plugin must be added to `plugins.enabled` in config.yaml

After restart the plugin was discovered ("54 found, 47 enabled") but produced
no feedback. Root cause: `plugins.enabled` in `~/.hermes/config.yaml` listed
only `hmp` and `capability-reuse` — discovery enumerates but does NOT load
plugins outside the enabled list. Fix:
```yaml
plugins:
  enabled:
    - hmp
    - capability-reuse
    - harness-feedback
```
then restart. Verify loading via `grep "Plugin discovery complete" agent.log`
(47 enabled after adding = loaded).

### Pitfall 3 — `.bak-*` dirs inside `skills/hermes/` collide as skill names

After the 2.4.17 plugin-runtime fix, `skills/hermes/capability-reuse.bak-246/`
caused `Skill name collision for 'capability-reuse': 2 candidates` and
`Ambiguous skill name` errors. Backups of skills must live OUTSIDE the skills
tree (e.g. `~/.hermes/skills-archive-*`), not as `*.bak-*` siblings — the
skill loader scans every subdir.

**Rollout status:** after the FINAL patch + restart, every tool call shows a
`🔍 azione considerata · harness ... (dummy)` bubble on Telegram. For 2.4.18:
replace the dummy rule with real capability-reuse retrieval decisions.

## Pitfall 4 — 0.20.1: the gateway does NOT load `~/.hermes/.env` into os.environ

The peer70 0.17.0 dummy gate `HARNESS_FEEDBACK_MODE=dummy` (env var) works on
peer70 but is INVISIBLE on a 0.20.1 core: verified via
`tr '\0' '\n' < /proc/<gwpid>/environ` — no `.env` variable (not even
`TELEGRAM_BOT_TOKEN`) reaches the gateway process env; adapters read
config.yaml (HMP `gateway.platforms.hmp.*`) or the secrets store instead.
Consequence: `os.environ.get("HARNESS_FEEDBACK_MODE")` is always None in the
gateway → `_enabled()` False → the plugin returns None → NO observe dict →
NO bubble, with zero errors in the log. Symptom: plugin listed as enabled,
gateway on new code, but no 🔍 bubble.

Fix (v0.1.1): the plugin reads its mode from
`plugins.entries.harness-feedback.settings.mode` in config.yaml via
`ctx.get_config("mode", ...)` (PluginContext method, hermes_cli/plugins.py
~1422; set with `hermes config set plugins.entries.harness-feedback.settings.mode dummy`),
keeps the env var only as a legacy fallback, and defaults to ON when unset
(being in `plugins.enabled` IS the opt-in). Capture `_CTX = ctx` at
`register()` time — hook callbacks receive no ctx in their kwargs.

Also on 0.20.1: `hermes config set plugins.enabled '["hmp", ...]'` writes a
JSON STRING, not a YAML list — the gateway then ignores it. Correct the
`plugins.enabled` block by hand to a real YAML list (peer70 fixed this
2026-08-14). Prefer `hermes config set` for scalar/leaf values only.

## Why this is the right place

- The "consideration" Hermes does before acting IS the `pre_tool_call` hook
  — same seam capability-reuse already uses for `authorize_execute_code`.
- The bubble rendering pipeline (progress_queue) already exists and is
  platform-aware (Telegram fenced blocks, emoji, dedup, interrupt guard).
- Making capability-reuse's intervention decision visible ("harness
  applicato/non applicato") turns an invisible shadow decision into an
  auditable one, without changing retrieval semantics.

## Key file/line pointers (peer70 checkout, 2026-08-14)

- `gateway/run.py:15479` — progress_callback definition
- `gateway/run.py:15349-15407` — tool_progress resolution + progress_queue
- `gateway/run.py:16456` — agent.tool_progress_callback wiring
- `hermes_cli/plugins.py:1982` — get_pre_tool_call_block_message
- `hermes_cli/plugins.py:1780` — PluginManager.invoke_hook
- `hermes_cli/plugins.py:319` — PluginContext (register_hook ~1048)
- `model_tools.py:910/1049` — pre_tool_call single-fire dispatch
- `run_agent.py:4286` — _emit_interim_assistant_message
- `agent/display.py` — get_tool_emoji, tool preview caps
