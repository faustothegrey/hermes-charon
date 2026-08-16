# HMP send semantics — local injection vs real cross-peer send (2026-08-16)

Discovered during the observe-channel runtime-proof (peer70 requester →
peer141 executor). Misusing the local endpoint makes your message loop back
into your OWN session — it looks like it went out but it never reached the
peer.

## `POST /hmp/send` on the LOCAL gateway = LOCAL INJECTION, not a send

`hmp_send` in `adapter.py` calls `_accept_hmp_message()` →
`BasePlatformAdapter.handle_message()` — the message is executed by the
LOCAL agent in the chat named by `session_id` and reappears in your own
conversation (the exact text comes back as a user message). Do NOT use your
own gateway's `/hmp/send` to send to another peer.

## REAL cross-peer send: POST to the TARGET's gateway

```
curl -X POST http://<target-peer>:18643/hmp/send \
  -H 'Content-Type: application/json' \
  -d '{"from_peer":"<your-peer-id>","session_id":"<target-chat>","text":"..."}'
```

- `from_peer` is read from the BODY by `extract_peer()` in `core.py`:
  `body.get("from") or body.get("from_peer") or body.get("peer")
  or body.get("sender") or "unknown"`. Setting `from_peer=<your own id>` is
  the CORRECT mesh identity (how the requester is attributed), not spoofing.
- `session_id` = the destination chat on the target (peer id for DMs).
- Health/agent-card probes before sending:
  `GET http://<peer>:18643/hmp/health` → `{"node_id": "<peer>", ...}`.
- Verify delivery: the receiving peer names back the exact `message_id` you
  got (`{"accepted": true, "message_id": "hmp_...", "status": "queued"}`) —
  that cross-check proves the envelope arrived with your requester identity.

## Endpoints (v0.1.4, `agent-card`)

`/health`, `/hmp/health`, `/hmp/agent-card`, `/hmp/send`, `/hmp/send_and_wait`
(blocking, polls store until completed/timed_out), `/send` (retired dual-plane
alias — blocking send_and_wait semantics), `/hmp/poll/{message_id}`.

## Runtime-proof trigger pattern (mesh e2e)

To make the target run a real tool call AND have a retrieval active in the
same turn, craft the text as: a retrieval-matchable request (e.g.
"check HMP health for peer58 and peer70") + a terminal command ("then run
the terminal command: echo v250-observe-mesh"). The retrieval fires at
`pre_llm_call` (envelope active), the terminal call at `pre_tool_call`
(observe bubble). Requires the target gateway to run the plugin version
that emits the bubble (restart after plugin sync — a stale gateway silently
"doesn't match").
