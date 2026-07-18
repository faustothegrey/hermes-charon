# HMP — Hermes Mesh Protocol

The HMP protocol is a lightweight, stdlib-only message-passing layer that runs alongside the Hermes API (`:8642`) on a dedicated port. There are TWO implementations:

| Implementation | Port | Backend | When to use |
|----------------|------|---------|-------------|
| **Hermes gateway plugin** (`plugins/hmp/`) | `18643` | Hermes agent session (full processing) | Peers that run Hermes Agent with gateway enabled |
| **Standalone hmp.py** | `8643` | SQLite bus + custom worker | Peers without Hermes Agent, or simple ping/pong only |

**Port 18643** is the new default via the Hermes gateway plugin. The old standalone `hmp.py` on `8643` is legacy — prefer the gateway plugin when the peer runs Hermes.

ARCHITECTURE NOTE — Updates from session 2026-07-15:

HMP now has FOUR components (previously three): HMPBus, HMPClient, HMPServer/ThreadingHMPHTTPServer,
plus the new HMPWorker and HMPCoordinator. The Worker closes the gap between "message stored on bus" and
"message processed by agent" by polling the local bus, sending ACK/responses, and enforcing terminal states.
The Coordinator runs on peer70 to detect stale deliveries, stale workers, and timed-out messages.

See sections below for full Worker and Coordinator documentation.

## Architecture

`hmp.py` implements **five components** in one file (zero dependencies beyond stdlib):

| Component | Role |
|-----------|------|
| `HMPBus` | SQLite-backed message queue with state machine |
| `HMPClient` | HTTP client for non-coordinator peers |
| `HMPServer` / `ThreadingHMPHTTPServer` | HTTP server handling concurrent requests |

### Threading

```python
from socketserver import ThreadingMixIn
from http.server import HTTPServer

class ThreadingHMPHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
```

- `ThreadingMixIn` spawns a new thread per request
- `daemon_threads = True` ensures threads don't block server shutdown
- `allow_reuse_address = True` prevents "address already in use" on restart

## State Machine

### States (6)

```
pending → queued → delivered → working → completed
                                  ↓
                             failed / timed_out
```

| State | Meaning |
|-------|---------|
| `pending` | Message accepted but not yet queued for delivery |
| `queued` | In the delivery queue for the target peer |
| `delivered` | Received by the target peer's HMPServer |
| `working` | Being actively processed by the target |
| `completed` | Processing finished successfully |
| `failed` | Processing failed |
| `timed_out` | Processing exceeded time limit |
| `cancelled` | Explicitly cancelled before processing |
| `needs_input` | Processing paused, awaiting user input |

### Terminal States

```python
TERMINAL_STATES = {completed, failed, timed_out, cancelled}
```

Messages in terminal states **cannot transition** — `update_status` returns an error if attempted:

```python
if old in TERMINAL_STATES:
    return {"error": f"Invalid transition: {old} is terminal, cannot transition to {new_status}"}
```

### Valid Transitions

```python
TRANSITIONS = {
    pending:  [queued, cancelled],
    queued:   [delivered, cancelled],
    delivered:[working, needs_input, cancelled],
    working:  [completed, failed, timed_out, needs_input],
    needs_input: [working, completed, failed, cancelled],
}
```

## API Endpoints

All on port `:8643`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status":"ok","service":"hmp","version":"1.0"}` |
| GET | `/hmp/agent-card` | Returns this peer's agent card with availability_window |
| GET | `/hmp/discover` | Returns known peers (currently self only) |
| GET | `/hmp/poll/<message_id>` | Poll for a message by ID (returns full row) |
| POST | `/hmp/send` | Submit a new message (with idempotency_key dedup) |
| POST | `/hmp/update` | Transition message status |
| POST | `/hmp/ack` | Acknowledge receipt without status change |
| POST | `/hmp/cancel` | Cancel a pending/queued/delivered message |

### /hmp/agent-card Response

```json
{
  "peer_id": "peer70",
  "hmp_version": "1.0",
  "version": "hmp-1.0",
  "capabilities": ["coordinator"],
  "availability_window": {
    "always_available": true
  }
}
```

The `availability_window` is read from config (`~/.hermes/hmp-config.json`). Peers can declare maintenance windows, off-hours, or always-available status.

## Message Format

```json
{
  "hmp_version": "1.0",
  "message_id": "msg_a1b2c3d4e5f6",
  "idempotency_key": "send_20260714_backup_report",
  "from": "peer70",
  "to": "peer84",
  "type": "task",
  "subtype": "research",
  "payload": { ... },
  "timestamp": "2026-07-14T12:00:00Z",
  "metadata": {}
}
```

Required fields: `hmp_version`, `message_id`, `idempotency_key`, `from`, `to`, `type`, `timestamp`.

## Sending Messages via the Gateway Plugin (`:18643`)

When sending to a peer that uses the Hermes gateway plugin, the `/hmp/send` endpoint
extracts the message text from the payload. The key lookup priority is:

1. `payload.text`
2. `payload.content`
3. `payload.message`
4. `payload.query`
5. (fallback) top-level `text`, `content`, `message`, `query`

**CRITICAL**: `payload.instruction` is NOT a recognized text key. Always use `payload.text`:

```bash
curl -s -X POST "http://<peer>:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d '{
    "hmp_version": "1.0",
    "message_id": "msg_'$(date +%s%N)'",
    "idempotency_key": "msg_'$(date +%s%N)'",
    "from": "peer70",
    "to": "peer84",
    "type": "request",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "payload": {
      "text": "Il messaggio che il peer deve processare"
    }
  }'
```

If `payload.text` is missing or empty, the endpoint returns:
```json
{"accepted": false, "message_id": "...", "error": "empty_text"}
```

The gateway plugin processes the message through Hermes' normal agent session machinery
(`handle_message()`), so the receiving peer's agent actually reads and responds to it —
not just stored in a bus.

## Bus Operations (HMPBus)

### Message Lifecycle

1. **send_message()** — validates, checks idempotency_key, inserts as `pending`, returns `{ok, message_id, duplicate}`
2. **route_message()** — transitions `pending → queued` (adds to delivery queue) or `queued → delivered` (mark as received)
3. **claim_message()** — transitions `delivered → working` (peer picks it up)
4. **update_status()** — state machine guard with TERMINAL_STATES check, transition validation
5. **complete/fail/timeout** — transitions to terminal states

### Query Methods

```python
get_pending(to_peer=None, limit=50)   # SELECT WHERE status IN (pending, queued)
get_working()                           # SELECT WHERE status = working
get_stalled(max_age_seconds=300)        # working messages with no heartbeat
get_message(message_id)                 # SELECT by primary key
count_pending()                         # COUNT WHERE status IN (pending, queued)
```

Each query method uses direct SQL with explicit state filters — no race conditions from compound WHERE clauses.

### Heartbeat Pattern

The `working` state requires periodic heartbeats. `get_stalled()` finds messages where `updated_at` is older than `max_age_seconds` while status is `working`. These can be auto-marked as `timed_out`.

### Maintenance

```python
archive_old_messages(days=30)          # DELETE terminal messages older than N days
cleanup_idempotency_keys(days=7)       # DELETE old messages with idempotency_key
compact()                              # VACUUM / WAL checkpoint
```

`archive_old_messages` only deletes terminal-state messages (safe garbage collection).  
`cleanup_idempotency_keys` is more aggressive — it deletes any message with an idempotency_key older than N days, regardless of state (safe because 7+ day old messages with tracking keys are always terminal in practice).

## Config File

`~/.hermes/hmp-config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8643,
  "db_path": "~/.hermes/data/hmp/agent_messages.db",
  "availability_window": {
    "always_available": true
  },
  "agent_card": {
    "peer_id": "peer70",
    "capabilities": ["coordinator"]
  }
}
```

## Server Installation on a New Peer

To bring a new peer into the HMP mesh with a full server (bidirectional communication):

### 1. Copy hmp.py to the peer

```bash
scp fausto@<coordinator-ip>:/home/fausto/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts/hmp.py ~/hmp.py
```

### 2. Create config file

`~/.hermes/hmp-config.json`:

```json
{
  "peer_name": "peerNN",
  "peer_role": "worker",
  "cluster_role": "observer",
  "db_path": "/home/fausto/.hermes/data/hmp/agent_messages.db",
  "server_port": 8643,
  "timezone": "Europe/Rome",
  "skills": [],
  "max_concurrent_tasks": 2,
  "max_timeout": 180,
  "supported_types": ["research", "query", "delegate"],
  "tasks_per_minute": 5,
  "tags": ["descriptor"],
  "agent_card_ttl": 300
}
```

**Platform notes:**
- **Linux:** `db_path` at `/home/<user>/.hermes/data/hmp/agent_messages.db`
- **macOS:** `db_path` at `/Users/<user>/.hermes/data/hmp/agent_messages.db`
- The config file is read by `load_config()` which looks for `~/.hermes/hmp-config.json` by default
- If you put the config in a different path, set `export HMP_CONFIG=/path/to/hmp-config.json` before starting the server

### 3. Create DB directory

```bash
mkdir -p ~/.hermes/data/hmp
```

### 4. Start the server

```bash
nohup python3 ~/hmp.py server 8643 > ~/.hermes/data/hmp/server.log 2>&1 &
```

This starts the HMP server on port 8643 as a background process. Logs go to `server.log`.

### 5. Verify

```bash
# Health check
curl -s http://127.0.0.1:8643/health
# → {"status":"ok","service":"hmp","version":"1.0"}

# Agent card (should show the new peer's name)
curl -s http://127.0.0.1:8643/hmp/agent-card
# → {"agent":"peerNN","role":"worker",...}
```

### 6. Test bidirectional communication

**A. From new peer to coordinator:**

