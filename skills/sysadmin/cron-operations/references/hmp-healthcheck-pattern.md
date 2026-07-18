# HMP Health Check — Cron Pattern

> ⚠️ **ARCHITECTURAL UPDATE (2026-07-17):** This reference initially
> described the **standalone HMP server** on port 8643 with a
> send-then-poll pattern. The deployment has since migrated to the
> **HMP gateway plugin** on port **18643**, which uses a simplified
> single-request ping. Both architectures are documented below — the
> current one first, the legacy one at the bottom.

## Overview (Current Architecture — Gateway Plugin on Port 18643)

The current HMP health check uses the **Hermes Gateway HMP plugin**,
which exposes a simple HTTP endpoint on port 18643. Instead of a
multi-phase send-then-poll protocol, the gateway plugin accepts a
bare-minimum JSON POST and responds immediately with acceptance status.

**Key difference from old architecture:** No separate poll phase, no
structured HMP message envelope (`hmp_version`, `message_id`, `to/from`,
`timeout`). The gateway plugin handles routing internally; the client
only needs `{"type": "text", "text": "...", "sender": "peer70"}`.

## Architecture Comparison

| Aspect | Old HMP Server (port 8643) | Gateway Plugin (port 18643) |
|--------|---------------------------|-----------------------------|
| Port | 8643 | 18643 |
| Endpoint | `/hmp/send` + `/hmp/poll/{id}` | `/hmp/send` only |
| Payload | Full HMP envelope (8+ fields) | Simple ping `{type, text, sender}` |
| Response | `{message_id, duplicate}` + poll later | `{accepted, status}` immediate |
| Poll phase | Required (GET after 2s delay) | Not needed — single POST |
| SSH fallback | Supported for peer128 | Not implemented (plugin handles routing) |

## When to Use HMP vs HTTP /health

| Check type | Endpoint | Port | What it tests | Latency |
|---|---|---|---|---|
| HTTP `/health` | `GET /health` | 8642 | Hermes API server is running | ~1-2s |
| HMP ping (gateway plugin) | `POST /hmp/send` | 18643 | HMP message routing is functional | ~1-3s |

**Use HMP when:**
- You want to verify the peer's HMP gateway plugin is accepting messages
- You need quick up/down status on the peer's plugin layer
- You want a single-request health check with immediate response

**Use HTTP /health when:**
- You only need to know if the peer machine is online and Hermes is running
- You want to verify the peer's API server is up (independent of HMP)
- Faster (GET vs POST) and simpler test

## Port Discovery

To find the actual HMP port on any deployment, check:

```bash
# Option 1 — config.yaml
grep 'hmp.port\|18643\|8643' ~/.hermes/config.yaml

# Option 2 — running processes (best for cron scripts)
ss -tlnp | grep hermes  # shows all listening Hermes ports

# Option 3 — plugin status
hermes plugins list 2>&1 | grep hmp
```

On this peer70 deployment, the HMP plugin listens on **port 18643**.

## Current Architecture: Simple Ping (Port 18643)

The gateway plugin on port 18643 accepts a minimal POST and responds
immediately with `{accepted: true/false, status: "queued"|"working"|...}`.

### Ping Format

```json
{
  "type": "text",
  "text": "HMP healthcheck orario — ping da peer70",
  "sender": "peer70"
}
```

| Field | Value | Notes |
|-------|-------|-------|
| `type` | `"text"` | Always `"text"` for health checks |
| `text` | Human-readable ping message | Identifies the source in peer logs |
| `sender` | Sender peer name | Usually `"peer70"` (the orchestrator) |

### Response

The gateway responds with a JSON object containing `accepted` and `status`:

```json
{"accepted": true, "status": "queued"}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `accepted` | `true` / `false` | Whether the gateway accepted the message for routing |
| `status` | `"queued"`, `"working"`, `"error"` | Current processing status |

A response of `accepted: true` with any `status` value means the peer's
HMP plugin is reachable and operational. The `status` sub-field
(`"queued"` vs `"working"`) indicates whether the message is being
processed or waiting in queue — for health check purposes, both are OK.

### Python Implementation (Current)

```python
import json, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer70": {
        "url": "http://127.0.0.1:18643/hmp/send",
        "timeout": 5,
        "role": "coordinatore",
        "desc": "RPi4 Debian 11 — orchestratore 24/7",
    },
    "peer105": {
        "url": "http://192.168.178.105:18643/hmp/send",
        "timeout": 8,
        "role": "worker",
        "desc": "RPi3B Fedora 30 — YouTube/trascrizioni",
    },
    "peer106": {
        "url": "http://192.168.178.106:18643/hmp/send",
        "timeout": 8,
        "role": "worker",
        "desc": "ARMv8 Fedora 30 — web research (Trixie!)",
    },
    "peer84": {
        "url": "http://192.168.178.84:18643/hmp/send",
        "timeout": 8,
        "role": "worker",
        "desc": "N56VV Ubuntu 22.04 — heavy duty (cooling 11-17, 02-03)",
    },
    "peer128": {
        "url": "http://192.168.178.112:18643/hmp/send",
        "timeout": 10,
        "role": "worker",
        "desc": "MacBook Pro macOS — portatile",
    },
}


def hmp_ping(peer_name, peer_info):
    msg_id = f"hc_{peer_name}_{int(time.time())}"
    payload = json.dumps({
        "type": "text",
        "text": "HMP healthcheck orario — ping da peer70",
        "sender": "peer70",
    }).encode()
    req = Request(peer_info["url"], data=payload,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=peer_info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            accepted = result.get("accepted", False)
            status = result.get("status", "unknown")
            if accepted:
                return ("ok", f"accepted ({status})")
            else:
                return ("error", f"refused: {result.get('error', '?')}")
    except HTTPError as e:
        if e.code == 413:
            return ("ok", "alive (413 — text too long, but reachable)")
        return ("error", f"HTTP {e.code}")
    except URLError as e:
        return ("error", f"unreachable: {e.reason}")
    except OSError as e:
        return ("error", f"connection failed: {e}")
    except Exception as e:
        return ("error", str(e))


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    online = 0
    total = len(PEERS)

    for peer_name, peer_info in sorted(PEERS.items()):
        status, detail = hmp_ping(peer_name, peer_info)
        if status == "ok":
            online += 1
        results.append((peer_name, peer_info["role"], peer_info["desc"],
                        status, detail))
        time.sleep(0.5)

    print(f"🌐 HMP Cluster Healthcheck — {now}")
    print()
    print(f"  {online}/{total} peer online")
    print()
    print(f"  {'Peer':<12} {'Ruolo':<14} {'Stato':<10} {'Dettaglio'}")
    print(f"  {'-'*12} {'-'*14} {'-'*10} {'-'*40}")
    for peer, role, desc, status, detail in results:
        icon = "🟢" if status == "ok" else "🔴"
        peer_label = f"{peer}"
        if peer == "peer106":
            peer_label += " ✨"  # Trixie star
        print(f"  {icon} {peer_label:<10} {role:<14} {status:<10} {detail[:40]}")
    print()
    if online == total:
        print("  ✅ TUTTI I PEER ONLINE")
    else:
        print(f"  ⚠️  {total - online} peer non raggiungibili")


if __name__ == "__main__":
    main()
```

Key differences from the old implementation:
- **No poll phase** — single POST, immediate response
- **No message envelope** — just `type`, `text`, `sender`
- **Self-ping on peer70** uses `127.0.0.1` (loopback, no network dependency)
- **No SSH fallback** — plugin handles routing; if the peer is down, nothing to SSH into
- **0.5s delay between peers** prevents burst saturation
- **Sorted output** by peer name for consistent table ordering
- **Trixie (peer106)** gets a ✨ star in output (local convention)

## Python Implementation

```python
import json, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer84": {
        "url": "http://192.168.178.84:8643/hmp/send",
        "poll_url": "http://192.168.178.84:8643/hmp/poll",
        "timeout": 8,
    },
    "peer128": {
        "url": "http://192.168.178.112:8643/hmp/send",
        "poll_url": "http://192.168.178.112:8643/hmp/poll",
        "timeout": 15,
    },
}

