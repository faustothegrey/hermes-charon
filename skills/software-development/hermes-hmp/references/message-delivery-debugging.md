# HMP message delivery debugging — where messages actually live, why logs look truncated

Lesson 2026-08-15/16: the recurring "messaggio troncato / non processato" confusion
between peer70 and peer141. The message was almost always DELIVERED INTACT — the
"truncation" was in the logs and in agent-side display truncation, not the protocol.

## 1. The gateway log preview truncates to 80 chars — it is NOT the message

`gateway/run.py` (~line 9649, `_handle_message_with_agent`):

```python
_msg_preview = (event.text or "")[:80].replace("\n", " ")
logger.info("inbound message: ... msg=%r ...", ..., _msg_preview, ...)
```

Every inbound message is logged with ONLY its first 80 chars. A long report from a
peer (e.g. 2283 chars) appears as `msg='peer70, REAL-GATEWAY DISPATCH SMOKE PASS
sul mio runtime (peer141, core 0.20.'` — looks truncated/cut mid-sentence. It is NOT:
the full text was queued and processed. NEVER conclude "message truncated / not
processed" from the gateway.log preview alone.

**Fix (if it ever matters for log reading):** raise the preview cap or append a
`…(+N chars)` marker — but the protocol itself never truncates.

## 2. The real HMP message store

| Path | What it is |
|---|---|
| `~/.hermes/data/hmp_gateway_plugin/messages.db` | **THE live HMP store** (`DEFAULT_DB_PATH` in `plugins/hmp/core.py`). Table `hmp_gateway_messages`. |
| `~/.hermes/data/hmp/agent_messages.db` | DEAD dual-plane relic (last write Jul/Aug, retired with :18644). Empty/irrelevant. Do not query it. |

Status lifecycle: `queued → delivering → completed | failed | timed_out`.
`delivering` means the consumer took it and dispatched to the gateway — a message
stuck in `delivering` for a long time is a *hung turn*, not a truncation.

Debug recipe (full text of what actually arrived):

```python
import sqlite3
con = sqlite3.connect("~/.hermes/data/hmp_gateway_plugin/messages.db")
cur = con.cursor()
cur.execute("SELECT message_id, from_peer, to_peer, status, length(text), updated_at "
           "FROM hmp_gateway_messages ORDER BY rowid DESC LIMIT 10")
for r in cur.fetchall(): print(r)
# full text of one message:
cur.execute("SELECT text FROM hmp_gateway_messages WHERE message_id = ?", (mid,))
```

## 3. The API returns 413 — it NEVER truncates

Verified on peer70 AND peer141 (v0.1.4):

- `POST /hmp/send`, `/hmp/send_and_wait`, `/send` (dual-plane alias), body form
  `{message: ...}` AND `{payload: {text: ...}}`:
  - 2048 bytes → HTTP 202 accepted
  - 2049+ bytes → HTTP 413 `{"error": "message_too_large", "max_bytes": 2048, "actual_bytes": N}`
- Guard lives in `adapter.py::_accept_hmp_message` (`MAX_MESSAGE_BYTES = 2048`),
  measured on `len(text.encode("utf-8"))` — bytes, not chars.
- Consumer passes `text` intact to `MessageEvent`; `send()` writes `response_text`
  intact. No truncation anywhere in the plugin.

## 4. `send_and_wait` timeout does NOT mean "not delivered"

`POST /hmp/send_and_wait` blocks until the peer's turn completes (default
`request_timeout_seconds`). Long peer tasks (implementation + restart + smoke,
400s+) exceed the client timeout → the client sees timeout/error, but the message
was already queued and the peer WILL process it. On timeout:
- Check the peer's `hmp_gateway_plugin/messages.db` for the message (status
  `completed` / `response_text` present) BEFORE re-sending.
- Or poll `/hmp/poll/{message_id}` — the response is stored server-side.
- To get a long report back, ask the peer for a COMPACT reply (max N chars) or
  follow up with a targeted question instead of re-sending the whole task.

## 5. Agent-side display truncation (self-inflicted)

Reading HMP responses with `python3 -c "... (d.get('response_text') or '')[:600]"`
truncates the PRINTED response — the stored response is full. When a peer's reply
"seems cut off", print the full length or the tail before concluding anything:
`print(len(t), t[-200:])`.

## 6. Verifying delivery end-to-end (probe)

Send a long-but-under-limit message with a unique marker, then grep the RECIPIENT's
DB (not the log):

```bash
# sender side
curl -s -X POST http://<peer>:18643/hmp/send -H 'Content-Type: application/json' \
  -d "{\"to\": \"peer70\", \"message\": \"$(python3 -c "print('Z'*1750 + 'UNIQUE-MARKER')")\"}"
# recipient side — marker must appear in full
ssh <peer> "python3 -c \"import sqlite3; c=sqlite3.connect('~/.hermes/data/hmp_gateway_plugin/messages.db'); \
  print([r for r in c.execute('SELECT text FROM hmp_gateway_messages ORDER BY rowid DESC LIMIT 3')])\""
```
