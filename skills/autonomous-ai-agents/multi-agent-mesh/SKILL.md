---
name: multi-agent-mesh
description: "Manage a mesh network of Hermes agents that communicate via API — multi-machine orchestration, peer discovery, and health monitoring."
version: 1.3.0
author: Hermes Agent (learned from session)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [multi-agent, mesh, orchestration, peer-network, api-communication]
    homepage: https://hermes-agent.nousresearch.com/docs
---

# Multi-Agent Mesh

Manage a network of independent Hermes agents (on different machines) that communicate **exclusively via HTTP API** — no SSH for inter-agent communication.

Each peer exposes the Hermes API server (`:8642`). One agent acts as **orchestrator**, monitoring peer health and routing coordination. This is distinct from `delegate_task` (subprocess spawning within one agent) — this skill covers independent physical/virtual machines running their own Hermes instances.

## When to Use

- You have 2+ machines each running Hermes Agent
- You want one to act as orchestrator (health pings, task routing)
- You need a machine that runs 24/7 (e.g. Raspberry Pi) to monitor others that may sleep/overheat
- You want API-only communication between agents (cleaner than SSH, standardized protocol)

## Setup

### 1. Enable API Server on Each Peer

Add to each machine's `~/.hermes/config.yaml`:

```yaml
gateway:
  enabled: true
  platforms:
    api_server:
      enabled: true
      extra:               # ← NOTE: must be under 'extra:', not at top level
        host: 0.0.0.0
        port: 8642
```

### 2. Set API Keys

Generate a strong key per peer:

```bash
openssl rand -hex 32
```

Add to each machine's `~/.hermes/.env`:

```
API_SERVER_KEY=<64-char-hex>
```

The API server **will refuse to start** without a key (minimum 16 chars for public binds).

### Persistence across reboots (HMP Gateway Plugin)

The HMP gateway runs as a plugin inside the Hermes gateway process, not as a standalone service.
Persist it by installing the Hermes gateway itself as a **systemd --user service**.

On **Linux (RPi, Ubuntu, Fedora)** — install the Hermes gateway as systemd --user:

```bash
# Install gateway as a user service (auto-restart on crash + boot)
hermes gateway install
```

Verify with:

```bash
systemctl --user status hermes-gateway
systemctl --user enable hermes-gateway   # start at boot
systemctl --user start hermes-gateway    # start now
systemctl --user restart hermes-gateway   # restart (use this, not kill/nohup)
```

**Key commands:**

| Action | Command |
|--------|---------|
| Start | `systemctl --user start hermes-gateway` |
| Stop | `systemctl --user stop hermes-gateway` |
| Restart | `systemctl --user restart hermes-gateway` |
| Status | `systemctl --user status hermes-gateway` |
| Enable at boot | `systemctl --user enable hermes-gateway` |
| View logs | `journalctl --user -u hermes-gateway -n 50 --no-pager` |

**⚠️ Canonical method:** Always use `systemctl --user restart hermes-gateway` to restart the gateway on a peer. Do NOT use `kill`/`pkill` followed by `nohup`/`setsid` — systemd manages the process lifecycle and will restart it automatically. `kill -9` on a systemd-managed process is compounded by systemd re-spawning it, leading to duplicate instances.

**On macOS** — use a LaunchAgent for launchd persistence:

```bash
hermes gateway install
```

This creates and loads the appropriate LaunchAgent.

**Legacy note:** The old standalone `hmp.py` (port 8643) is **no longer in use** on any peer in this fleet. All peers use the HMP gateway plugin on port 18643.

Name peers by their **IP suffix** — not by descriptive names:

| Right | Wrong |
|-------|-------|
| `peer84` | `peer-host`, `peer-n56vv` |
| `peer128` | `peer-mac`, `peer-orchestrator-old` |

This stays stable across hostname changes and is unambiguous on the subnet.

## Communication Protocol

**API only, never SSH.** Use the OpenAI-compatible chat completions endpoint:

```bash
curl -X POST http://<peer>:8642/v1/chat/completions \
  -H "Authorization: Bearer <peer-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "hermes-agent", "messages": [{"role": "user", "content": "..."}]}'
```

### Storage of Peer API Keys

Keep a JSON file per mesh:

```json
{
  "peers": {
    "peer70": { "host": "192.168.178.70", "port": 8642, "api_key": "..." },
    "peer84": { "host": "192.168.178.84", "port": 8642, "api_key": "..." }
  }
}
```

Place at `~/.hermes/peer-network/peer-api-keys.json`.

## Querying Peer Status (Beyond Health)

Beyond simple `/health` pings, peers can respond to **task-specific queries** via the chat completions endpoint. This is useful for periodic status polling — e.g. checking backup job results on another machine without SSH.

### Constrained Peers: Sequential Querying Pattern

Not all peers respond quickly to LLM queries. Constrained machines (thermal-throttled laptops, low-RAM ARM devices, WiFi-connected peers) may **time out on complex multi-part prompts** while responding instantly to short, focused ones.

**Observed behavior on N56VV (peer84, Ubuntu laptop, thermal cooling):**
- Complex prompt with multiple questions (3+ sentences or multi-part) → timeout at 60-120s
- Simple yes/no or single-line question → responds in 10-30s
- `max_tokens=10` response only → fastest (2-10s)

**Pattern: instead of asking everything at once, probe sequentially:**

```python
# ❌ WRONG — one big question (will likely timeout on constrained peers)
ask("I need your full email config: tool used, config path, file contents, passwords.")

# ✅ RIGHT — break into short sequential questions
ask("Che tool email usi?")        # → "Himalaya"
ask("Percorso del config?")       # → "~/.config/himalaya/config.toml"
ask("Leggi il config e mandamelo.")  # → full file content
ask("Leggi anche il file password.") # → password
```