```python
import json, urllib.request, time
msg = {
    "hmp_version": "1.0",
    "message_id": "ping_peerNN_" + str(int(time.time())),
    "idempotency_key": "ping_peerNN_" + str(int(time.time())),
    "from": "peerNN", "to": "peer70",
    "type": "request",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "timeout": 30,
    "payload": {"task_type": "ping", "instruction": "Ping da peerNN via HMP!"}
}
data = json.dumps(msg).encode()
req = urllib.request.Request("http://<coordinator-ip>:8643/hmp/send",
    data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=10)
print(resp.read().decode())
```

**B. From coordinator to new peer:**

```bash
curl -s -X POST http://<new-peer-ip>:8643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"pong_...","idempotency_key":"...","from":"peer70","to":"peerNN","type":"request","timestamp":"...","timeout":30,"payload":{"task_type":"ping","instruction":"Pong da peer70!"}}'
```

### 7. Process messages on the new peer

The new peer's HMP server stores received messages in its SQLite DB, but no cron processes them automatically. To process:

```python
import sqlite3, json, urllib.request, time

conn = sqlite3.connect("/path/to/agent_messages.db")
conn.row_factory = sqlite3.Row

# Find pending messages
rows = conn.execute("SELECT * FROM messages WHERE to_peer='peerNN' AND status='pending' ORDER BY id ASC LIMIT 1").fetchall()

for row in rows:
    msg = dict(row)
    mid = msg['message_id']
    
    # Update state through the lifecycle
    conn.execute("UPDATE messages SET status='delivered', delivered_at=datetime('now') WHERE message_id=?", (mid,))
    conn.commit()
    conn.execute("UPDATE messages SET status='working', updated_at=datetime('now') WHERE message_id=?", (mid,))
    conn.commit()
    
    # Send response via HMP
    response = {
        "hmp_version": "1.0",
        "message_id": "respNN_" + str(int(time.time())),
        "idempotency_key": "respNN_" + str(int(time.time())),
        "in_reply_to": mid,
        "from": "peerNN",
        "to": "peer70",
        "type": "response",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timeout": 30,
        "payload": {"answer": "peerNN risponde via HMP!", "status": "ok"}
    }
    data = json.dumps(response).encode()
    req = urllib.request.Request("http://<coordinator-ip>:8643/hmp/send",
        data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Response sent: {resp.read().decode()}")
    
    # Mark as completed
    conn.execute("UPDATE messages SET status='completed', completed_at=datetime('now') WHERE message_id=?", (mid,))
    conn.commit()

conn.close()
```

### 8. Add to coordinator's PEER_API (optional)

If the coordinator's message-router should forward messages TO this peer, add it to `PEER_API` in `hmp-message-router.py`:

```python
PEER_API = {
    "peerNN": {
        "url": "http://<new-peer-ip>:8642/v1/runs",
        "key": "<peer-api-key>",
        "timeout": 10,
    },
}
```

### 9. Persistence across reboots

On **Linux** (Raspberry Pi, Ubuntu), add to crontab or a systemd service:

```bash
# crontab -e
@reboot sleep 10 && cd ~ && nohup python3 ~/hmp.py server 8643 > ~/.hermes/data/hmp/server.log 2>&1 &
```

On **macOS**, use a LaunchAgent (`launchd`) for reliable persistence. LaunchAgents auto-restart on crash and survive macOS updates:

```xml
<!-- ~/Library/LaunchAgents/com.peerNN.hmpserver.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.peerNN.hmpserver</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/fausto/hmp.py</string>
        <string>server</string>
        <string>8643</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>WorkingDirectory</key><string>/Users/fausto</string>
    <key>StandardOutPath</key><string>/Users/fausto/.hermes/data/hmp/server.log</string>
    <key>StandardErrorPath</key><string>/Users/fausto/.hermes/data/hmp/server.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.peerNN.hmpserver.plist
launchctl list | grep hmpserver
```

To unload: `launchctl unload ~/Library/LaunchAgents/com.peerNN.hmpserver.plist`

### 10. Prevent macOS sleep (optional)

macOS MacBooks enter forced sleep on lid close, even with `caffeinate`. To keep the HMP server reachable:

```bash
# Requires sudo, disables sleep entirely
sudo pmset -a disablesleep 1

# Alternative: caffeinate (no sudo, but does NOT prevent lid-close sleep)
caffeinate -d -i -t 86400 &
```

**`caffeinate` via LaunchAgent (persistent, no sudo):**

```xml
<!-- ~/Library/LaunchAgents/com.peerNN.caffeinate.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.peerNN.caffeinate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-d</string><string>-i</string><string>-t</string><string>86400</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.peerNN.caffeinate.plist
```

## HMPWorker — Agent Loop (per-peer daemon)

The `HMPWorker` is the component that **closes the gap between "message stored on bus" and "message processed by agent"**. Every peer that should respond to HMP requests autonomously runs a Worker daemon alongside its Server.

### The Blind Spot (Before Worker)

