# HMP v2 Protocol (port 8643)

HMP v2 is a self-contained, zero-dependency protocol for peer-to-peer messaging
between Hermes agents. It replaces the older HMP gateway plugin (port 18643) with
a simpler SQLite-backed bus that any peer can run with only Python stdlib.

**Key difference from HMP v1 (plugin on 18643):** v2 has NO Hermes plugin dependency.
It's a standalone Python service using `http.server`, `sqlite3`, and `urllib` only.
The `hmp.py` library (~686 lines) is the full implementation.

## Architecture

```
peer70 (coordinator)
├── HMP server :8643         (receives + stores messages)
├── message-router (cron 30s) (pending→queued→delivered, local + forward)
├── worker-router (cron 30s)  (delivered→completed with auto-response)
└── agent_messages.db         (SQLite WAL, single source of truth)

peer84 / peer128 (workers)
├── HMP server :8643         (receives + stores messages)
└── worker-router (cron 30s)  (pending→delivered→completed with auto-response)
```

## Components

### hmp.py (~/.hermes/skills/.../hmp-protocol/scripts/hmp.py)

Single file, zero pip dependencies. Contains:
- `HMPBus` — SQLite interface with WAL mode, idempotency, state machine
- `HMPServer` — threaded HTTP server on :8643
- `HMPClient` — for non-coordinator peers to send/poll
- CLI: `python3 hmp.py [port]` starts the server

### Message States

```
pending → queued → delivered → working → completed
                                    ↘ failed
```

### message-router.py (peer70 only)

Runs every 30s via cron. Two branches:
- Messages `to_peer=peer70` → local delivery (pending→queued→delivered)
- Messages `to_peer=other` → forward via API Hermes (`/v1/runs` on target's :8642)

File: `~/.hermes/scripts/hmp-message-router.py`

### worker-router.py (all peers)

Runs every 30s via cron. Finds messages in `delivered` or `working` state
for its own peer, processes the payload, sends response via HMP.

File: `~/.hermes/scripts/hmp-worker-router.py`

## Setup on a New Peer

```bash
# 1. Copy hmp.py
scp fausto@192.168.178.70:/home/fausto/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts/hmp.py ~/hmp.py

# 2. Create config
cat > ~/.hermes/hmp-config.json << EOF
{
  "peer_name": "peerNNN",
  "peer_role": "worker",
  "cluster_role": "observer",
  "db_path": "/path/to/agent_messages.db",
  "server_port": 8643
}
EOF

# 3. Start server
nohup python3 ~/hmp.py 8643 > ~/.hermes/data/hmp/server.log 2>&1 &

# 4. Install worker-router cron
(crontab -l; echo '* * * * * sleep 0 && python3 ~/.hermes/scripts/hmp-worker-router.py >/dev/null 2>&1'; echo '* * * * * sleep 30 && python3 ~/.hermes/scripts/hmp-worker-router.py >/dev/null 2>&1') | crontab -
```

## Healthcheck

The `hmp-healthcheck.py` script sends ping messages to all peers every hour
via cronjob. Results saved to `~/.hermes/peer-network/hmp-health.log`.

## Protocol

Messages are JSON with standard fields:
```json
{
  "hmp_version": "1.0",
  "message_id": "msg_uuid",
  "idempotency_key": "same_as_message_id",
  "from": "peer70",
  "to": "peer84",
  "type": "request",
  "timestamp": "2026-07-14T20:00:00Z",
  "timeout": 30,
  "payload": {"task_type": "ping", "instruction": "..."}
}
```

Responses use `"type": "response"` with `in_reply_to` pointing to the original
message_id. Task types: `ping`, `query`, `delegate`.