**Guidelines for sequential probing:**
1. **Start with health check** (`GET /health`) — instant, no auth needed, confirms the peer is alive
2. **First chat message: single question, `max_tokens=50-100`** — if this works, the peer is ready
3. **Escalate complexity gradually** — add context and increase `max_tokens` only after basic communication is confirmed
4. **Timeout fallback**: if a longer query times out, retry as 2-3 sequential short queries
5. **Cache intermediate answers** — once you have a config path or tool name from a short query, reuse it rather than re-asking
6. **Keep `timeout` at 60s+ for all chat queries** even short ones, because token generation on slow peers is unpredictable

### Pattern: Cron-Driven Status Polling

```python
# backup_monitor.py — runs every 30 min via Hermes cronjob
# Collects backup status from each peer via chat completions API

def query_peer_backup(name, host, port, api_key, job_id):
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{
            "role": "user",
            "content": (
                f"Stato del cron job backup {job_id}. "
                "Voglio solo: esito (success/error/running/never-ran), "
                "orario ultimo run, run totali. "
                "Rispondi SOLO con JSON valido, niente altro."
            )
        }],
        "max_tokens": 150,
    }).encode()

    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]

    # Extract JSON from possible markdown code fence
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return json.loads(content)
```

Key constraints:
- **Model is always `hermes-agent`** — it routes to whatever model the peer has configured
- **Timeout is long** (120s) — macOS peers on WiFi can be very slow to generate responses
- **Prompt must ask for structured output** (JSON only, no explanation) — otherwise the response includes markdown prose that's hard to parse
- **Response may be wrapped in ```json```** — strip the fence before parsing
- **Token cost** — each query costs ~60-100K input tokens (the peer loads its full context). Space queries 30+ min apart to keep costs reasonable
- **Offline peers** — catch `urllib.error.URLError` and record as unreachable rather than failing the entire batch

### Result Persistence

Results from multiple peers are aggregated into a shared JSON file under `~/.hermes/peer-network/`:

```json
{
  "updated_at": 1234567890,
  "backups": [
    {
      "peer": "peer128",
      "label": "peer128 (Mac)",
      "reachable": true,
      "esito": "success",
      "ultimo_run": "2026-07-09T23:00:00+02:00",
      "run_totali": 15
    }
  ]
}
```

Shared JSON files under `~/.hermes/peer-network/` are the preferred data bus between background cron jobs and frontend dashboards (NetBoard, web UIs). The pattern:
1. Cron job writes JSON → `backup_status.json`, `status.json`
2. Python data modules read JSON → `backup_data.py`, `peer_data.py`
3. Dashboards query data modules → framebuffer, web server, CLI

## Orchestrator Handover (Coordinator Transition)

When the current orchestrator must step down (overheating, maintenance, role reassignment):

### Preconditions
- The replacement node must have Hermes API server running (`:8642`) and be confirmed reachable via `/health`
- All peers must be running Hermes API (no SSH-only nodes) — otherwise the beacon system is still needed

### Transition Checklist

1. **Verify replacement readiness**: Check the replacement's `/health` endpoint. Confirm API server is stable, gateway is active.

2. **Copy peer configuration** to replacement:
   - `peer-mesh.yaml` — peer topology with roles, capabilities, URLs
   - `~/.hermes/peer-network/peer-api-keys.json` — API keys for all peers
   - `peers_config.json` (in `~/.hermes/scripts/`) — compact key/host mapping for cron scripts

3. **Set up peer-mesh.yaml on replacement** with all peers:
   ```yaml
   peers:
     peer70:
       url: http://192.168.178.70:8642
       api_key_env: HERMES_PEER_70_KEY
       role: coordinator
       capabilities: [hermes, lan, coordinator]
     n56vv:
       url: http://192.168.178.84:8642
       api_key_env: HERMES_PEER_N56VV_KEY
       role: worker
       capabilities: [hermes, lan, heavy]
     peer105:
       url: http://192.168.178.105:8642
       api_key_env: HERMES_PEER_105_KEY
       role: worker
       capabilities: [hermes, youtube, transcript]
     peer106:
       url: http://192.168.178.106:8642
       api_key_env: HERMES_PEER_106_KEY
       role: worker
       capabilities: [hermes, research, web]
     peer128:
       url: http://192.168.178.112:8642
       api_key_env: HERMES_PEER_128_KEY
       role: worker
       capabilities: [hermes, macos]
   ```

4. **Create health-check scripts** on the replacement for each peer (see "Heartbeat Pattern: no_agent=True" below)

5. **Register cron jobs** on the replacement's scheduler for:
   - Heartbeat/health checks for each peer (hourly, no_agent)
   - Keepalive pings for peers that need App Nap prevention (every 2min, no_agent)
   - Research Queue advancement (agent-driven, delegates to worker peers)
   - Quest advancement (agent-driven, every 4h)
   - Weekly peer exchange (agent-driven, Friday)
   - Full network health monitor (hourly, all peers)

6. **On the old orchestrator**, remove peer-infrastructure cron jobs (heartbeats, autonomous loops), keeping only local machine-specific jobs (thermal/cooling, local backups).

7. **Retire beacon system** if one was running — see "Faro Beacon → /health Migration" section below.

8. **Inform peers** via API that the orchestrator has changed.

## Heartbeat Pattern: no_agent=True

For simple health checks that don't need LLM reasoning, use `no_agent=True` cron jobs. These run a Python script directly — zero LLM token cost, silent when healthy, only output on state transitions.

### Script Structure

