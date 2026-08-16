# HMP trace_id end-to-end propagation — data-path analysis (2026-08-16, G0 P0-10)

## Problem

G0 requires a request-unique trace_id (UUID v4) correlating the whole chain:
HMP ingress → Capability Reuse real retrieval → observe/result. Generating the
UUID in the adapter is NOT enough: it must reach the `pre_llm_call` hook
context, where the retriever reads it.

## Verified data path (read from source, Charon 0.17.0)

```
adapter._process_item() → uuid.uuid4() generated (done)
  → MessageEvent(raw=body, source=SessionSource)
  → BasePlatformAdapter.handle_message(event)   (gateway/platforms/base.py:4322)
  → gateway runner (gateway/run.py) → AIAgent(user_id=source.user_id, chat_id=source.chat_id, ...)
  → agent/turn_context.py:419-430 → invoke_hook("pre_llm_call", kwargs)
```

## The break point

`agent/turn_context.py:419-430` hardcodes the hook kwargs:
`session_id, task_id, turn_id, user_message, conversation_history,
is_first_turn, model, platform, sender_id=agent._user_id`.

- NO `trace_id`, NO `chat_id`, NO `requester_peer_id` are passed.
- `event.raw_message` does NOT reach turn_context (run.py uses it only for
  Discord `_get_guild_id()` at run.py:11564).
- `MessageEvent` has no free metadata field that survives to the hook
  (`SendResult.metadata` is outbound-only).

## Why Capability Reuse ends up with trace_id = peer58

`plugins/capability-reuse/retriever.py:583-598` resolution order:
1. `hook_context["trace_id"]` → never present
2. `hook_context["chat_id"]` → never present
3. platform == "hmp" → `sender_id` = `agent._user_id` = `source.user_id` = from_peer
→ trace_id = peer58. The v2.5.0 B5 fallback chain only kicks in because the
upstream UUID never arrives.

## Minimal plumbing (4 touches, NO capability-reuse 2.6.0 change)

| # | File | Change |
|---|------|--------|
| 1 | `plugins/hmp/adapter.py` | set `event.source.trace_id = uuid` (or a dedicated MessageEvent field) |
| 2 | `gateway/run.py` (AIAgent construction) | `trace_id=getattr(event, "trace_id", None)` |
| 3 | `agent/agent_init.py` | `self._trace_id = trace_id or ""` |
| 4 | `agent/turn_context.py` | add `trace_id=getattr(agent, "_trace_id", "")` to hook kwargs |

The retriever already reads `hook_context["trace_id"]` FIRST → capability-reuse
uses the propagated UUID with ZERO changes to the ACCEPTed 2.6.0 release.
Expected result per request: same UUID-X in HMP ingress, Cap Reuse retrieval,
observe/result; second request → UUID-Y.

## Verification recipe

- After deploy + gateway restart: send a real HMP message with
  `provenance: organic_live`, then check `~/.hermes/data/reuse-observer/events.jsonl`:
  `retrieval_event` + `surface_execution_*` must share the same UUID v4 trace_id.
- A capability-reuse real retrieval_event (if triggered) must carry the SAME trace.
- Two requests → two distinct UUIDs.
