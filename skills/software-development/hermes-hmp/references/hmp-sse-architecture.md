# SSE Streaming Architecture — HMP Plugin v0.2.0+

## Overview

The HMP plugin v0.2.0 adds Server-Sent Events (SSE) streaming. Instead of
polling `/hmp/poll/{id}`, a client can open `GET /hmp/stream/{id}` and
receive `event: progress` / `event: complete` SSE events as the agent
produces output.

## Core Components (in-memory, no DB changes)

```
SSEStreamStore (core.py)
  └─ asyncio.Queue per message_id
      └─ subscribe() → async generator yielding SSEEvent
      └─ push_progress(mid, text)  → push progress event
      └─ push_complete(mid, text)  → push + sentinel (None)
```

## Adapter Flow

```
POST /hmp/send
  → _accept_hmp_message()
    → store.accept(), store.mark("gateway_accepted")
    → MessageEvent → await handle_message(event)
    → *** handle_message() spawns BACKGROUND TASK, returns immediately ***
    → store.mark_status("working")
    → return {accepted, status: "working"}

  BACKGROUND TASK (runs later):
    → agent processes message
    → adapter.send() called with final response
      → sse.push_progress(mid, text)
      → store.complete(mid, text, ...)
      → sse.push_complete(mid, text)
```

## CRITICAL: handle_message() is async

`BasePlatformAdapter.handle_message()` spawns a background task and returns
quickly. The agent's response comes asynchronously via `adapter.send()`.

```python
# WRONG — agent hasn't produced output yet:
await self.handle_message(event)
response_text = await some_accumulator()   # EMPTY!
self.store.complete(mid, response_text)    # completes with empty!

# RIGHT — let send() handle completion asynchronously:
await self.handle_message(event)
self.store.mark_status(message_id, "working")
return {"accepted": True}, 202
# send() is called later by the background task.
```

## SSE Endpoint Behaviour

| State | Client sees |
|-------|-------------|
| Already completed | Single `event: complete\ndata: <text>` immediately |
| Still processing | Blocks, sends events as they arrive |
| Agent output | `event: progress\ndata: <chunk>` |
| Agent finishes | `event: complete\ndata: <final>` |
| Client disconnect | StreamConsumer catches error, cleans up queue |

## Interim Streaming — Current State

### Works: real-time delivery of the final response

`send()` is called once with the complete response → one progress + one complete event.

### Does NOT work: tool-level progress

Tool-level progress (e.g. "🔧 Eseguo: ls" then "📋 Trovati 5 file") requires
the gateway to call `adapter.send()` multiple times. This depends on:

1. **`_PLATFORM_DEFAULTS`** — without an "hmp" entry, defaults may not enable streaming.
2. **`SUPPORTS_MESSAGE_EDITING = False`** — prevents stream consumer creation (good for HMP since it can't edit messages).
3. **Model/provider** — deepseek/deepseek-v4-flash produces everything in one `send()` call.
4. **`send_or_update_status()`** — defined on HMPAdapter, but tool progress may not route to non-streaming adapters.

### _PLATFORM_DEFAULTS fix (approach B)

Add to `hermes-agent/gateway/display_config.py`:

```python
"hmp": {**_TIER_MEDIUM, "streaming": False},
```

This sets: `tool_progress="new"`, `interim_assistant_messages=True`,
`streaming=False`. Even with this, tool-level interim depends on the model.

## Key Discoveries from Implementation

### Platform("hmp") identity

`Platform("hmp")` works because `_missing_()` checks `platform_registry`.
After `register_platform()` is called, `Platform("hmp")` creates a cached
pseudo-member via `_value2member_map_`. `Platform("hmp") is Platform("hmp")`
is True (identity-stable), critical for adapter lookups.

### HMP is NOT a bundled plugin

`_Platform__bundled_plugin_names` scans only `hermes-agent/plugins/platforms/`.
User plugins under `~/.hermes/plugins/hmp/` rely on `platform_registry`.

### StreamConsumer fallback

With `SUPPORTS_MESSAGE_EDITING = False`, the stream consumer setup raises
at line 16224 of run.py, caught silently. The `_interim_assistant_cb` then
falls back to `_status_adapter.send()`.

## Testing

```bash
# Send message and stream response
MSGID="test_$(date +%s%N)"
curl -s -X POST http://peer106:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"'${MSGID}'","from":"peer70","to":"peer106","type":"request","timeout":30,"payload":{"text":"Rispondi solo: OK"}}'
timeout 30 curl -sN http://peer106:18643/hmp/stream/$MSGID

# Verify backward compat
curl -s http://peer106:18643/hmp/poll/$MSGID
```