```
peer70 ──POST /hmp/send──→ peer106 (pending)
                             ↓
                    peer106's HMP DB stores it
                             ↓
                    status = "pending" — FOREVER
                             ↓
                    peer70 never learns if peer106:
                      - noticed the message?
                      - accepted it?
                      - rejected it?
                      - is working on it?
                      - completed it?
```

**"Delivered" was misleading.** It meant "stored on the peer's bus", not "the peer's agent is processing it".

### The Worker Contract (After Worker)

Every request from peer to peer now guarantees:

1. **ACK** — Worker sends `type: ack, payload: {accepted: true/false}` back to the sender, with optional `eta_s` and `reason`
2. **Working** — Worker updates local message status to `working` with `progress: "started"`, `progress_pct: 0`
3. **Terminal response** — Worker sends `type: response, status: completed|failed|timed_out` back to the sender with result payload
4. **Heartbeat** — Worker updates `progress` and `progress_pct` periodically on the local bus (sender can poll)
5. **Capability validation** — If `payload.type` is not in the peer's `supported_types`, Worker sends `failed` with `error.code: not_implemented`

### Components

```python
class HMPWorker:
    def __init__(self, bus, config, client=None, poll_interval=5):
        self.peer_name = config.get("peer_name", "unknown")
        self.supported_types = set(config.get("supported_types", []))
        self.poll_interval = poll_interval  # seconds between polls
        self.handlers = {}  # payload_type -> callable(msg)

    def register_handler(self, payload_type, fn):
        """Register a handler for a specific payload.type.
           fn(msg) returns (status, payload_dict, error_dict_or_None)."""
```

### Polling Loop

```
while running:
    pending = bus.get_pending(to_peer=self.peer_name, limit=10)
    for each pending message:
        1. Validate payload.type against supported_types
           └─ if unsupported → send FAILED (not_implemented), update local → failed
        2. Send ACK back to sender (type: ack, accepted: true)
        3. Update local status → working (progress: "accepted", pct: 0)
        4. Route to handler or default_handler
        5. Send terminal response: completed or failed
        6. Update local status → completed/failed
    sleep(poll_interval)
```

### ACK Contract

The ACK is a new message sent to the **sender's HMP server** with `in_reply_to` pointing to the original message_id:

```python
def build_ack_msg(in_reply_to, from_peer, to_peer, accepted=True, reason=None):
    return {
        "hmp_version": "1.0",
        "message_id": "msg_<random>",
        "idempotency_key": "msg_<random>",
        "in_reply_to": original_message_id,
        "from": responding_peer,
        "to": original_sender,
        "type": "ack",
        "status": "delivered",
        "timestamp": "...",
        "payload": {"accepted": true, ...},
    }
```

The sender's Coordinator or monitoring code can correlate ACKs via `in_reply_to` on its own bus.

### Default Handlers

The Worker ships with built-in handlers for common payload types:

| `payload.type` | Response |
|----------------|----------|
| `"ping"` or `action: "ping"` | `completed, {type: "pong", echo: ...}` |
| `"health_report"` | `completed, {type: "acknowledged"}` |
| `"code_review"` | `completed, {type: "review_received"}` |
| *(anything else)* | `completed, {type: "acknowledged", original: ...}` |

Custom handlers are registered via `worker.register_handler(type, fn)`.

### State Machine Integration

The Worker required adding `STATE_WORKING` as a valid transition from `STATE_PENDING`:

```python
TRANSITIONS = {
    STATE_PENDING: [STATE_QUEUED, STATE_WORKING, STATE_CANCELLED],
    #                     ^^^^^^^^ added for direct agent claim
    STATE_QUEUED: [STATE_DELIVERED, STATE_CANCELLED],
    STATE_DELIVERED: [STATE_WORKING, STATE_FAILED, STATE_TIMED_OUT, STATE_CANCELLED],
    STATE_WORKING: [STATE_COMPLETED, STATE_FAILED, STATE_NEEDS_INPUT, STATE_TIMED_OUT],
    STATE_NEEDS_INPUT: [STATE_WORKING, STATE_CANCELLED],
}
```

### Running the Worker

```bash
# Foreground (daemon mode)
python3 hmp.py worker

# One-shot poll (for cron or manual testing)
python3 hmp.py once
```

The Worker reads its config from `~/.hermes/hmp-config.json` to determine `peer_name`, `supported_types`, and `max_timeout`.

### Systemd Service