```python
#!/usr/bin/env python3
"""peer105-heartbeat.py — Health check for peer105 (YouTube transcript specialist).
Runs hourly via cron. Silent unless transition detected.
"""
import json, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

PEER_URL = "http://192.168.178.105:8642/health"
STATUS_FILE = Path.home() / ".hermes/peer-network/peer105-status.json"
STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

def check():
    try:
        req = urllib.request.Request(PEER_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=8)
        body = json.loads(resp.read().decode())
        return "ONLINE", body.get("version", body.get("platform", "?"))
    except Exception:
        return "OFFLINE", "unreachable"

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status, version = check()
    
    prev = {"status": "UNKNOWN"}
    if STATUS_FILE.exists():
        try: prev = json.loads(STATUS_FILE.read_text())
        except: pass

    data = {"timestamp": now, "peer": "peer105", "status": status, "version": version}
    STATUS_FILE.write_text(json.dumps(data, indent=2) + "\n")

    # Only produce output on transition (so cron stays silent when healthy)
    if prev.get("status") != status:
        print(f"[peer105] TRANSITION: {prev.get('status', '?')} -> {status}")

main()
```

### Cron Registration

```bash
hermes cron create \
  --name "peer105 heartbeat" \
  --schedule "every 1h" \
  --script "peer105-heartbeat.py" \
  --no-agent \
  --deliver local
```

Key design decisions:
- **One script per peer** — keeps isolation, each script is ~40 lines, easy to debug
- **/health endpoint** — uses the unauthenticated Hermes health endpoint (no API key needed)
- **State file per peer** — `~/.hermes/peer-network/<name>-status.json` — tracks previous state
- **Silent output** — script only prints when status changes. With `no_agent=True`, cron delivers stdout verbatim only on non-empty. This means no notifications during healthy operation.
- **Local delivery** — `deliver=local` so output goes to the local session, not the user's chat
- **5-8 second timeout** — short timeout since /health is instant on responsive peers

### Keepalive Pattern (macOS App Nap Prevention)

macOS App Nap can suspend Hermes after 30-60s of inactivity. Prevent with frequent /health pings:

```bash
hermes cron create \
  --name "peer128 keepalive" \
  --schedule "every 2m" \
  --script "peer128-keepalive.py" \
  --no-agent \
  --deliver local
```

The script is identical to heartbeat but runs more frequently and only notifies on RECONNECT (OFFLINE→ONLINE transition):

```python
# Only notify when peer comes back online after being offline
if status == "ONLINE" and prev.get("status") != "ONLINE":
    print(f"[peer128] RECONNECTED at {now}")
```

### Combined Health Monitor Script

For an overview of all peers in one run, use a single `peer-health.py` that aggregates:

```python
PEERS = {
    "peer70":  {"host": "127.0.0.1",        "port": 8642, "role": "coordinator"},
    "peer84":  {"host": "192.168.178.84",    "port": 8642, "role": "worker"},
    "peer105": {"host": "192.168.178.105",   "port": 8642, "role": "worker"},
    "peer106": {"host": "192.168.178.106",   "port": 8642, "role": "worker"},
    "peer128": {"host": "192.168.178.112",   "port": 8642, "role": "worker"},
}
```

This writes to `~/.hermes/peer-network/status.json` once per run and produces a styled terminal report.

## Faro Beacon → /health Migration

When all peers are running Hermes API servers, the old beacon system (dedicated listener :9191, beacon.sh scripts) can be retired in favour of direct /health polling.

### Old System (Before)
```
peer105 (beacon.sh) ──curl──→ N56VV(:9191) Faro listener
peer106 (beacon.sh) ──curl──→ N56VV(:9191) Faro listener
peer128 (beacon.sh) ──curl──→ N56VV(:9191) Faro listener
```

### New System (After)
```
peer70 (peer-health.py, hourly)
  ├── GET /health → peer105( :8642)  ← no auth needed
  ├── GET /health → peer106( :8642)
  ├── GET /health → n56vv( :8642)
  └── GET /health → peer128( :8642)
```

### Migration Steps
1. Create heartbeat scripts on the orchestrator for each peer
2. Register cron jobs (no_agent=True, every 1h or appropriate interval)
3. Run each cron manually to verify health checks work
4. After verifying all pipes work, stop the beacon-listener on the old orchestrator
5. Leave beacon.sh scripts running on peers — they'll fail silently (harmless) or update them to stop sending

### When NOT to Migrate
If any peer doesn't run Hermes API (e.g., runs a custom agent without `/health`), keep the beacon system for that peer. The migration only works when ALL peers have Hermes API on :8642.

### API Delegation for Cross-Machine Configuration Retrieval

When the orchestrator needs to **adopt a service configuration** that was previously running on another peer (e.g., email client setup with IMAP/SMTP credentials), use API delegation with sequential probing:

**Pattern: Query → Extract → Replicate**

1. **Query the source peer** via chat completions (sequential short questions, see above)
2. **Extract**: config file paths, tool type, password mechanism
3. **Replicate**: install the same tool and create matching config files on the destination

**Real-world example: Himalaya email migration (peer84 → peer70)**

Step by step:
```
# 1. Health check (instant)
GET /health → 200 OK

# 2. Identify tool (short question, 200 tokens max)
Q: "Che tool email usi su di te?"  
R: "Uso himalaya per le email"

# 3. Get config path (50 tokens)
Q: "Dammi il percorso config himalaya."
R: "~/.config/himalaya/config.toml"

# 4. Read config file (2000 tokens — may timeout, retry as shorter request)
Q: "Leggi il config e mandamelo completo."

# 5. Get password (need to ask the peer to read the password file or password command)
Q: "Leggi il file /home/fausto/.config/himalaya/virgilio.pass"

# 6. Replicate on destination
- Install himalaya (if not present)
- Create config.toml on destination with same IMAP/SMTP settings
- Create password file with same content
- Set correct permissions (chmod 600)
```