SSH_FALLBACK = {
    "peer128": (
        "fausto@192.168.178.112",
        "curl -s --connect-timeout 3 http://127.0.0.1:8643/health",
    ),
}


def hmp_send(peer_name, peer_info, msg_id):
    msg = {
        "hmp_version": "1.0",
        "message_id": msg_id,
        "idempotency_key": msg_id,
        "from": "peer70",
        "to": peer_name,
        "type": "request",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeout": 30,
        "payload": {
            "task_type": "ping",
            "instruction": "Healthcheck HMP orario. Rispondi con ACK."
        },
    }
    data = json.dumps(msg).encode()
    req = Request(peer_info["url"], data=data,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=peer_info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            if result.get("duplicate"):
                return "sent_dup", result["message_id"]
            return "sent", result["message_id"]
    except (HTTPError, URLError, OSError) as e:
        if peer_name in SSH_FALLBACK:
            user_host, cmd = SSH_FALLBACK[peer_name]
            try:
                import subprocess
                r = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no",
                     "-o", "ConnectTimeout=5", user_host, cmd],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0 and '"ok"' in r.stdout:
                    return "sent_ssh", "via SSH fallback"
            except Exception:
                pass
        return "error", str(e)


def hmp_poll(peer_info, msg_id):
    try:
        with urlopen(f"{peer_info['poll_url']}/{msg_id}", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status", "unknown")
    except Exception:
        return "unreachable"


def main():
    timestamp_suffix = str(int(time.time()))
    results = []
    all_ok = True

    for peer_name, peer_info in PEERS.items():
        msg_id = f"hc_{peer_name}_{timestamp_suffix}"
        status, detail = hmp_send(peer_name, peer_info, msg_id)

        if status in ("sent", "sent_ssh", "sent_dup"):
            time.sleep(2)
            poll_status = hmp_poll(peer_info, detail if status == "sent_dup" else msg_id)
            results.append((peer_name, status, poll_status, detail))
            if poll_status in ("unreachable",):
                all_ok = False
        else:
            results.append((peer_name, "error", detail, ""))
            all_ok = False

    # Compose output
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🌐 HMP Healthcheck — {now}")
    print()
    print("| Peer | Invio | Stato HMP |")
    print("|---|---|---|")
    for peer, send_status, peer_status, mid in results:
        icon_send = "✅" if send_status in ("sent", "sent_ssh", "sent_dup") else "❌"
        icon_peer = "🟢" if peer_status in ("delivered", "working", "pending", "ok") else "🔴"
        method = " (via SSH)" if send_status == "sent_ssh" else ""
        print(f"| {peer} | {icon_send}{method} | {icon_peer} {peer_status} |")
    print(f"| peer70 | — | 🟢 orchestratore |")
    print()
    print(f"Stato: {'✅ TUTTO OK' if all_ok else '⚠️ PROBLEMI RILEVATI (vedi sopra)'}")
```

## SSH Fallback Strategy

When a peer's HMP HTTP endpoint is unreachable but the machine itself is
reachable via SSH, a fallback check can verify whether the HMP server
process is running locally:

```python
SSH_FALLBACK = {
    "peer128": (
        "fausto@192.168.178.128",
        "curl -s --connect-timeout 3 http://127.0.0.1:8643/health",
    ),
}
```

The fallback is attempted **only after** the HTTP send fails. It SSHes
into the peer and runs `curl` against `127.0.0.1:8643/health` — if the
HMP server responds locally, the issue is network-level (firewall, NAT,
routing, suspend), not a crashed HMP daemon.

Return status `"sent_ssh"` distinguishes SSH-fallback sends from direct
HTTP sends in the output.

## Notification Logic

The cron job should deliver output only when problems exist. The pre-run
script or agent tests `all_ok` to decide:

- `all_ok = True` → all peers reachable → **suppress delivery** (`[SILENT]`)
- `all_ok = False` → at least one peer unreachable → **check if the error
  changed since the last delivered report before deciding** (see
  `SKILL.md` → "Repeat Detection for Persistent Problems")

### Change Detection for Persistent Failures

When `all_ok = False`, do NOT blindly deliver. Read the previous run's
cron output (`~/.hermes/cron/output/<job_id>/<most recent>`) and
compare peer errors:

- **Error type changed** (e.g., 111→113, peer recovered) → **deliver**
- **Same peer(s), same error** → **`[SILENT]`** (avoid hourly spam)
- **New peer failing** → **deliver**
- **Peer recovered since last report** → **deliver**

This prevents the common pattern of delivering an identical "peer84
down" report every hour for 8+ hours with no change. One escalation
(see "Errno Translation" below) is sufficient; subsequent identical
reports are spam.

## History Log Pattern — `~/.hermes/peer-network/hmp-health.log`

Append each healthcheck result to `~/.hermes/peer-network/hmp-health.log`
with a blank-line separator between runs. This is the canonical log path
for HMP-specific health data (port 8643), distinct from `STATUS.md` (HTTP
API health on port 8642) and `backup_status.json` (backup probe results).

**When the cron prompt says "Salva l'output in ~/.hermes/peer-network/hmp-health.log":**
The pre-run script's output (`## Script Output`) is the authoritative data
source. The agent cannot re-run the script (Tirith block). Write the data
from `## Script Output` to the log file using `write_file` or `patch`.
No need to re-verify — the pre-run script already captured the data.

### Data Source Attribution in Log Entries

When the agent cannot re-run the script (Tirith block) and writes the
pre-run `## Script Output` data to the log file, add a `=== Note ===`
section below the status table documenting the data source:

```
=== Note ===
- Dati raccolti dal pre-run script alle 00:43:16.
- Lo script hmp-healthcheck.py non ha potuto essere eseguito
  direttamente: la policy di sicurezza cron blocca l'esecuzione
  di comandi terminal in contesto cron job.
- L'override in ~/.hermes/cron/cron_config_override.yaml non viene
  caricato automaticamente dal sistema di configurazione.
```

This attribution prevents confusion when reviewing the log later — it's
clear whether each entry came from a fresh script run or a cached agent
write.

Each entry is a self-contained Markdown block:

```
🌐 HMP Healthcheck — 2026-07-15 01:53:56

| Peer | Invio | Stato HMP |
|---|---|---|
| peer84 | ✅  | 🟢 pending |
| peer128 | ✅ (via SSH) | 🔴 unreachable |
| peer70 | — | 🟢 orchestratore |

Stato: ⚠️ PROBLEMI RILEVATI (vedi sopra)
```

⚠️ **Corruption risk when appending via write_file from agent**: When
the pre-run script is blocked (Tirith cron mode) and the agent uses
`write_file` (overwrite) instead of `open(..., "a")`, the entire file
is rewritten. If sibling cron jobs write to the same file, their
entries can be overwritten.

**When to use write_file (full rewrite):** Safe when this cron job is
the ONLY writer to the log file. Read the current file with
`skill_view`, append the new entry to the content, and write it all
back via `write_file`. This is simpler for exclusive-writer scenarios.

**When to use patch (append target end):** Required when multiple cron
jobs (e.g., HMP healthcheck + HTTP healthcheck + peer-health) write to
the same log file. Use `patch` with a unique anchor from the last entry
to append without overwriting sibling entries. The anchor must be the
**last unique content line** in the file — not the final blank line.
A working pattern from a production session:

```
# 1. Read the log file to find the last unique content line
read_file("~/.hermes/peer-network/hmp-health.log")

# 2. Use that last line as the anchor, replacing it with
#    itself + blank line + new entry (pass-through append):
patch(
    mode="replace",
    path="~/.hermes/peer-network/hmp-health.log",
    old_string="192.168.178.1   (router)   🟢 Flags 0x2",   # ← last unique line
    new_string="192.168.178.1   (router)   🟢 Flags 0x2\n\n🌐 HMP Healthcheck — 2026-07-15 23:53:10\n\n| Peer | Invio | Stato HMP |\n|---|---|---|\n| peer84 | ❌  | 🔴 Err 111 |\n| peer128 | ✅  | 🟢 pending |\n\nStato: ⚠️ PROBLEMI RILEVATI"
)
```

**Key details of this technique:**
- The `old_string` is a **pass-through** — it appears unchanged in
  `new_string`. `patch` replaces `old_string` with the entire
  `new_string`, so the anchor line stays and the new content follows it.
- The blank line between anchor and new content separates log entries.
- **Do NOT use the final blank line as an anchor** — `patch` requires a
  non-empty unique string. A trailing newline is invisible.
- **Verify by byte count:** Check `bytes_written` in the `patch` response
  — a large positive jump (e.g., 1353 → ~1650) confirms the append.
- **Risk of duplicate match:** If the anchor line appears twice (e.g.,
  both first and last entry share the same ending), `patch` matches the
  first occurrence instead of the last. Add 2-3 surrounding lines to the
  `old_string` to disambiguate.

See `references/peer-health-http-pattern.md` for the full append corruption
analysis.

**Verification:** After writing, check `bytes_written` in the tool
response to confirm the file grew (not truncated).

## Cron-Mode Fallback (When Tirith Blocks Terminal)

When running as an agent-based cron job, both `terminal()` and
`execute_code()` are blocked. The agent must work from the pre-run
script's output (in `## Script Output`) and use `write_file`/`patch`
to persist results.

**Workflow when pre-run script output exists:**

1. **Parse the pre-run stdout** — the script's table output is in
   `## Script Output` at session start. Extract peer status from the
   markdown table.
2. **Read the existing log** — `read_file("~/.hermes/peer-network/hmp-health.log")`
3. **Append new entry** — `patch` the file at the last unique anchor
   or `write_file` with the complete history (beware overwrite races).
4. **Report** — if any peer is unreachable, deliver the report.
   Otherwise return `[SILENT]`.

## Critical: Browser Does NOT Work for HMP Health Checks

The browser-based fallback (used for HTTP `/health` GET on port 8642)
is **not applicable** to HMP checks on port 8643. HMP endpoints are
**POST-only** — the browser only does GET navigations.

When you attempt `browser_navigate` to an HMP endpoint:

| Scenario | Browser Result | Root Cause |
|----------|---------------|------------|
| HMP server down (e.g., peer84) | `ERR_CONNECTION_REFUSED` | No service listening on :8643 |
| HMP server up but GET only (e.g., peer128) | `CDP command timed out: Page.navigate` | Server receives GET, hangs, does not respond (POST-only endpoint) |

**Neither result is diagnostically useful.** A browser timeout does NOT
mean the HMP endpoint is unreachable — it only means the server doesn't
speak HTTP GET on that path. The peer could be perfectly healthy but
simply reject browser navigation.

**The only reliable data source for HMP checks in cron mode is the
pre-run script output** (`## Script Output` at session start). The
pre-run script runs as a subprocess outside the agent sandbox and can
make real POST requests with HMP message payloads. Do NOT try to
verify or supplement HMP data with browser probes — they will either
fail (connection refused) or hang (POST-only timeout) without providing
useful information.

**`web_extract` (Firecrawl) also cannot reach HMP endpoints.** It blocks
all private/internal network addresses — returns `"Blocked: URL targets
a private or internal network address"`. This is a second dead-end for
HMP checks in cron mode beyond the browser's GET-only limitation.
No HTTP-based tool available to the agent can reach HMP port 8643 on
LAN peers; only the pre-run script (which runs outside the agent
sandbox) has the network access to make real POST requests.

## Poll Response Status Values (Complete)

The poll response status values form a spectrum from healthy to
unreachable:

| Status | Meaning | Operational Signal |
|--------|---------|-------------------|
| `delivered` | Message delivered to peer agent | Healthy — full HMP pipeline working |
| `working` | Agent processing the ping | Healthy — message routing functional |
| `pending` | Accepted but queued | **Acceptable** — HMP server alive, routing delay |
| `ok` | Ping completed | Healthy — full round-trip succeeded |
| `completed` | Message processed by HMP server, no agent ACK returned | **Degraded** — HMP server is alive and routed the message, but the target agent either didn't respond or the response didn't arrive back. The HMP messaging layer routed the message correctly; the peer agent may be busy, offline, or the ACK was lost. Marked 🔴 (red) in output. |
| `unreachable` | HMP server not contacted | **Failure** — peer's HMP service or network path down |

**Key operational insight:** A transition from `unreachable` to
`pending` or `completed` between consecutive runs represents
**improvement** — the HMP server has recovered and is again accepting
and tracking messages, even if delivery/ACK hasn't completed. Conversely,
a transition from any status to `unreachable` means the HMP service
became unreachable (peer shutdown, network issue, service restart).

Only `unreachable` triggers `all_ok = False`. The `completed` status is
marked 🔴 but represents a less severe problem — the HMP messaging layer
is operational but the target agent isn't fully responsive.

### Errno Translation — Connection Refused vs No Route to Host

When an HMP send fails with a `URLError`, the `errno` value reveals the
**layer** at which communication broke. This helps distinguish between
a peer that is online-but-not-listening and one that is completely
unreachable:

| Error | errno | Meaning | Network Layer | Diagnostic |
|-------|-------|---------|---------------|------------|
| `Connection refused` | 111 | Peer machine is alive but nothing is listening on :8643 | Transport (TCP) | HMP server process likely crashed or not running. Peer OS responded to initial TCP handshake with RST. **SSH into the peer and check `systemctl status hermes` or restart the HMP service.** |
| `No route to host` | 113 | Peer machine cannot be reached at all | Network (IP) | Peer is offline, NIC disconnected, VPN down, suspend/sleep, or firewall drops at network layer. **Check physical connectivity, power, suspend state, or VLAN/firewall config.** |

**Operational implications:**
- **111 → 113 transition means things got worse.** If a peer changes from
  `Connection refused` to `No route to host` between consecutive healthchecks,
  it has gone from "running but not serving HMP" to "completely unreachable."
  This can happen when a machine suspends, shuts down, or a network segment
  goes down.
- **113 → 111 transition means improvement.** The peer has reappeared on the
  network but the HMP service hasn't restarted yet. An SSH + systemctl restart
  sequence may be warranted.
- **Persistent 111** (same for hours) means the peer machine is on but its
  HMP service is dead. This is a maintenance target.
- **Persistent 113** (same for hours) means the peer is completely gone.
  Only physical/network intervention can fix it.

**Real-world example (2026-07-15):**
```
06:08  peer84 → Errno 111 Connection refused   ← raspberry alive, HMP down
11:21  peer84 → Errno 113 No route to host      ← raspberry went offline/suspend
20:47  peer84 → Errno 111 Connection refused   ← raspberry back on network, HMP still down
```
The peer went from "HMP service down but machine on" (111) to "machine completely
unreachable" (113), then back to "machine online but HMP still down" (111) ~9
hours later. The 113→111 transition is an improvement — the peer reappeared on
the network — but the HMP service never restarted, indicating it may need a
manual `systemctl restart hermes` or a restart-on-wake service. Likely causes:
suspend-to-RAM, power cycle overheating-triggered shutdown (common on Raspberry
Pi ARM64 with intermittent power), or network interface drop followed by
automatic recovery.

### Systemic All-Same-Error Detection

When **all monitored peers** report the **same error type** (e.g., both peer84
AND peer128 show `[Errno 111] Connection refused`), this is a qualitatively
different signal than isolated peer failures:

| Pattern | Signal | Likely Cause |
|---------|--------|-------------|
| One peer down, others OK | Isolated peer failure | That peer's HMP process crashed, peer suspended/rebooted |
| **All peers same error** | **Infrastructure-level issue** | Network change (subnet, gateway, firewall), orchestrator's own network stack issue, HMP service config change affecting routing |
| Mix of different errors | True multi-point failure | Independent problems — each peer needs separate diagnosis |

**Operational response when all peers show the same error:**

1. **Check orchestrator self-health first** — the orchestrator (peer70) itself
   may have a network issue. Run a local loopback check:
   - `browser_navigate("http://127.0.0.1:8642/health")` — is the orchestrator's
     own API server working?
   - `browser_navigate("http://127.0.0.1:8643/health")` — is the orchestrator's
     own HMP endpoint responding? (Note: this is a GET on port 8643 — may
     succeed for `/health` even if `/hmp/send` is POST-only.)
2. **Check the gateway status** — if all remote peers are down, the
   orchestrator's gateway might be in a degraded state. Read logs:
   `~/.hermes/logs/gateway.log`
3. **Report as a systemic alert** — phrase the report differently: not "peer84
   and peer128 are down" but "All HMP peers unreachable — possible network or
   orchestrator issue." Include the errno and a note that isolated failures
   were ruled out.
4. **Suppress if unchanged from previous run** — if all peers were also down
   with the same errno in the last run, and no peers recovered, go `[SILENT]`.
   A systemic alert that fires every hour with no change is spam.

**Real-world example (2026-07-16):** Both peer84 and peer128 showed
`[Errno 111] Connection refused` simultaneously. Cross-referencing with ARP
(`/proc/net/arp` → Flags `0x2` for both) and Hermes API health
(`browser_navigate` to port 8642 → both online) revealed that ONLY HMP
port 8643 was down on both peers — a systemic HMP service outage, not a
network or peer-machine failure. The correct report was: "Both peers alive
(L2 + HTTP API OK) but HMP service down on both — possible HMP plugin
misconfiguration or service restart needed on both peers."

## Test Output Table

```
🌐 HMP Healthcheck — 2026-07-15 01:53:56

| Peer | Invio | Stato HMP |
|---|---|---|
| peer84 | ✅  | 🟢 pending |
| peer128 | ✅ (via SSH) | 🔴 unreachable |
| peer70 | — | 🟢 orchestratore |

Stato: ⚠️ PROBLEMI RILEVATI (vedi sopra)
```

The output is deliberately simple — one table, one summary line.
Consistent formatting makes it easy to scan multiple entries in the
log and spot changes at a glance.

## When Pre-run Script Shows HMP Errors: ARP + Browser Cross-Reference Workflow

When the pre-run script's `## Script Output` shows HMP failures
(Connection refused, No route to host) on every peer, do NOT just
report the failure. Use a **three-layer** diagnostic to distinguish
"machine offline" from "machine alive, HMP service down":

| Layer | Tool | What it tells you |
|-------|------|-------------------|
| L2 (ARP) | `read_file("/proc/net/arp")` | Is the peer machine reachable on the LAN? Flags `0x2` = recently communicated. `0x0` = no response (offline). |
| L7 (Hermes API) | `browser_navigate("http://<peer_ip>:8642/health")` | Is the Hermes agent running on the peer? JSON `{"status":"ok","platform":"hermes-agent","version":"0.x.y"}` |
| L7 (HMP) | Pre-run script output (`## Script Output`) | Is HMP port 8643 serving? Only the pre-run script can POST — browser GET does not work for HMP. |

### Diagnostic Matrix

| ARP | Hermes API :8642 | HMP :8643 | Interpretation |
|-----|-----------------|-----------|----------------|
| 🟢 0x2 | 🟢 Online | 🔴 Conn refused | Machine alive, Hermes agent running, HMP plugin not configured/started. Needs `hermes plugins enable hmp`. |
| 🟢 0x2 | 🔴 Conn refused | 🔴 Conn refused | Machine alive (L2), but Hermes agent and HMP both down. Peer process not started. |
| 🔴 0x0 | 🔴 Conn refused | 🔴 No route to host | Machine offline/unreachable. Power/network/standby. |

### Concrete Worked Example (2026-07-16)

Pre-run output — both peers fail:
```
| peer84  | ❌  | 🔴 <urlopen error [Errno 111] Connection refused> |
| peer128 | ❌  | 🔴 <urlopen error [Errno 111] Connection refused> |
```

**Step 1 — ARP check** (`read_file("/proc/net/arp")`):
```
192.168.178.84   0x1  0x2  24:0a:64:1b:fd:67   *  wlan0   → 🟢 reachable
192.168.178.112  0x1  0x2  88:66:5a:4f:a5:3f   *  wlan0   → 🟢 reachable
```

**Step 2 — Browser /health check on Hermes API port:**
- `browser_navigate("http://192.168.178.84:8642/health")` → `{"status":"ok","platform":"hermes-agent","version":"0.16.0"}`
- `browser_navigate("http://192.168.178.112:8642/health")` → `{"status":"ok","platform":"hermes-agent"}`

**Conclusion:** Both peers are ACCESO with Hermes agent running. HMP port 8643 is specifically down — the HMP plugin isn't configured or the HMP service isn't running on those peers.

**Step 3 — Persist the richer diagnosis** to the log file (instead of the bare "Connection refused"):
```markdown
=== Interpretazione ===
- Entrambi i peer sono ACCESI e raggiungibili sulla LAN (ARP flags 0x2 = reachable).
- Entrambi hanno Hermes agent attivo su porta 8642 (API online).
- HMP (porta 8643) NON è attivo su nessuno dei due peer → servizio HMP non avviato.
- peer84: hermes-agent v0.16.0; peer128: hermes-agent (versione generica).
```

### When to Deliver vs Suppress

All three layers — ARP, Hermes API, HMP — are persistent-state checks.
Deliver a report only when something **changed**:
- A peer's ARP flags changed (0x2↔0x0) — L2 status changed
- A peer's Hermes API started/stopped responding — L7 status changed
- The errno changed (111↔113) — the nature of the failure changed
- A new peer appeared in the failure set or recovered
- 12+ hours of the same problem — daily summary heartbeat

If everything is identical to the previous run, go `[SILENT]`.

### Pitfall: ARP is ephemeral

`/proc/net/arp` shows peers that recently communicated. A peer that hasn't
exchanged packets in ~5-10 minutes may have Flags 0x0 even if online.
ARP 0x2 = confirmed reachable; ARP 0x0 ≠ definitively offline. Always
cross-reference with the Hermes API /health browser check.

## Pitfalls

- **Send-then-poll delay is fixed at 2s.** If the peer is under load,
  polling too early returns `"pending"` instead of `"delivered"`.
  Consider making the delay configurable per-peer or exponential.
- **SSH fallback requires key-based auth.** The cron agent has no
  interactive SSH session. Ensure `~/.ssh/config` has the right keys
  and `StrictHostKeyChecking=no` is set (or the host key is accepted
  ahead of time).
- **The script cannot be re-run in cron mode.** Tirith blocks all
  terminal calls. The pre-run script output is the sole data source
  for the agent session.
- **`replace_all=True` on `patch` with duplicate anchors.** Both the
  first and last log entries look identical, so `patch` with a common
  ending string matches both. Use enough surrounding context to make
  the anchor unique, or target only the file's final lines.
- **`patch` with fuzzy matching fails on 3+ structurally identical
  log entries.** When the HMP health log accumulates 3+ consecutive
  entries with the same structure (same peer names, same errors, same
  table format), `patch` finds N matches even when the `old_string`
  includes the unique timestamp line. The fuzzy matcher ignores the
  timestamp as a "minor difference" and matches the structural body N
  times, causing `patch` to refuse with "Found N matches."
  
  **The only reliable workaround is `write_file` with the full content:**
  1. `read_file("~/.hermes/peer-network/hmp-health.log")` to capture
     the current file
  2. Construct the new content as old_content + separator + new_entry
  3. `write_file` with the complete concatenated string
  
  This is safe when this cron job is the **only writer** to the file.
  
  **Alternative (not recommended):** `patch(replace_all=True)` — this
  replaces EVERY matching entry's content, corrupting all previous
  entries. Do not use `replace_all` for log appending.
  
  **Diagnostic indicator:** If patch keeps returning "Found N matches"
  after 2-3 attempts despite adding more context, switch to `write_file`
  immediately. Further patch attempts waste turn budget.
  
  **Real-world example (2026-07-16):** 3 consecutive HMP entries all
  showing peer84=❌ peer128=❌ with Errno 111. Every `old_string`
  ending in `| peer70 | — | 🟢 orchestratore |\n|Stato: ⚠️ PROBLEMI RILEVATI`
  matched 3 times. Including the timestamp `22:40:00` still matched 3
  times (fuzzy match ignored the timestamp). Final fix: `write_file`
  with the full 4-entry history composed from the `read_file` snapshot
  plus the new entry.