```bash
[Unit]
Description=HMP Worker - processes pending messages
After=hmp-server.service
Requires=hmp-server.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/hmp.py worker
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

### ⚠️ Pitfall: Multiple processing cycles before the fix

Before the Worker, messages stayed in `pending` state forever because `pending → working` was not a valid transition. When the Worker was first deployed without the transition fix, it correctly sent ACK + completed to the sender BUT the local status stayed `pending`, causing the Worker to re-process the same message on every poll cycle. This created duplicate ACK/response pairs on the sender's bus.

**Fix applied:** Added `STATE_WORKING` to the allowed transitions from `STATE_PENDING`. After this fix, each message is processed exactly once — the local status transitions `pending → working → completed`, and `get_pending()` excludes it on subsequent cycles.

## HMPCoordinator — Timeout Enforcement (peer70 only)

The `HMPCoordinator` runs on the coordinator peer (peer70) to detect and remedy stalled messages. It is the **enforcement layer** that ensures messages don't sit in non-terminal states forever.

### Components

```python
class HMPCoordinator:
    def __init__(self, bus, config, poll_interval=15, ack_timeout=15):
        self.max_timeout = config.get("max_timeout", 300)
        self.poll_interval = 15       # seconds between enforcement cycles
        self.ack_timeout = 15         # seconds to wait for ACK before marking stale
```

### Enforcement Rules

| Check | SQL | Action |
|-------|-----|--------|
| **Stale delivery** | Messages TO this peer, status=pending, created_at > 15s ago, no ACK reply exists | → `timed_out` with cause "No ACK within 15s" |
| **Stale worker** | Messages FROM this peer, status=working, updated_at > max_timeout ago | → `timed_out` with cause "No completion within Ns" |
| **Timed out** | Messages FROM this peer, not terminal, created_at > max_timeout ago (excluding stale_workers already caught) | → `timed_out` with cause "Exceeded max_timeout" |

### Running the Coordinator

```bash
python3 hmp.py coordinator
```

The coordinator is non-destructive: it only transitions `pending` and `working` messages to `timed_out`. It never deletes or modifies terminal-state messages.

### Peer Registry — DNS-free Resolution

HMP includes a built-in peer registry for resolving peer names to HTTP URLs without DNS:

```python
# Gateway plugin port (:18643) — for peers running Hermes gateway
GATEWAY_PEER_REGISTRY = {
    "peer70":  "http://192.168.178.70:18643",
    "peer84":  "http://192.168.178.84:18643",
    "peer105": "http://192.168.178.105:18643",
    "peer106": "http://192.168.178.106:18643",
    "peer128": "http://192.168.178.112:18643",
}

# Standalone hmp.py port (:8643) — for peers without Hermes gateway
LEGACY_PEER_REGISTRY = {
    "peer70":  "http://192.168.178.70:8643",
    "peer84":  "http://192.168.178.84:8643",
    "peer105": "http://192.168.178.105:8643",
    "peer106": "http://192.168.178.106:8643",
    "peer128": "http://192.168.178.112:8643",
}

def peer_url(peer_name, registry=None):
    """Resolve a peer name to its HMP URL.
       Falls back to http://192.168.178.{suffix}:8643 for peerNN convention."""
```

The Worker uses `peer_url()` to determine where to send ACK and response messages. Configurable via `HMP_PEER_REGISTRY` env var or by passing a custom registry dict.

## CLI — Updated Entry Point

Previous versions accepted only `hmp.py <port>`. The new CLI uses subcommands:

```bash
# Usage
hmp.py <command> [args]

# Commands:
server [port]        — Run HMP HTTP server
worker               — Run HMP Worker agent (poll + ACK + process)
coordinator          — Run HMP Timeout Enforcer (peer70 only)
once                 — Poll and process pending messages once (one-shot)

# Examples
hmp.py server                # default :8643
hmp.py server 8643           # explicit port
hmp.py worker                # daemon mode (runs forever)
hmp.py once                  # single poll cycle
hmp.py coordinator           # timeout enforcement (peer70 only)
```

Each subcommand loads its config from `~/.hermes/hmp-config.json` using `load_config()`.

## Full Lifecycle (with Worker + Coordinator)

```
peer70 ──POST /hmp/send──→ peer106:8643
                             │  peer106 HMP server stores message
                             │  status = pending
                             ▼
                    peer106 HMPWorker (poll every 5s)
                             │
                    1. Validate payload type
                    2. Send ACK ───────POST /hmp/send──→ peer70:8643
                    3. Update local → working
                    4. Process task (handler)
                    5. Send COMPLETED ──POST /hmp/send──→ peer70:8643
                    6. Update local → completed
                             │
                             ▼
                    peer70 HMPCoordinator (poll every 15s)
                      ├─ Check: ACK received within 15s?     → OK or timed_out
                      ├─ Check: completed within max_timeout? → OK or timed_out
                      └─ No action needed (clean)