**Observed constraints:**
- Even short sequential queries to a constrained peer can take 5-30s each — the whole migration takes 2-4 minutes
- The password file likely contains the actual secret — store it with `chmod 600` on the destination
- After installing and configuring, verify with a test command (e.g., `himalaya folder list`)

When the orchestrator needs to read/write files that live on another peer (e.g., Obsidian vault on N56VV), use **API delegation** — send a chat request to the peer hosting the files:

```python
import json, urllib.request

def ask_peer_to_read_file(host, port, api_key, filepath):
    """Ask a peer to read a file and return its contents via chat API."""
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{
            "role": "user",
            "content": f"Read the file at {filepath} and return its EXACT contents. Respond ONLY with the raw file content, no commentary or markdown formatting."
        }],
        "max_tokens": 4000,
    }).encode()

    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]

def ask_peer_to_write_file(host, port, api_key, filepath, content):
    """Ask a peer to write content to a file."""
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{
            "role": "user",
            "content": f"Write the following content to {filepath}. Use write_file tool. Confirm the file was written by reading it back and reporting its hash or size. Content:\n\n{content}"
        }],
        "max_tokens": 500,
    }).encode()
    # ... similar request
```

### When to Use
- Obsidian vault / Markdown knowledge base on another machine
- Quest files, research queues, or any user content on a non-orchestrator peer
- Any file that lives on a machine that isn't the coordinator

### Pitfalls
- **Model cost**: Each API delegation costs ~60-100K input tokens (the peer loads its full context). Space requests 30+ min apart.
- **Response reliability**: The peer may not follow exact formatting instructions. Always ask for structured output (JSON, raw text) explicitly.
- **Timeout**: Use 120s+ timeout — peers, especially on constrained hardware, can be slow to generate.
- **Verification**: When writing files, ask the peer to verify (read back and report hash/size) rather than trusting self-report.
- **Scheduling**: Agent-driven cron jobs that use API delegation should run fewer times per day than no_agent heartbeat jobs (every 4h vs every 1h).
**Step 1 — Audit what's already running on the target:**

```bash
# List all existing cron jobs on the new orchestrator
cronjob(action='list')

# Check what peer scripts already exist
find ~/.hermes/scripts/ -name 'peer-*' -o -name '*heartbeat*' -o -name '*keepalive*'
```

**Step 2 — Verify peer-mesh config:**

Check `~/.hermes/peer-mesh.yaml` has all peers listed. If the handover document mentions peers not in the mesh, add them. The file should contain every peer — the replacement orchestrator, the old orchestrator, workers, offline machines.

**Step 3 — Verify /health on all peers:**

Before accepting the role, confirm every claimed online peer responds:

```bash
# For each peer IP:
curl -s -o /dev/null -w "%{http_code} %{time_total}s" http://<peer-ip>:8642/health --connect-timeout 5
# Expected: 200 OK quickly
```

If browser_navigate is available instead of curl (no terminal tool):
```python
# Navigate to http://<peer-ip>:8642/health
# Expected response: {"status": "ok", "platform": "hermes-agent"}
```

**Step 4 — Cross-check handover claims against reality:**

The handover may list cron jobs to "migrate" that are already running on the target. For each claimed job:

- If it already exists on the new orchestrator → mark as VERIFIED, do NOT create a duplicate
- If it does NOT exist → create using the same schedule/script
- If it exists with a slightly different schedule → keep the existing one (it was likely tuned), document the discrepancy

**Step 5 — Save the handover document locally:**

### 9. Persistence across reboots

On **Linux** (Raspberry Pi, Ubuntu, Fedora), use a **systemd service** for reliable persistence with auto-restart:

```bash
sudo cat > /etc/systemd/system/hmp-server.service << 'EOF'
[Unit]
Description=HMP Server - Hermes Mesh Protocol
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/hmp.py 8643
Restart=always
RestartSec=10
User=<user>
WorkingDirectory=/home/<user>

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable hmp-server.service
sudo systemctl start hmp-server.service
```

Verify: `systemctl status hmp-server.service`

**Alternative — crontab @reboot** (simpler, no auto-restart):

```bash
# crontab -e
@reboot sleep 10 && cd ~ && nohup python3 ~/hmp.py 8643 > ~/.hermes/data/hmp/server.log 2>&1 &
```

On **macOS**, use a LaunchAgent (`launchd`) for reliable persistence. LaunchAgents auto-restart on crash and survive macOS updates:

**Step 6 — Tell the old orchestrator to retire its cron jobs:**

Once the new cron jobs are verified running on the replacement, instruct the old orchestrator to remove its copies. Use the peer's API endpoint, not SSH:

```python
# Via the old orchestrator's chat completions API:
POST http://<old-orchestrator>:8642/v1/chat/completions
{
  "model": "hermes-agent",
  "messages": [{"role": "user", "content": "Remove all migrated cron jobs now that peer70 is the coordinator: remove peer105-heartbeat, peer106-heartbeat, research-queue, quest-advancement, weekly-peer-exchange, faro-beacon from your cron."}]
}
```

**Step 7 — Handle offline peers gracefully:**

If a peer is listed as offline (e.g. peer128), do not create its keepalive/health jobs yet. The heartbeat script/script-based job can run harmlessly and will just record OFFLINE until the peer returns. Keep the schedule in place so recovery is auto-detected.

**Step 8 — Confirm the role transition via health status:**

Update peer-monitor or the monitoring script to mark the new orchestrator's role:
- Update description strings (e.g. "orchestratore" → "coordinatore", flag emoji)
- Update KNOWN_PEERS list if the old orchestrator changes role from coordinator to worker
- Save the new status file so downstream dashboards reflect the change

## Peer Onboarding via HMP

When a new peer joins the cluster (or an existing peer is elevated to first-class citizenship), introduce it to the cluster via an HMP message:

```bash
curl -s -X POST http://<peer-ip>:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text",
    "text": "Benvenuto! Sei parte del cluster Hermes. Ecco i tuoi peer:\n\n• peer70 (coordinatore) — RPi4 Debian 11, 24/7, IP 192.168.178.70\n• peer105 — RPi3B Fedora 30, YouTube/trascrizioni, IP 192.168.178.105\n• TU — descrizione e ruolo qui\n• peer84 — N56VV Ubuntu 22.04, heavy duty (cooling 11-17, 02-03)\n• peer128 — MacBook Pro macOS, portatile\n\nTi contatterò periodicamente per health check e task.",
    "sender": "peer70"
  }'
```

The HMP gateway plugin accepts `{"type": "text", "text": "...", "sender": "peer70"}` format. This is different from the old standalone HMP format which used `hmp_version`, `payload`, etc.

After sending the introduction, verify the peer is reachable and add it to all monitoring scripts:
1. `peer-<name>-heartbeat.py` — dedicated heartbeat script
2. `peer-health.py` — combined health monitor (add to PEERS dict)
3. `peer-health-watch.py` — HMP port watch (add to PEERS tuple)
4. `hmp-healthcheck.py` — HMP bidirectional healthcheck (add to PEERS dict)
5. Any task-specific dispatchers (research_queue.py, etc.)

See `scripts/hmp-healthcheck.py` for the current peer list with all active peers on port 18643.

Set up a silent cronjob (no user notification) on the orchestrator:

```python
# peer-monitor.py — runs every hour via cronjob (deliver=local)
# Pings each peer's /health endpoint, saves status to STATUS.md and JSON
```

Key features:
- Detect state changes (online↔offline) between ticks
- Log history for trend analysis
- Discover new LAN devices via ARP table (`ip neigh show`)
- Save machine-readable JSON for programmatic access

### Installing HMP on a New Peer

To add a new peer to the HMP mesh from the coordinator:

```bash
# 1. Copy hmp.py to the peer
scp fausto@<coordinator-ip>:~/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts/hmp.py ~/hmp.py

# Alternative (when scp fails): pipe via base64
base64 hmp.py | sshpass -p '<password>' ssh -o StrictHostKeyChecking=no <user>@<peer-ip> \
  "base64 -d > ~/hmp.py && chmod +x ~/hmp.py && echo OK"

**Alternative — base64 pipe (when scp won't work):** When the coordinator and target peer use different SSH auth methods (key vs password), or scp gets `Permission denied`, pipe the binary through base64:

```bash
# From coordinator, pipe binary to target peer
base64 hmp.py | sshpass -p '<password>' ssh -o StrictHostKeyChecking=no <user>@<target-ip> \
  "base64 -d > ~/hmp.py && chmod +x ~/hmp.py && echo OK"
```

This works for any single-file tool. For multi-file tools, tar+gz+base64 the directory first. Requires `sshpass` on the coordinator and SSH password access on the target. If `sshpass` is unavailable, install it: `sudo apt-get install sshpass` (Debian/RPi) or `sudo dnf install sshpass` (Fedora).

# 2. Verify it works
python3 -c "from hmp import HMPClient, new_message_id, now_iso; print('HMP OK')"

# 3. Send a test ping to the coordinator via HMP
python3 -c "
import json, urllib.request, time
msg = {
    'hmp_version': '1.0',
    'message_id': 'ping_<peer_name>_' + str(int(time.time())),
    'idempotency_key': 'ping_<peer_name>_' + str(int(time.time())),
    'from': '<peer_name>',
    'to': 'peer70',
    'type': 'request',
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'timeout': 30,
    'payload': {'task_type': 'ping', 'instruction': 'Ping da <peer_name> via HMP!'}
}
data = json.dumps(msg).encode()
req = urllib.request.Request('http://<coordinator-ip>:8643/hmp/send',
    data=data, headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=10)
print('HMP ping sent:', resp.read().decode())
"
```

After sending the ping, run the message-router on the coordinator to deliver the message:

```bash
cd ~/.hermes && python3 scripts/hmp-message-router.py
```

The peer only needs the `hmp.py` client — no server required. The coordinator handles all message routing and persistence. For **bidirectional** HMP communication (mesh topology), install the HMP server on the peer too — see `references/hmp-protocol.md` → "Server Installation on a New Peer".

### Adding to PEER_API in the Router

If the coordinator's message-router should forward messages TO this new peer, add it to `PEER_API` in `hmp-message-router.py`:

```python
PEER_API = {
    "newpeer": {
        "url": "http://<newpeer-ip>:8642/v1/runs",
        "key": "<newpeer-api-key>",
        "timeout": 10,      # adjust based on peer speed
    },
}
```

## Waking Peers from Sleep

macOS peers (and some Linux laptops) can enter deep sleep (lid closed, idle timeout). The coordinator can wake them via SSH:

```bash
# Attempt SSH to wake (works even if SSH command fails)
ssh -o ConnectTimeout=5 fausto@<peer-ip> "echo wake" 2>/dev/null
sleep 3
# Retry API
curl -s --connect-timeout 5 http://<peer-ip>:8642/health
```

If the Hermes gateway doesn't restart automatically after wake, pipe through SSH:

```bash
ssh -o ConnectTimeout=5 fausto@<peer-ip> "hermes gateway restart 2>&1" 2>/dev/null
# Wait for restart, then verify
sleep 5
curl -s http://<peer-ip>:8642/health
```

### Persistent Sleep Prevention (macOS)

For a Mac that should stay reachable 24/7 in the mesh, use a **LaunchAgent** to run `caffeinate` persistently:

```bash
# Create the launchd plist
cat > ~/Library/LaunchAgents/com.peer.caffeinate.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.peer.caffeinate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-d</string><string>-i</string><string>-t</string><string>86400</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.peer.caffeinate.plist
```

