# Canary Upgrade Protocol

Upgrade Hermes Agent version across the cluster with a **canary-first** approach
to detect issues before touching the coordinator or other critical peers.

## Phase 0: Evaluate

Before any upgrade, collect and report to the user:

1. **Current versions** of every peer (via HMP agent-card, API /health, or SSH)
2. **Latest version changelog** — relevant features, performance gains, breaking changes
3. **Per-peer risk assessment:**
   - Install method (git clone with local commits vs pip)
   - Plugin compatibility (hmp, capability-reuse versions)
   - Config preservation (approvals.mode, gateway settings)
4. **Structured pros/cons table** to the user before they greenlight

## Phase 1: Canary Selection

**Rule:** never upgrade the coordinator (peer70) first. Use a non-critical peer:

| Priority | Peer | Reason |
|----------|------|--------|
| 1st | peer58 | Sidecar/failover node, non-critical |
| 2nd | peer84 | Idle-capable, similar arch to coordinator |
| 3rd | peer106 | Research peer, can pause tasks |
| Last | peer70 | Coordinator — critical infrastructure |

## Phase 2: Ask → Volunteer Confirmation → Autonomous Execution

**Step A — Ask if the peer volunteers.** Before instructing the peer to
execute, send a first HMP message asking if they accept the canary role
and if they have any conditions.

```bash
curl -s -X POST http://<canary-ip>:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text",
    "text": "Ciao <peer>, sei disposto a fare da canarino per l'\''upgrade a v0.19.0? Rispondi yes/no e eventuali dubbi.",
    "sender": "peer106"
  }'
```

Wait for the response (poll `/hmp/poll/{message_id}`). The peer may
state conditions (e.g. "skip heavy loads during canary", "backup first",
"avoid upgrade during peak hours"). Accept or negotiate, then proceed.

**Step B — Instruct autonomous execution.** Once confirmed, send the
go-ahead message:

```bash
curl -s -X POST http://<canary-ip>:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text",
    "text": "Ciao <peer>! Procedi da solo in autonomia: fai backup, esegui upgrade a v0.19.0, verifica tutto (HMP health, gateway, plugin, cron), e riferisci esito. Interveniamo solo se problemi.",
    "sender": "peer106"
  }'
```

**What the canary peer should do (autonomously):**
1. Backup: `~/.hermes/` → `~/.hermes/canary-<version>-<timestamp>/`
2. Run `git fetch --tags origin` (or `git remote update --prune`)
3. Checkout the target tag (e.g. `v2026.7.20`)
4. Run `pip install -e .` or rebuild from source
5. Restart gateway from **external shell** (see pitfall below)
6. Verify: health endpoints, plugin loading, config preservation

**Poll for response** and report to user. Only SSH-intervene on failure.

### Monitoring Long git Operations via SSH

While the HMP poll shows `status: delivering` or `status: working` with no
response_text for several minutes, the peer may be stuck on a long git
fetch. Check via SSH:

```bash
sshpass -p '<password>' ssh <user>@<peer-ip> 'ps aux | grep -E "git|pip" | grep -v grep'
```

If `git index-pack --stdin --fix-thin` is running with a large pack
(e.g. `--pack_header=2,173626`), the fetch is in progress — it will take
1-5 minutes depending on connection speed.

If the HMP poll shows `status: delivering` for >5 minutes with no
response and no git/pip processes, the peer's agent may be waiting for
user input or stuck. Intervene manually.

### Real-world Timings

| Peer | Version jump | Git fetch time | Autonomy | Intervention needed |
|------|-------------|----------------|----------|-------------------|
| peer58 | v0.18.2 → v0.19.0 | ~4 min (173k objects) | Full — agent did everything | No |
| peer84 | v0.16.0 → v0.19.0 | ~3 min (88k shallow) | Partial — gateway restart killed agent | Yes — external SSH restart |

## Phase 3: Verification Checklist

After the canary reports success (or you check via SSH), verify *every* item:

| Check | Command |
|-------|---------|
| Version | `hermes --version` → show v0.19.0+ |
| HMP health | `curl :18643/hmp/health` → status ok |
| Agent-card | `curl :18643/hmp/agent-card` → all endpoints |
| HMP bidir | Send ping via HMP, wait for "OK" response |
| Plugin list | `ls ~/.hermes/plugins/` → hmp, capability-reuse present |
| Plugin data | Check registry mirror, sidecar state for heartbeats |
| Config preserved | `hermes config get approvals.mode` → `off` |
| Gateway status | `systemctl --user status hermes-gateway` → active |
| Cron intact | `hermes cron list` or check jobs.json |

## Phase 4: Escalate

After the canary passes for 24-48 hours without issues:

1. Upgrade **idle peers** (peer84 if not already done, peer106)
2. Upgrade **coordinator** (peer70) — last, after full confidence
3. Upgrade **offline/flaky peers** (peer105, peer128) when they reconnect

## Known Pitfalls

### Gateway restart kills itself from within

**Symptom:** peer84 agent started upgrade via `systemctl restart hermes-gateway`
from within the gateway's terminal. Result: SIGKILL of the entire gateway
process tree, upgrade halted midway, peer84 stuck on v0.16.0 with crashed gateway.

**Fix:** restart the gateway from an **external SSH session**, not from within
the gateway's own terminal/agent:
```bash
ssh peer84 systemctl --user start hermes-gateway
```

**Gateway stuck in "deactivating" with hanging children:** after pip
install (or a partial agent-initiated upgrade), `systemctl restart` may
stall because the old gateway has orphaned child processes (bash, pip,
hermes doctor) blocking shutdown. Fix from an external shell:

```bash
systemctl --user kill -s KILL hermes-gateway
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway
```

To avoid: when asking a peer to upgrade autonomously, include in the
instructions that gateway restart must use an external mechanism (cron job
or separate SSH call), not `systemctl` from within the agent's terminal.

### git fetch may timeout on slow connections

Hermes repo is large (173k+ pack objects on a full fetch). On peers with
slow internet (RPi, WiFi), `git fetch --tags origin` can timeout.

**Workaround:** use `git fetch origin main --depth=50` for a shallow check,
or `pip install -U hermes-agent` instead of git-based update.

### peer versions before v0.17.0 have different API

**Symptom:** `POST /v1/chat/completions` returns `400 Model parameter is required`
on v0.16.0. Use `/v1/runs` with `input` field instead.

**Fix:** when communicating with v0.16.0 peers via API, use:
```bash
curl -X POST http://peer:8642/v1/runs \
  -H "Authorization: Bearer <key>" \
  -d '{"input":"instruction","model":"hermes-agent"}'
```
