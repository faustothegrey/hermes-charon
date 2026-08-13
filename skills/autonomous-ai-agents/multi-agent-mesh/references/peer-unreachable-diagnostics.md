# Diagnosing an Unreachable Peer ("No route to host")

When a cron job or script fails with `[Errno 113] No route to host` (or
`curl exit 7`) against a peer, use this workflow to determine WHAT is down
and WHEN it went down. Example case: 2026-08-02 — `research_queue.py`
failed fetching from peer84 (N56VV); diagnosis: peer84 off the network for
~22h, peer105 also down, peer106 healthy.

## Step 1 — Classify the failure (host down vs service down)

| Symptom | Meaning |
|---------|---------|
| `No route to host` / `Errno 113` / `curl exit 7` + **ARP FAILED** | Machine powered off, asleep, or disconnected from WiFi — unreachable at L2 |
| `Connection refused` / `curl exit 7` but **ARP reachable** | Host is up but the service (Hermes API :8642 / HMP :18643) is not listening |
| Timeout / no response but ARP reachable | Host up, service slow or hung (see sequential-probing pattern in SKILL.md) |

**Critical: hostnames don't resolve.** `ping peer84` or `ping N56VV` fails
with "Name or service not known" — there are no /etc/hosts entries for
peers. Always use the IPs from `~/.hermes/scripts/peers_config.json`.

```bash
# 1. Ping the IP directly
ping -c 2 -W 3 192.168.178.84

# 2. ARP state — the decisive check
ip neigh show | grep 192.168.178.84
#   FAILED / incomplete  → no MAC resolution → host truly off the network
#   REACHABLE / STALE    → host answered recently → look at services instead

# 3. LAN sweep to confirm absence and see what IS up
#    (parallel ping, NOT shell backgrounding — use ThreadPoolExecutor)
```

## Step 2 — Determine WHEN it went down (timeline reconstruction)

Three independent sources; cross-check them:

1. **Cron job output history** — `~/.hermes/cron/output/<job_id>/` holds one
   `.md` per run. Classify OK vs FAIL:
   ```bash
   cd ~/.hermes/cron/output/01602cb5c3ba && for f in $(ls | sort); do
     grep -q "Script Error" "$f" && echo "FAIL $f" || echo "OK   $f"; done
   ```
   The boundary (last OK → first FAIL) brackets the outage start. In the
   2026-08-02 case: last OK 07-31 00:01, first FAIL 07-31 07:01.

2. **hmp-healthcheck.log quirk** — `~/.hermes/logs/hmp-healthcheck.log`
   (from `hmp-healthcheck.sh`) **omits peers that don't answer ping**; the
   log line only lists reachable peers. So a peer *disappearing* from the
   lines = it stopped responding. Caveat: lines carry only `HH:MM`, no
   date — use the cron outputs to anchor which day. Note the last entry is
   `[00:00] peer128=DOWN peer106=OK` with NO peer84 → already down at
   midnight.

3. **HMP ping round output** — `~/.hermes/cron/output/3ac4bbef740c/`
   (`hmp-ping-round.py`, every 10 min, port 18643). Shows
   `→ peer84 (...)... ❌ curl exit 7` per down peer. Retains ~50 files
   (~8h of history), so it confirms "down for at least N hours" but not
   long outages.

## Step 3 — Report

Use a per-peer table: ping / ARP / HMP :18643 / API :8642. State the
root cause explicitly as **L2 unreachable (powered off / WiFi dropped) vs
service down**, since the fix differs (wake the machine vs restart gateway).
Include: outage window, impact (which pipeline is blocked and why — e.g.
"the queue file lives on peer84, so nothing can be dispatched"), and
physical actions (wake/reconnect peer, check peer105's power, resilience
options like a local queue mirror).

## Gotchas

- `execute_code`'s `terminal()` rejects shell `&` backgrounding — do the
  LAN sweep with `concurrent.futures.ThreadPoolExecutor` + `subprocess.run`,
  not `ping ... &`.
- A peer may be down on **one service** but not another — check BOTH
  :8642 (Hermes API) and :18643 (HMP gateway). peer106 answered ping while
  peers 84/105 were fully gone.
- `peers_config.json` can drift from `peer-mesh.yaml` (e.g. peer128 listed
  at .112 in one, .128 in another). Trust `peers_config.json` for script
  targets; flag drift in the report.
- Don't wake peers with `iw` power-save tricks — the fix is physical
  (power on / reconnect to FRITZ!Box WiFi). WoL or a local queue mirror are
  the durable resilience options.