**Note:** `caffeinate` cannot prevent lid-close sleep on MacBooks. Only `sudo pmset -a disablesleep 1` works for that. Without sudo, the Mac will sleep when the lid is closed, and the coordinator must wake it via SSH.

The HMP protocol uses a SQLite-backed bus at `~/.hermes/data/hmp/agent_messages.db`. When the HMPBus Python module isn't importable (wrong path, no sys.path setup), you can update messages directly via SQLite:

```bash
# Update status to 'working'
python3 -c "
import sqlite3
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
c.execute('UPDATE messages SET status=?, updated_at=? WHERE message_id=?',
    ('working', '2026-07-14T22:05:00Z', 'msg_xxx'))
c.commit()
c.close()
"
```

**Key tables and columns:**
- `messages` table: `message_id`, `status`, `from_peer`, `to_peer`, `type`, `payload`, `progress`, `progress_pct`, `has_progress`, `created_at`, `updated_at`, `delivered_at`, `completed_at`
- Valid statuses: `pending`, `queued`, `delivered`, `working`, `completed`, `failed`, `needs_input`, `timed_out`, `cancelled`
- State machine: `pending→queued/delivered→working→completed/failed/timed_out` (or `pending→working` for direct agent claim by HMPWorker)
- `payload` is a JSON text column — use `json.dumps()` before writing
- `progress` is a free-text field for human-readable status
- `progress_pct` is a float (0-100), with `has_progress` as boolean flag

**Use this pattern when:**
- The HMPBus module is on a path not in sys.path and you can't add it
- You're running from a cron `no_agent=true` script with limited Python environment
- You need a quick one-off update without importing the full module

**Pitfall — `$` sign expansion in bash:** When writing SQLite updates from bash scripts, use `python3 << 'PYEOF'` heredocs (not `python3 -c "..."`) for any payload containing `$` characters (e.g., prices like `$299`). See `cron-operations` skill -> "Bash Script Pitfalls with `no_agent=true`" for details.

## Pitfalls

### Virgilio SMTP: IP-level rate-limit trap on invalid recipients

When an orchestrator uses API delegation to configure email on a new peer and a first send fails (invalid domain like `gmail.dom`), the SMTP client (himalaya) retries 20+ times, triggering a **30+ minute IP-level rate-limit ban** from Virgilio. All subsequent sends from that IP fail; IMAP reading unaffected.

**Prevention:** validate recipient domain before sending with `host -t MX <domain>`.
**Recovery:** wait 30-60 minutes or use a different peer with a different public IP.

Also note: `smtp.virgilio.it` on port 587 (STARTTLS) presents a `*.libero.it` certificate — hostname mismatch that blocks any mail client doing strict verification. Use port 465 (direct TLS) only. Full details in `references/italian-email-providers.md`.

### Stale Python bytecode cache after plugin deploy

When deploying updated HMP plugin files (adapter.py, core.py) to a peer, the running gateway process may use stale `.pyc` bytecode cached in `__pycache__/`. Python's invalidation check compares the `.pyc` timestamp to the `.py` source — if they fall within the same second, the old bytecode is used even though the source has changed.

**Symptoms:** The plugin's source file on disk has the new code (confirmed by md5sum matching the coordinator), but the running gateway responds with the old behaviour (e.g., agent-card missing new fields). Health endpoints and HMP send work fine.

**Fix:**
```bash
# 1. Stop the gateway
systemctl --user stop hermes-gateway

# 2. Delete ALL bytecode cache in the plugin directory
rm -rf ~/.hermes/plugins/hmp/__pycache__/
find ~/.hermes/plugins/hmp -name '*.pyc' -delete

# 3. Start the gateway fresh
systemctl --user start hermes-gateway
```

**Verification:** Check the agent-card endpoint for new fields:
```bash
curl -s http://<peer-ip>:18643/hmp/agent-card
```

If the endpoint still shows old behaviour despite correct source files and deleted cache, the gateway may have loaded the module from an alternative plugin path (e.g., `/home/fausto/.hermes/plugins/hmp/` vs `/root/.hermes/plugins/hmp/` on multi-user setups). Check all locations.

### Heartbeat health-check port selection

The Hermes API server (:8642) and the HMP gateway plugin (:18643) are **separate services** on a peer. A peer may have the HMP gateway running but the API server down (or vice versa). When creating heartbeat scripts:

- Use `/health` on **port 8642** to verify the full Hermes agent (API reachable)
- Use `/health` on **port 18643** to verify the HMP gateway (mesh communication)
- Use `/hmp/send` on **port 18643** for bidirectional ping (the HMP healthcheck pattern)

The combined health monitors (`peer-health.py`) use port 8642; the HMP-specific healthchecks (`hmp-healthcheck.py`, `peer-health-watch.py`) use port 18643. Keep both so you know which service is down.
The gateway refuses `systemctl --user restart hermes-gateway.service` from within its own process (even via `background=true` or `delegate_task`). Always use system crontab or a separate shell.

### API server config YAML structure
The `host` and `port` keys **must** be under `extra:` in the YAML, not directly under `api_server:`:
```yaml
# ✅ CORRECT
api_server:
  enabled: true
  extra:
    host: 0.0.0.0
    port: 8642

# ❌ WRONG — host/port are silently ignored
api_server:
  enabled: true
  host: 0.0.0.0
  port: 8642
```

### API key required for public bind
The API server refuses to start without `API_SERVER_KEY` on any bind. On `0.0.0.0`, it additionally enforces minimum 16-char key length.