```

Compare to the old lifecycle where peer70 had no visibility into what happened on peer106 after the message was stored.

### Verification Checklist

Before declaring a peer HMP-operational with Worker:

- [ ] HMP server running (`/health` returns 200)
- [ ] HMPWorker running (check `ps aux | grep 'hmp.py worker'`)
- [ ] Coordinator running on peer70 (check `ps aux | grep 'hmp.py coordinator'`)
- [ ] Worker config has correct `peer_name` and `supported_types`
- [ ] Send a `ping` message from coordinator → peer
- [ ] Verify ACK received on coordinator's bus (`from=peerXX, type=ack`)
- [ ] Verify COMPLETED received on coordinator's bus (`type=response, status=completed`)
- [ ] Verify local status on the peer (`message_id` in terminal state)
- [ ] Verify no duplicate processing (exactly 1 ACK + 1 response per message)

## Message Router (Coordinator Cron Pattern)

The coordinator runs a cron job (`hmp-message-router.py`) that advances message states and forwards messages to remote peers. This is the bridge between HMP's local SQLite bus and the wider peer network.

### Architecture

The message router runs on the **coordinator** (peer70) every 30s. It operates in two steps:

1. **pending → queued** — takes ownership of ALL new messages regardless of target
2. **queued → delivered or forwarded** — routes each message based on `to_peer`:

```
┌─ to_peer = coordinator ──→ delivered (local DB, callback)
└─ to_peer = remote peer ──→ POST /v1/runs via Hermes API → delivered
```

### Peer Registry

The router maintains a `PEER_API` dict mapping peer names to their Hermes API endpoint and key:

```python
PEER_API = {
    "peer84": {
        "url": "http://192.168.178.84:8642/v1/runs",
        "key": "<api-key>",
    },
    "peer128": {
        "url": "http://Faustos-MacBook-Pro-Home-3.fritz.box:8642/v1/runs",
        "key": "<api-key>",
    },
}
```

### Forwarding to Remote Peers

When a message targets a remote peer, the router:

1. Builds a prompt from the HMP payload's `instruction` field
2. Appends instructions for the peer to respond via HMP (POST to coordinator's `/hmp/send`)
3. POSTs to `http://<peer>:8642/v1/runs` with the prompt
4. On HTTP 200 → marks message `delivered` with `run_id` in stats
5. On HTTP error → marks message `failed` with error details
6. Unknown peers → marks message `failed` with "no route" error

The `/v1/runs` endpoint is used (not `/v1/chat/completions`) because:
- Returns a `run_id` for tracking
- Supports async execution (status can be polled later)
- Can accept `session_id` for continuity

### Response Flow

The remote peer's agent processes the `/v1/runs` task and eventually sends its response back to the coordinator via:

```python
from hmp import HMPClient, new_message_id, now_iso

client = HMPClient("http://192.168.178.70:8643")
client.send_message({
    "hmp_version": "1.0",
    "message_id": new_message_id(),
    "idempotency_key": new_message_id(),
    "in_reply_to": "<original-message-id>",
    "from": "peer84",
    "to": "peer70",
    "type": "response",
    "timestamp": now_iso(),
    "payload": {"result": "...", "status": "completed"},
})
```

The response message enters the coordinator's HMP bus as `pending`, and the next cycle of the message-router delivers it locally.

### Complete Message Lifecycle

```
peer70 → POST /hmp/send → DB (pending)
  ↓
message-router (30s cron)
  ├─ pending → queued
  └─ queued → POST /v1/runs → peer84 (delivered)
  ↓
peer84 processes task, responds:
  POST /hmp/send → peer70:8643 → DB (pending)
  ↓
message-router (30s cron)
  └─ pending → queued → delivered (local)
  ↓
peer70 polls /hmp/poll/<id> → response ready
```

### Cron Installation

The message-router script lives on the **coordinator** (`~/.hermes/scripts/hmp-message-router.py`). The cron job that triggers it can run on any peer that has SSH access to the coordinator:

```bash
# On peer84 (or any peer with SSH to coordinator):
* * * * * sleep 0 && ssh -o StrictHostKeyChecking=no \
  fausto@192.168.178.70 "cd /home/fausto/.hermes && python3 scripts/hmp-message-router.py" >/dev/null 2>&1
* * * * * sleep 30 && ssh -o StrictHostKeyChecking=no \
  fausto@192.168.178.70 "cd /home/fausto/.hermes && python3 scripts/hmp-message-router.py" >/dev/null 2>&1
```

This runs every 30s (two cron entries offset by 30s). The script is idempotent — it processes whatever messages are available.

### Companion Scripts

| Script | Schedule | Purpose |
|--------|----------|---------|
| `hmp-message-router.py` | Every 30s | Advances message states, forwards to remote peers |
| `hmp-watchdog.py` | Every 2 min | Detects and marks stalled messages (working > 5min) |
| `hmp-dream-engine.py` | Daily 00:00 | Maintenance: archive old messages, VACUUM, compact |

### Pitfalls

- **Peer must have `/v1/runs` endpoint** — the router uses Hermes API, not HMP. If a peer doesn't have Hermes API running, messages to it will fail.
- **Response delivery is best-effort** — the forwarded task instructs the peer to respond via HMP, but there's no hard guarantee. The watchdog can detect stalled messages.
- **API key exposure** — PEER_API dict contains plaintext keys. Keep `hmp-message-router.py` permissions restricted (`chmod 600`).
- **Cron on remote peer** — the cron job that triggers the router can run on any machine, but the script itself runs on the coordinator. SSH keys must be set up.
- **Router is not recursive** — messages forwarded to a remote peer won't be re-routed by that peer's router (if it has one). The router only handles messages on the coordinator's bus.
- **Per-peer timeout tuning** — Different peers respond at different speeds. Configurable per peer:
  ```python
  PEER_API = {
      "peer84":   {"url": "...", "key": "...", "timeout": 10},   # 10s for fast LAN peers
      "peer128":  {"url": "...", "key": "...", "timeout": 5},    # 5s for slow Mac peers
  }
  ```
  A timeout causes `URLError` which the router catches and marks the message `failed`. It remains in `queued` state and is retried on the next cron cycle.
