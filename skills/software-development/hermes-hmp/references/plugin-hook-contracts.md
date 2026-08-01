# Hermes Plugin Hook Contracts (v0.17.0)

Discovered through code inspection of `~/.hermes/hermes-agent/hermes_cli/plugins.py`
on peer70, 2026-07-26. These are documentation-level evidence — the executable
conformance suite (§3.3) remains the sole source of truth for deployment.

## VALID_HOOKS

Defined in `hermes_cli/plugins.py:VALID_HOOKS`:

```
pre_tool_call, post_tool_call
transform_terminal_output, transform_tool_result, transform_llm_output
pre_llm_call, post_llm_call
pre_api_request, post_api_request, api_request_error
on_session_start, on_session_end, on_session_finalize, on_session_reset
subagent_start, subagent_stop
pre_gateway_dispatch
pre_approval_request, post_approval_response
kanban_task_claimed, kanban_task_completed, kanban_task_blocked
```

### Lifecycle hooks (session boundary)
- `on_session_start` — new session created
- `on_session_end` — session ending (agent deciding)
- `on_session_finalize` — session fully finalized
- `on_session_reset` — session reset (/new)

### Agent hooks (turn/tool boundary)
- `pre_llm_call` — once per turn, before LLM call
- `post_llm_call` — once per turn, after LLM response
- `pre_tool_call` — before each tool call
- `post_tool_call` — after each tool call (success, failure, or blocked)

## Hook Kwargs

### pre_llm_call
Documented kwargs: `session_id`, `user_message`, `conversation_history`,
`is_first_turn`, `model`, `platform`.

No planner state, structured constraints, or active-target register.
Uses `**kwargs` pattern for forward compatibility.

**Return contract:** `None` (no action) or `{"context": str}` (injected into
user message, ephemeral, never system prompt).

### post_llm_call
Fires after LLM response. Return value: `None` or `{"context": str}` (appended
to user message for next turn).

### pre_tool_call
Kwargs: `tool_name: str`, `args: dict`, `task_id: str`, plus `**kwargs`.

**Block contract:**
```python
return {"action": "block", "message": "Human-readable reason"}
```
Returning this short-circuits the tool and returns `message` as the tool error
result to the model. First valid block wins across all registered plugins
(Python hooks evaluated before shell hooks).

**Allow contract:** `return None` — tool proceeds normally.

### post_tool_call
Kwargs: `tool_name: str`, `args: dict`, `result: Any`, `task_id: str`,
`duration_ms: int`, plus `**kwargs`.

Fires for all outcomes: success, failure (exception), and plugin-blocked
(gets the block message as result). No return value expected (observer only).

## Plugin Discovery

1. **Source priority** (highest to lowest): bundled → general (`plugins/`) → pip entry point
2. **General plugin path:** `~/.hermes/plugins/<name>/plugin.yaml` + `__init__.py`
3. **Plugin.yaml** must have `name`, `hooks` list, optional `tools`.
4. **Project-local plugins** are used only when explicitly enabled and trusted.
5. **Same-name collision:** later sources override on name collision.
6. **`register(ctx)`** is the entry point — receives `PluginContext` with
   `register_tool()`, `register_hook()`, etc.

## Tool Registration

```python
ctx.register_tool(
    name="invoke_capability",
    toolset="capability_reuse",
    schema={...},       # JSON schema for arguments
    handler=callable,   # receives (params, **kwargs) -> str (JSON)
    description="...",
)
```

**Tool visibility:** Non-core/plugin tools may be filtered by toolsets or
deferred behind a tool-search bridge. Progressive disclosure can make a
registered tool invisible on some sessions. The conformance suite must verify
the tool is directly callable on each target deployment.

## Fail-Open Behavior

A crashing callback is logged and skipped. The agent continues. Plugin callbacks
must not be relied upon as safety controls.

## Concurrent Tool Dispatch

`pre_tool_call` fires once per tool call, including concurrent calls. Each
invocation has its own `task_id`. Multiple concurrent `invoke_capability` or
`execute_code` calls can arrive without sequential ordering.

## Approval Pipeline

The Hermes approval system (including smart-mode assessment of `execute_code`
scripts) operates independently of plugin hooks. Blocked-then-resubmitted
`execute_code` can traverse the approval pipeline twice in degraded mode.

## Subagent Lifecycle

`subagent_start` / `subagent_stop` expose parent-child delegation mapping only.
They do NOT prove child tool calls. `delegated_execution_coverage = "unknown"`
until child tool events are directly observable and correlated.

## Plugin Discovery Order for pre_llm_call Injection

Multiple plugins' context is joined in **plugin discovery order** (alphabetical
by directory name). The intervention's position relative to co-resident plugins
is recorded in provenance.

## Shell Hooks

User-configured shell hooks share the same `invoke_hook()` dispatcher and can
independently block tools or inject context. Python plugin hooks are evaluated
first; first valid block directive wins.