### Don't claim protocol completeness before end-to-end verification
HMP requires **four components** verified before declaring a peer operational: (1) message sent, (2) message routed, (3) message processed/responded, (4) response delivered. Testing only one direction (e.g. coordinator→peer sends OK) does NOT mean the return path works. Always use the checklist in `references/hmp-protocol.md` → "Pitfalls" → "Don't claim completeness" before telling the user a peer is HMP-ready.

### HMP is the primary protocol
On this mesh, communicate with peers via HMP (port 18643) first. Fall back to API Hermes (port 8642) for complex tasks that need a full agent session. Use SSH only for maintenance or waking sleeping machines.`
### Mac may be slow to respond
Macs on WiFi may have 100-200ms RTT and thermal throttling can cause API timeouts. Use `--max-time 120` for curl calls and `timeout=120` for `urllib`/`requests` calls to macOS peers. The chat completions endpoint on a Mac can take 30-90s to respond even when the `/health` endpoint is instant — the model needs to load and generate.

### UPnP/TR-064 port forwarding writes
On FritzBox 7490 (and likely others), UPnP IGD **delete** works but **add** returns error 606 (Action not authorized). This is a FritzBox security restriction — enable "Allow changes via UPnP" in the web UI, or use web-API-based approaches instead.

`~/.hermes/scripts/fritzbox-portmgr.py` wraps the TR-064 API for listing/adding/deleting port forwarding rules. Requires FritzBox admin password. Read operations (list, info) work without auth; write operations (add, delete) require a FritzBox user with UPnP write permissions enabled.

### DHCP IP changes on peers

Peers that get IPs via DHCP (especially macOS laptops) can change IPs. The DNS hostname (e.g., `Faustos-MacBook-Pro-Home-3.fritz.box`) is more stable than the raw IP. Always prefer DNS hostnames in `PEER_API` configs, but keep a fallback IP for direct access. When a peer's IP changes:
- ARP entries for the old IP show FAILED
- `ip neigh show` confirms the new IP
- Update `peers_config.json` with the new IP
- The message-router retries queued messages on every cycle, so it self-heals once the peer is reachable again

### HMP message field naming: `payload.text` vs `payload.instruction`

The HMP gateway plugin's `extract_text()` searches for text in
`payload.text`, `payload.content`, `payload.message`, or `payload.query`
(in that order). Using `payload.instruction` returns
`{"accepted": false, "error": "empty_text"}`.

```json
// ✅ CORRECT
{"payload": {"text": "Ciao mondo"}}

// ❌ WRONG — accepted: false
{"payload": {"instruction": "Ciao mondo"}}
```

Same for top-level fields: `body.text` works; `body.instruction` does not.

### Duplicate cron jobs from partial migration
When an orchestrator handover or migration happens in stages, some cron jobs may already be running on the target from a prior session. Always run `cronjob(action='list')` before creating any new job. If the job already exists (same name, same schedule, same script), do NOT create a duplicate — the duplication is invisible until the job list is read, and the scheduler will run both copies independently.

If you accidentally create a duplicate, remove it immediately:
```
cronjob(action='remove', job_id='<id>')
```

The `cronjob` tool's `list` output includes `next_run_at` and `last_run_at` — if a job has `last_run_at: null` and you just created it, it's a fresh one. Jobs with historical `last_run_at` values are pre-existing and should be left alone.

### Env var references may not exist at runtime

The `peer-mesh.yaml` `api_key_env` fields are **declarative references** — they name env vars that SHOULD exist, but there is no runtime check. When a coordinator transition moves the mesh to a new machine, the env vars from the old coordinator don't travel with it.

**This session's real-world example:** `peer-mesh.yaml` referenced `HERMES_PEER_105_KEY` and `HERMES_PEER_106_KEY`, but neither env var was set on the new coordinator (peer70). The keys only existed as notes in past conversations and had to be provided manually by the user.

**Fix during handover:** after copying the peer-mesh.yaml to the new coordinator, verify every referenced env var actually exists:
```bash
for var in $(grep api_key_env ~/.hermes/peer-mesh.yaml | awk '{print $2}'); do
  if [ -z "${!var+x}" ]; then
    echo "MISSING: $var — must be set or stored in peers_config.json"
  fi
done
```

**Long-term fix:** maintain `~/.hermes/scripts/peers_config.json` with the actual key values (not env var names). Cron scripts and API delegation use this file directly, bypassing env vars entirely.

### Configuration drift between peers_config.json and peer-mesh.yaml

The network uses **two config files** that can drift out of sync:

| File | Purpose | Location |
|------|---------|----------|
| `peers_config.json` | API key + host mapping for cron scripts | `~/.hermes/scripts/` |
| `peer-mesh.yaml` | Full topology with roles, capabilities, notes | `~/.hermes/` |

**Common drift scenarios:**
- A peer is added to `peer-mesh.yaml` (full description) but not to `peers_config.json` (no API key for cron scripts)
- A peer's IP changes in one file but not the other
- `peer-mesh.yaml` references env vars (`HERMES_PEER_105_KEY`) that don't actually exist in the environment

**Fix: after any peer addition or handover, verify both files are consistent:**
```bash
# Check all peers in peer-mesh.yaml have an env var defined
grep api_key_env ~/.hermes/peer-mesh.yaml | while read line; do
  var=$(echo $line | sed 's/.*: //')
  if [ -z "${!var+x}" ]; then
    echo "MISSING ENV: $var"
  fi
done