- **Slow Mac peers** — macOS peers on WiFi can take 30-90s for chat completions but often fail to respond within `timeout` seconds on `/v1/runs`. The router marks these as `failed` on timeout; the `queued` state survives retry cycles. If a Mac doesn't respond after several cycles, the message stays in the queue until manually resolved or replaced by a fresh one.
- **Wake from sleep pattern** — Macs in sleep (lid closed) can often be woken by an SSH connection attempt. After waking, the Hermes gateway needs to restart:
  ```bash
  ssh -o ConnectTimeout=5 fausto@<mac-ip> "echo wake" 2>/dev/null
  sleep 3
  curl -s --connect-timeout 5 http://<mac-ip>:8642/health
  ```
  The SSH key must be installed on the Mac. If the gateway doesn't restart automatically, pipe a restart command through SSH.

## Worker-Router (Peer Cron Pattern)

Worker peers (peer84, peer128) need their own cron-based message processor to automatically handle incoming HMP messages. The worker-router runs every 30s and provides **autonomous ping/pong** — the peer responds without external SSH or API intervention.

### Architecture

```python
# Runs on each worker peer every 30s via crontab
# 1. SELECT pending WHERE to_peer = self
# 2. pending -> delivered -> working
# 3. Process message (ping -> pong, query -> answer)
# 4. POST /hmp/send -> coordinator with response
# 5. working -> completed
```

### Installation

The worker-router script lives at the coordinator and must be **copied to each worker peer**:

```bash
# Copy to peer84 (Linux)
scp fausto@192.168.178.70:/home/fausto/.hermes/skills/autonomous-ai-agents/multi-agent-mesh/scripts/hmp-worker-router.py /root/.hermes/scripts/

# Copy to peer128 (macOS)
scp fausto@192.168.178.70:/home/fausto/.hermes/skills/autonomous-ai-agents/multi-agent-mesh/scripts/hmp-worker-router.py /Users/fausto/.hermes/scripts/
```

### Cron Registration

```bash
# Two entries offset by 30s for ~15s max latency
* * * * * sleep 0 && python3 /path/to/hmp-worker-router.py >/dev/null 2>&1
* * * * * sleep 30 && python3 /path/to/hmp-worker-router.py >/dev/null 2>&1
```

The script auto-detects the peer name and DB path based on the filesystem:
- `/root/.hermes/data/hmp/agent_messages.db` → peer84
- `/Users/fausto/.hermes/data/hmp/agent_messages.db` → peer128
- `~/.hermes/data/hmp/agent_messages.db` → auto-detect

Override via environment variables:
```bash
HMP_PEER_NAME=peer128 HMP_DB_PATH=/custom/path python3 hmp-worker-router.py
```

### Message Processing

The worker-router handles three task types:

| `task_type` | Response |
|-------------|----------|
| `ping` | `{"answer": "Pong da peerNN!", "status": "online", "hostname": "..."}` |
| `query` | `{"answer": "peerNN: ricevuto e processato", "status": "ok"}` |
| `general` (default) | `{"answer": "...", "status": "ok"}` |

### Failure Handling

- **HMP send fails** → message marked `failed`, retried on next cron cycle
- **DB not found** → silent exit (prevents spam when script runs on wrong platform)
- **State transitions** → all guarded by SQLite WAL with auto-commit per transition

### Testing

After installation, verify from the coordinator:

```bash
# Send a ping
curl -s -X POST http://127.0.0.1:8643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"test_$(date +%s)","idempotency_key":"test_$(date +%s)","from":"peer70","to":"peer84","type":"request","timestamp":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","timeout":30,"payload":{"task_type":"ping","instruction":"Test automatico"}}'

# Wait 35s for cron cycle, then check for response
curl -s http://127.0.0.1:8643/hmp/poll/resp_peer84_*
```

Expected result: a response message with `status: delivered` and a payload containing `"answer": "Pong da peer84!"`.

## Prioritisation

HMP is the **primary protocol** for inter-peer communication on this network. Use HMP before API Hermes or SSH. Rationale:

| Criterion | HMP (:8643) | API Hermes (:8642) | SSH |
|-----------|-------------|-------------------|-----|
| Token cost | Zero (no LLM context) | High (~60-100K/turn) | Zero |
| Latency | ~2-5s (state machine) | ~10-90s (LLM inference) | ~1-3s |
| Structured | State machine, idempotency | Free-form chat | Raw shell |
| Persistence | SQLite, survives restart | None (session-based) | None |
| Automation | Cron-friendly | Agent-only | Fragile |

