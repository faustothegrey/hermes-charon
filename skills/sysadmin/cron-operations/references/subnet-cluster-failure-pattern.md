# Subnet/Cluster-Level Failure Detection (Backup Monitor)

## The Gap

The backup monitor reference documents two failure extremes:

| Scope | Pattern | Documented in |
|---|---|---|
| **Single peer** | One peer changes error type or reachability | `backup-monitor-timeout-pattern.md` → "Per-Peer Delta Detection" |
| **Fleet-wide** | All peers fail identically | `backup-monitor-timeout-pattern.md` → "All Peers Unreachable (Systemic Failure)" |

**What's missing: cluster-level failures** — a **subset** of peers (typically
on the same subnet, hardware generation, or role) simultaneously transitions
state while the rest of the fleet is unaffected.

## The Pattern

A cluster-level failure has three signals:

1. **Multiple peers change state in the same run** (not just one)
2. **Those peers share a common property** (same subnet, same hardware
   generation, same power circuit, same service)
3. **The remaining peers stay unchanged** — the monitoring host is still
   reaching at least some peers, so this is NOT a fleet-wide failure

### Concrete Example (This Session — 2026-07-20 22:46)

```
22:02 CEST:   peer105=never-ran (🟢 reachable)   peer106=never-ran (🟢 reachable)
22:46 CEST:   peer105=error/timed-out (🔴)       peer106=error/timed-out (🔴)

Unchanged:    peer128=offline (🔴, chronic), peer84=error/timed-out (🔴, chronic)
```

**Signal 1:** Two peers changed in the same run.
**Signal 2:** Both are Raspberry Pis (RPi 3B + ARMv8) on the same LAN subnet.
**Signal 3:** peer128 and peer84 unchanged (different subnets/hardware).

### How to Detect

```python
# After building current_peers list and comparing with previous run:
from collections import Counter

# Group peers by a shared property (inferred from label or peer name suffix)
def group_by_hardware(peers):
    """Group peers by hardware type for cluster analysis."""
    groups = {
        "rpi":     ["peer105", "peer106"],  # Raspberry Pis
        "laptop":  ["peer84"],               # N56VV laptop
        "desktop": ["peer128"],              # Mac
    }
    return groups

# Find cluster-level changes
newly_down = [p for p in current_peers
              if p.get("esito") in ("error", "offline")
              and prev_peers.get(p["peer"], {}).get("reachable", False)]

# Count by cluster
cluster_counts = Counter()
for p in newly_down:
    for cluster, members in group_by_hardware(peers).items():
        if p["peer"] in members:
            cluster_counts[cluster] += 1

# Signal: all members of a cluster changed simultaneously
at_risk_clusters = {c: n for c, n in cluster_counts.items()
                    if n == len(group_by_hardware(peers).get(c, []))
                    and n > 1}

if at_risk_clusters:
    print(f"CLUSTER EVENT: {len(newly_down)} peers went down simultaneously")
    for cluster, count in at_risk_clusters.items():
        print(f"  • All members of {cluster} are now down ({count} peers)")
```

### Classification

| Pattern | Likely cause | Response |
|---|---|---|
| **All RPis down** (peer105+106) | Power outage on Pi circuit, SD card failures on both, switch port flapping for that VLAN/subnet | Check power strip / UPS feeding the Pis. Check per-Pi SSH health. |
| **All laptops down** (peer84 only = N56VV) | Single machine — treat as single-peer failure. N56VV has scheduled downtime 11:00-17:00 UTC+2. | Compare against known availability window. |
| **Two peers on same subnet both timeout** | Network switch port, cable, or subnet-level issue | Check the switch port status, cable connections, subnet VLAN config. |
| **All peers on same subnet, mixed error types** (e.g., 1× "No route to host" + rest "timed out") | **Sequential timeout cascade from fast-fail -> slow-fail** (see `backup-monitor-timeout-pattern.md` → "Fast-Fail vs. Slow-Fail"). The first peer failed fast at ICMP level; later peers each consumed the full per-peer timeout. The monitoring host IS online (it got ICMP responses AND made TCP attempts), but individual peers have different service states. | Distinguish cascade from genuine failure: if any later peer returned "No route to host" (not "timed out"), that's a genuine per-peer routing failure (script had budget for ICMP response). If all later peers are "timed out" uniformly, the cascade consumed the budget. Check each peer's port 8642 directly. |

### Distinction from Fleet-Wide Failure

| Signal | Cluster-level | Fleet-wide |
|---|---|---|
| How many peers changed | Subset (e.g., 2/4) | All (4/4) |
| Unchanged peers | ✅ Some peers still reachable | ❌ None reachable |
| Error diversity | May vary by cluster | Same error across all peers |
| Monitoring host role | Host is fine (reaching some peers) | Host-side issue likely |

### Distinction from Independent Single-Peer Failures

| Signal | Cluster-level | N independent failures |
|---|---|---|
| Timestamp correlation | All changed in the same run | Would be spread across runs |
| Peer relationship | Share subnet/hardware/role | Random subset |
| Previous pattern | Both were reachable → both unreachable | Gradual attrition |

### Root Cause Analysis (from this session)

The 22:46 transition of both peer105+106 from `never-ran` (reachable) to `error`
(timed out) has these possible causes, ranked by likelihood:

1. **Power-cycle of the Pi cluster** — Both Pis on a shared power strip/UPS.
   If someone reset the strip, both went offline simultaneously.
2. **SD card failure on both** — Unlikely but possible if they share the same
   brand/batch of SD cards. Check `dmesg` for I/O errors.
3. **Switch port flapping** — If both Pis connect through the same network
   switch, a switch glitch drops both. Check `ip link` on the monitoring host
   for carrier transitions.
4. **Monitoring script backlog** — Sequential timeouts cascade: if peer84
   (queried first) took 30s, peer105 and peer106 would get shorter effective
   timeouts in the remaining 90s budget. The cascade causes them to time out
   even if they're actually reachable. This is the most likely explanation
   given the pre-run script's sequential design.

### Mitigation

- **Parallelize queries** — use `ThreadPoolExecutor` so Pi cluster queries
  fire concurrently, not sequentially. A slow peer84 request won't starve
  the Pi cluster's timeout budget.
- **Add per-subnet monitoring** — if the Pi cluster has its own health
  endpoint, check it separately from the laptop/desktop peers.
- **Log monitoring-host metrics** — include `loadavg`, `memory`, and
  `uptime` from the monitoring host alongside peer status, so you can
  distinguish "peers went down" from "monitoring host is overloaded."