# Check all peers in peers_config.json have a matching entry in peer-mesh.yaml
# (look for matching IP addresses across files)
```

## Related

- `hermes-agent` skill (for general Hermes configuration)
- Files at `~/.hermes/scripts/peer-monitor.py`, `~/.hermes/peer-network/`
- `references/hmp-protocol.md` — HMP (Hermes Mesh Protocol): lightweight stdlib-only message-passing layer on port `:8643`...
- `references/hmp-watchdog-pattern.md` — HMP-based system watchdog: monitor disk, RAM, load, uptime, temperature on worker peers and report via HMP protocol. Complementary to the API-based `/health` polling pattern. Includes threshold configuration, cron installation, and coordinator querying.
- `scripts/watchdog_hmp.py` — Reusable watchdog script: `/usr/local/bin/watchdog_hmp.py` on worker peers, runs every 30min via cron. Sends `watchdog_alert` and `health_report` messages to coordinator via HMP protocol.
- `scripts/hmp-worker-llm.py` — Universal HMP Worker with optional LLM support. Gracefully falls back to pong/echo when Hermes is unavailable. Works on Linux ARM, x86, and macOS without modification. See `references/hmp-llm-integration.md` for handler registration pattern.

## Protocol Contract — HTTP Only

The HMP protocol surface is **purely HTTP**. Two implementations exist:

| Implementation | Port | Backend | Fleet status (2026-07) |
|----------------|------|---------|-----------------------|
| **Hermes gateway plugin** (preferred) | `18643` | Hermes agent session | ✅ **Attivo su tutti i peer** |
| **Standalone hmp.py** (legacy) | `8643` | Custom SQLite bus | ❌ **Fermo su tutti i peer** — solo riferimento storico |

Messages must use `payload.text` for the message content (see `references/hmp-protocol.md` → "Sending Messages via the Gateway Plugin").

**Public HTTP endpoints (the contract):**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Liveness check |
| `GET` | `/hmp/agent-card` | Peer capabilities |
| `POST` | `/hmp/send` | Submit a message |
| `GET` | `/hmp/poll/{id}` | Poll message status |
| `POST` | `/hmp/cancel/{id}` | Cancel a queued message |

**Rule:** All inter-peer communication MUST go through these endpoints using a plain HTTP client (`urllib`, `curl`, etc.). Never read another peer's SQLite DB, never peek at local state that isn't exposed via `/hmp/poll/`.

### send_and_wait — Pure HTTP Polling

```python
def send_and_wait(client, msg, poll_interval=3, timeout=60):
    \"\"\"Send a message and wait for terminal state — HTTP only.\"\"\"
    result = client.send_message(msg)
    if "error" in result:
        return result
    mid = result["message_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.poll_message(mid)
        if "error" in resp:
            return resp
        status = resp.get("status")
        if status in ("completed", "failed", "timed_out", "cancelled"):
            return resp
        time.sleep(poll_interval)

    return {"status": "timed_out", "message_id": mid, "from": msg.get("from")}
```

No `import sqlite3`. No local file access. Only `urllib.request` calls to the remote peer's HTTP surface. The caller does not need to know whether the peer uses SQLite, a flat file, or an in-memory store — that's implementation.

See `references/hmp-gateway-plugin.md`.

## Protocol Updates (2026-07-15 Session)

This session identified and fixed a critical **blind spot** in the HMP protocol: the gap between "message stored on the bus" (`delivered`/`pending`) and "message accepted by the target's agent". 

**Problem:** Messages sent via HMP were stored in the target's SQLite bus but no agent existed to pick them up, process them, and send ACK/responses. "Delivered" meant "stored on peer70" — not "peer70's agent is processing it".

**Fix — Two new components added to `hmp.py`:**

| Component | Role |
|-----------|------|
| `HMPWorker` | Per-peer daemon that polls the local bus, sends ACK, processes tasks, sends completed/failed responses. Guarantees every request gets an ACK or rejection. |
| `HMPCoordinator` | Runs on peer70, monitors for stale deliveries (no ACK within 15s), stale workers (no heartbeat within timeout), and timed-out messages. |

**New CLI subcommands:**
- `python3 hmp.py server [port]` — HTTP server (was `hmp.py <port>`)
- `python3 hmp.py worker` — Worker agent daemon (new)
- `python3 hmp.py coordinator` — Timeout enforcer on peer70 (new)
- `python3 hmp.py once` — Single poll cycle for testing (new)

**State machine fix:** Added `STATE_WORKING` to allowed transitions from `STATE_PENDING`, enabling the Worker to claim a task immediately.

**Peer registry:** Built-in `DEFAULT_PEER_REGISTRY` mapping `peerNN → http://192.168.178.NN:8643` for DNS-free resolution.

**Verification:** After the fix, a message sent from peer70 → peer106 produces exactly 1 ACK + 1 completed response on peer70's bus, with the local message on peer106 showing status `completed` — no duplicate processing.

See `references/hmp-protocol.md` → "HMPWorker — Agent Loop" and "HMPCoordinator — Timeout Enforcement" sections for full documentation.
- `references/hmp-llm-integration.md` — Connecting HMPWorker to an LLM (Hermes CLI, OpenAI API) for conversational message handling. Covers the `hermes chat -q` non-interactive mode, importlib module loading, handler registration pattern, and deployment.
- `references/italian-email-providers.md` — Virgilio IMAP/SMTP configuration (port 465 TLS, Italian folder names, password wrapper script) for use with the cross-machine email migration pattern above
- `references/visual-peer-identity.md` — per-peer shell prompt color scheme for instant visual recognition across the mesh
- `references/hmp-healthcheck-cron-pattern.md` — HMP healthcheck cron job: pre-run script pattern, agent session workflow, known issues with Tirith in cron mode, persistent-state detection, cron prompt anti-pattern, and historical log format
- `references/framebuffer-ascii-overlay.md` — layering ASCII art on a framebuffer dashboard during screensaver (NetBoard pattern)
- `scripts/research-queue-processor.py` — Reusable script: fetches queue from peer84 via API, parses items, dispatches YouTube to peer105 and web research to peer106, updates queue status. Run via `delegate_task` with `toolsets=["terminal"]` from cron context.