HMP for: pings, healthchecks, task dispatch, structured queries.
API Hermes for: complex reasoning, file operations, multi-step tasks that need a full agent.
SSH for: one-off maintenance, waking sleeping Macs.

## Complete Lifecycle (Peer70 → Peer84 → Peer70)

```
peer70 ──HMP──► /hmp/send ──► DB (pending)
                     │
          message-router (30s cron on peer70)
                     │
          to_peer=peer84 ──► POST /v1/runs (Hermes API)
                     │
          peer84 riceve task
                     │
          worker-router (30s cron on peer84)
                     │
          pending→delivered→working→completed
                     │
          POST /hmp/send──► peer70:8643 (response)
                     │
          message-router (30s cron on peer70)
                     │
          to_peer=peer70 ──► delivered (locale)
```

## Pitfalls

### Don't claim completeness until verified end-to-end

The most common mistake is declaring HMP "bidirectional" or "working" after only testing one direction. A full cycle requires ALL four components verified:

1. ✅ Message sent (HMP POST accepted with `duplicate: false`)
2. ✅ Message routed (router transitions pending→queued→delivered)
3. ✅ Message processed (worker responds via HMP)
4. ✅ Response delivered (originator receives and marks delivered)

**Test checklist before declaring a new peer operational:**
- [ ] HMP server running (`/health` returns 200)
- [ ] Agent card shows correct peer name
- [ ] Coordinator can send message → peer receives (check peer's DB)
- [ ] Worker-router cron installed (30s interval)
- [ ] Peer auto-responds to ping (check coordinator's DB for response)
- [ ] Coordinator's message-router delivers the response

### utcnow() deprecation

Python 3.12+ emits deprecation warnings for `datetime.utcnow()`. Use `datetime.now(datetime.timezone.utc)` everywhere:

```python
# ✅ Correct
def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

### Thread safety

HMPBus uses `threading.Lock` only on write operations (`send_message`, `update_status`, maintenance). Reads (`get_pending`, `get_message`) are lock-free — acceptable for SQLite with WAL mode because reads never block reads. If writes become contended, consider wrapping all public bus methods with the lock.

### Message routing: direct SELECT per state

When transitioning messages between states, use direct SELECT queries with explicit state literals rather than compound WHERE clauses that depend on prior query results:

```python
# ✅ Correct — SELECT by state directly
pending = bus.get_pending(to_peer=peer_id)       # WHERE status IN (pending, queued)
queued_for_delivery = bus._conn.execute(          # separate query
    "SELECT * FROM messages WHERE status = ? AND to_peer = ?",
    (STATE_QUEUED, peer_id)
)

# ❌ Wrong — combining states in a single query can skip transitions
rows = bus._conn.execute(
    "SELECT * FROM messages WHERE status IN (?, ?)",
    (STATE_PENDING, STATE_QUEUED)
)
for row in rows:
    # mixing pending and queued in one loop can race
```

### Timer resolution for stall detection

`get_stalled` compares against `max_age_seconds` but `updated_at` is set to `now_iso()` (second resolution). With `max_age_seconds=300`, a message could be up to `300 + <1s` old before detection. This is acceptable — sub-second precision isn't needed for stall detection.

### macOS firewall blocks remote HMP

On macOS, the HMP server listens on `*:8643` and responds to localhost (`127.0.0.1`) but is **not reachable from other LAN hosts** — even though `lsof` shows `TCP *:8643 (LISTEN)`. This is the macOS application firewall silently blocking incoming connections.

**Symptoms:** `curl http://<mac-ip>:8643/health` times out; `curl http://127.0.0.1:8643/health` works from the Mac itself.

**Solutions (in order of preference):**
1. **Add firewall exception** — System Settings → Network → Firewall → Options → Add `python3` (or the specific Python launcher) and allow incoming connections
2. **SSH tunnel** — route HMP traffic through SSH: `ssh -L 8643:localhost:8643 fausto@<mac-ip>`
3. **SSH fallback** — if HMP direct fails, the coordinator can check peer health via SSH: `ssh fausto@<mac-ip> "curl -s http://127.0.0.1:8643/health"`
4. **Accept degraded mode** — peer128 can send to the coordinator, but the coordinator can't reach peer128's HMP. Use the API Hermes (`:8642`) or SSH for the return path.

The `hmp-healthcheck.py` script (see scripts/) implements the SSH fallback automatically — it tries HMP direct first, then falls back to SSH health check.

### No authentication

Current version (v0.2) has no auth layer. Any process on the LAN can send/update/cancel messages. Documented as TODO in the SPEC. If security is needed, add HMAC signing or wire the HMP server behind the Hermes API gateway.

### No rate limiting

Also not yet implemented. A misconfigured peer could flood the bus with messages. Consider adding a simple token-bucket per source peer or a global rate limit on `/hmp/send`.