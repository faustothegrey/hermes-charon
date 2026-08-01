# Peer Message Queue — Implementation Reference

## Files

| File | Path | Role |
|------|------|------|
| `peer_queue.py` | `~/.hermes/scripts/peer_queue.py` | Core engine: queue management, health check, HMP send, CLI commands |
| `peer-msg` | `~/.hermes/scripts/peer-msg` → `/usr/local/bin/peer-msg` | Bash wrapper CLI (symlinked to PATH) |
| `peer_queue.json` | `~/.hermes/peer_queue.json` | Persistent queue data (auto-created) |
| Cron job | job_id `3051b1b94cc6` | Delivery every 2 min, no_agent=True |

## Queue JSON schema

```json
[
  {
    "id": "msg_3ca8e1f2",
    "to": "peer84",
    "text": "Ciao peer84! Messaggio in attesa.",
    "priority": 30,
    "from": "peer70",
    "status": "pending",       // pending | delivered | failed
    "attempts": 1,
    "max_attempts": 10,
    "created_at": 1784385012.0,
    "delivered_at": null,
    "last_attempt": 1784385030.0,
    "last_error": "offline"
  }
]
```

## Key implementation details

### Health check

```python
def peer_health(peer_name):
    ip = PEER_IP.get(peer_name)
    req = urllib.request.Request(f"http://{ip}:18643/health")
    with urllib.request.urlopen(req, timeout=4) as r:
        data = json.loads(r.read())
        return data.get("status") == "ok"
```

Returns `True` only if HTTP 200 + `{"status":"ok"}`. Any exception (timeout, connection refused, DNS failure) → `False`.

### HMP send

```python
def hmp_send(peer_name, text, from_name="peer70"):
    msgid = f"peerq_{uuid.uuid4().hex[:12]}"
    payload = json.dumps({
        "hmp_version": "1.0",
        "message_id": msgid,
        "from": from_name,
        "to": peer_name,
        "type": "request",
        "timeout": 60,
        "payload": {"text": text}
    }).encode()
    req = urllib.request.Request(
        f"http://{ip}:{HMP_PORT}/hmp/send",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    return result.get("accepted", False)
```

Uses non-blocking `/hmp/send` (not `/hmp/send_and_wait`). No polling for response — fire-and-forget delivery.

### Lock mechanism

File-based lock (`O_CREAT | O_EXCL`) on `~/.hermes/peer_queue.json.lock` to prevent concurrent access from cron job and manual CLI usage. Max 15 retries (1.5s total) before `TimeoutError`.

### NetBoard notification on delivery

```python
if delivered_count > 0:
    peers_delivered = [m["to"] for m in pending if m["status"] == "delivered"]
    if peers_delivered:
        peer_list = ", ".join(sorted(set(peers_delivered)))
        subprocess.run(
            ["netboard-msg", f"📨 Messaggio recapitato a {peer_list}",
             "--priority", "60", "--duration", "10",
             "--sub", "Peer-queue delivery"],
            timeout=5, capture_output=True
        )
```

### Peer registry

```python
PEER_IP = {
    "peer70":  "192.168.178.70",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer128": "192.168.178.112",
    "peer58":  "192.168.178.58",
    "peer136": "192.168.178.136",
}
```

**Note:** peer128 IP is `.112`, not `.128`.

## Testing

```bash
# Invia a peer online (consegna immediata)
peer-msg send peer128 "Test messaggio diretto"
peer-msg deliver --no-cooldown

# Invia a peer offline (rimane in coda)
peer-msg send peer84 "Messaggio per quando torni" --priority 30
peer-msg list

# Verifica stato
peer-msg status
```

## Delivered message lifecycle

1. Message sent → status `delivered`, `delivered_at` = now
2. Remains visible in `peer-msg list` for 24h
3. After 24h, `peer-msg clean` removes it (or cron auto-clean)
4. Failed after 10 attempts → status `failed`, kept for inspection
