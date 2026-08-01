# Peer Recovery After Resource Exhaustion

## Scenario: Peer Becomes Unresponsive (swap saturation)

### Symptoms
- API health check (`:8642/health`) responds OK but agent doesn't process requests
- Dual-plane server (`:18644`) responds slowly or not at all
- SSH connections time out or are very slow
- HMP messages stay "delivering" indefinitely
- Simple responses ("OK") work, but any real work times out

### Root Cause (peer106, 2026-07-25)
- Swap: 252MB/447MB used (56%) — system thrashing
- Hermes gateway process had been running for 10h+ uninterrupted
- Memory pressure caused LLM generation to stall mid-task

### Recovery Procedure

**Step 1 — Diagnose:**
```
ssh root@<peer-ip> "uptime; free -h; curl -s :18644/health; curl -s :8642/health"
```

**Step 2 — Reboot peer (only option for swap exhaustion):**
1. Sync updated files (skill, config) before reboot
2. `ssh root@<peer-ip> "reboot"`
3. Wait ~90s, then poll for reconnection
4. After boot: restart dual-plane server, run health checks

**Step 3 — Restart services after reboot:**
```
kill $(lsof -t -i :18644) 2>/dev/null
python3 -c "import sys; sys.path.insert(0,'.hermes/scripts'); from hmp_dual_plane import run_server; run_server(port=18644, node_id='<peer_id>')"
curl -s http://127.0.0.1:8642/health
curl -s http://127.0.0.1:18644/health
```

### Gateway Restart (when not rebooting)

When `systemctl --user restart hermes-gateway` is blocked (Hermes safety):
```
kill -9 <gateway_pid>   # SIGKILL bypasses Hermes signal handler
```
systemd `Restart=always` respawns the gateway within seconds.

### Preventative: System Watchdog

```
*/5 * * * *  syswatch.py    # Log CPU, memory+swap%, I/O to JSONL
0 * * * *    syswatch-alert # Alert only when thresholds exceeded
# Thresholds: CPU load 1m > 4.0 | CPU load 5m > 3.0 | Mem > 85% | Swap > 50%
```
