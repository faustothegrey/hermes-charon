# HMP as Hermes Gateway Plugin

The proper architecture for HMP (Hermes Mesh Protocol) is a **Hermes Gateway Platform Plugin**, not a separate `hmp.py server` process. This guarantees every incoming HMP message is delivered to the Hermes agent, not just stored in a SQLite bus.

## Why a Gateway Plugin

| Approach | Message reaches Hermes agent? | Maintenance |
|----------|------------------------------|-------------|
| `hmp.py server` + `worker_llm.py` | Best-effort (worker calls Hermes CLI) | Two scripts to maintain |
| **Gateway Plugin** on `:8642` | **Guaranteed** (native gateway pipeline) | One plugin, standard API |

The gateway plugin model (see `gateway/platforms/ADDING_A_PLATFORM.md` in the Hermes repo):

1. Incoming `POST /hmp/send` → plugin creates `MessageEvent` → gateway routes to Hermes agent
2. Agent processes → calls `adapter.send()` → plugin POSTs response back to sender
3. All state is tracked via the existing HMP `/hmp/poll/` endpoint (HTTP surface only)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Hermes Gateway Process (port 8642)                      │
│                                                           │
│  ┌──────────────┐    ┌────────────────────────────────┐  │
│  │ Telegram     │    │  HMP Gateway Plugin             │  │
│  │ Discord      │    │  plugins/platforms/hmp/         │  │
│  │ WhatsApp     │    │                                │  │
│  │ ...          │    │  POST /hmp/send → MessageEvent │  │
│  └──────────────┘    │  GET  /hmp/poll/{id} → status  │  │
│                      │  GET  /health → ok             │  │
│                      └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                              │
                    HTTP requests from peers
                    (no SQLite access)
```

## Plugin Structure

### `~/.hermes/plugins/hmp/plugin.yaml`

```yaml
name: hmp
description: "Hermes Mesh Protocol — peer-to-peer agent communication"
version: 1.0.0
author: Hermes Agent
```

### `~/.hermes/plugins/hmp/adapter.py`

The adapter subclasses `BasePlatformAdapter` and implements:

```python
from gateway.platforms.base import (
    BasePlatformAdapter, MessageEvent, MessageType, SendResult
)

class HMPAdapter(BasePlatformAdapter):
    def __init__(self, config, platform):
        super().__init__(config, platform)
        self._httpd = None

    async def connect(self, *, is_reconnect=False):
        # Start HTTP server on port 8642 that handles:
        #   POST /hmp/send → handle_message(MessageEvent(...))
        #   GET /hmp/poll/{id} → return message status
        #   GET /health → {"status":"ok"}
        # The HTTP server shares port 8642 with the Hermes gateway.
        # Each POST /hmp/send becomes a MessageEvent in the gateway pipeline.

    async def disconnect(self):
        # Stop HTTP server, cancel tasks

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        # POST response back to the requesting peer's HMP endpoint
        # chat_id = sender peer name (e.g., "peer106")
        # content = response payload (JSON string)
```

### Registration

The `register(ctx)` entry point calls `ctx.register_platform()` with the adapter class:

```python
def register(ctx):
    ctx.register_platform(
        name="hmp",
        adapter=HMPAdapter,
        description="Hermes Mesh Protocol",
        env_enablement_fn=lambda: {"enabled": True},
    )
```

## HTTP Surface

The plugin exposes the same HTTP endpoints as the standalone HMP server, now on port 8642:

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| `GET` | `/hmp/health` | → `{"status":"ok"}` | Liveness |
| `GET` | `/hmp/agent-card` | → `agent_card` | Capabilities |
| `GET` | `/hmp/poll/{id}` | → `bus.get_message(id)` | Poll status |
| `POST` | `/hmp/send` | → `MessageEvent` | Submit message |
| `POST` | `/hmp/cancel/{id}` | → `bus.update_status(cancelled)` | Cancel |

## send_and_wait — Client-Side

The client side remains unchanged — it's pure HTTP to the peer's gateway:

```python
import json, time, urllib.request

def send_and_wait(peer_url, msg, poll_interval=3, timeout=60):
    \"\"\"Pure HTTP — no DB access, no internal state peek.\"\"\"
    # 1. Send
    data = json.dumps(msg).encode()
    req = urllib.request.Request(
        f"{peer_url}/hmp/send", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    if "error" in result:
        return result
    mid = result["message_id"]

    # 2. Poll until terminal
    deadline = time.time() + timeout
    while time.time() < deadline:
        req = urllib.request.Request(f"{peer_url}/hmp/poll/{mid}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = json.loads(resp.read())
        s = status.get("status")
        if s in ("completed", "failed", "timed_out", "cancelled"):
            return status
        time.sleep(poll_interval)

    return {"status": "timed_out", "message_id": mid}
```

## File-Based State (Alternative)

For peers that don't run a full gateway but still want to exchange structured messages, the **file-based approach** is an alternative to SQLite:

```python
import json, os, time, threading

MESSAGES_FILE = "/path/to/hmp_messages.json"
_lock = threading.Lock()

def _read():
    with _lock:
        if os.path.exists(MESSAGES_FILE):
            with open(MESSAGES_FILE) as f:
                return json.load(f)
        return {"messages": [], "next_id": 1}

def _write(data):
    with _lock:
        with open(MESSAGES_FILE, "w") as f:
            json.dump(data, f, indent=2)

def create_message(msg):
    data = _read()
    msg["status"] = "pending"
    msg["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["messages"].append(msg)
    _write(data)
    return msg["message_id"]

def get_message(message_id):
    data = _read()
    for msg in data["messages"]:
        if msg["message_id"] == message_id:
            return msg
    return None

def poll_message(message_id):
    msg = get_message(message_id)
    if msg:
        return {"status": msg["status"], "payload": msg.get("payload")}
    return {"status": "not_found"}
```

This avoids the SQLite dependency entirely while keeping the same HTTP surface. The `send_and_wait` function above is unaffected — it talks HTTP, not storage.

## Why Not Both Ports?

Two confusion risks with running both the standalone `hmp.py server` (`:8643`) AND the gateway plugin (`:8642`):

1. **Split state** — messages stored in two different SQLite DBs (one under `~/.hermes/data/hmp/`, one under the gateway's own store)
2. **Sync problem** — who processes which? The gateway plugin would handle POSTs to `:8642/hmp/send`, the standalone server handles `:8643/hmp/send` — a message sent to `:8643` would NOT reach the Hermes agent

**Solution:** Run ONLY the gateway plugin (on `:8642`, sharing the Hermes gateway process). Remove the standalone `hmp.py server` cron/systemd services and the `worker_llm.py` scripts. The plugin handles both `send` and `poll` through the gateway.

## Migration Path

1. Create `~/.hermes/plugins/hmp/adapter.py` + `plugin.yaml`
2. Enable in config: `hermes gateway setup` → HMP → enabled
3. Restart gateway: `hermes gateway restart`
4. Verify: `curl http://localhost:8642/hmp/health`
5. Update peer registry: all peers now target `:8642` instead of `:8643`
6. Remove old services: `systemctl disable --now hmp-server hmp-worker` (or `launchctl unload`)
7. Remove `worker_llm.py` scripts
