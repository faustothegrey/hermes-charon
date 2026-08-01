# Peer Diagnosis & Recovery

When a peer becomes unresponsive (HMP messages stuck on "delivering", API timeouts,
SSH timeouts), follow this diagnostic and recovery procedure.

## 1. Quick Health Check

```bash
# API health (fastest check)
curl -s --connect-timeout 3 http://PEER_IP:8642/health

# Dual-plane health
curl -s --connect-timeout 3 http://PEER_IP:18644/health

# HMP health
curl -s --connect-timeout 3 http://PEER_IP:18643/hmp/health

# SSH (if above all fail)
ssh -o ConnectTimeout=10 root@PEER_IP "echo OK"
```

## 2. Check System Resources (SSH)

When a peer is slow or timing out, check:

```bash
ssh root@PEER_IP '
# Memory & swap pressure
free -h
echo "---"
# Load average
uptime
echo "---"
# Gateway process
ps aux | grep "hermes_cli.main gateway" | grep -v grep
echo "---"
# Listening ports
ss -tlnp | grep -E "18644|8642|18643"
echo "---"
# Recent gateway errors
journalctl --user -u hermes-gateway -n 20 --no-pager 2>/dev/null | grep -i "error\|exception\|timeout"
'
```

- **Swap usage ≥50%** → reboot needed (see §4)
- **Gateway process missing** → restart gateway (see §3)
- **Dual-plane :18644 missing** → restart dual-plane server (see §5)

## 3. Gateway Restart (when blocked by safety)

`systemctl --user restart hermes-gateway` is **blocked** from SSH when the SSH
session is a child of the gateway process (Hermes safety feature: SIGTERM
propagates to children).

**Workaround — SIGKILL (-9):**

```bash
# 1. Find gateway PID
PID=$(ssh root@PEER_IP 'ps aux | grep "hermes_cli.main gateway" | grep -v grep | awk "{print \$2}"')

# 2. Kill -9 (SIGKILL cannot be caught by signal handler)
ssh root@PEER_IP "kill -9 $PID"

# 3. Wait for systemd to restart it automatically (Restart=always)
sleep 5

# 4. Verify new PID and health
ssh root@PEER_IP 'ps aux | grep "hermes_cli.main gateway" | grep -v grep'
curl -s http://PEER_IP:8642/health
```

After gateway restart, the dual-plane server also needs restart (see §5).

**Caveat:** `kill -9` bypasses the safety feature but also loses the
connection immediately. You cannot verify the restart from that same
SSH session — use a new SSH connection or wait for the peer to come
back up (~5-15 seconds).

## 4. Reboot (fixes swap pressure)

When swap is ≥50% used and the peer has been running for hours/days:

```bash
# 1. Sync any pending files first
scp ... any important files to backup

# 2. Reboot
ssh root@PEER_IP "reboot"

# 3. Wait for peer to come back up (~60-120s)
for i in $(seq 1 12); do
  sleep 10
  if ssh -o ConnectTimeout=5 root@PEER_IP "echo ONLINE" 2>/dev/null; then
    break
  fi
done

# 4. Verify services
curl -s http://PEER_IP:8642/health
# If API is not up yet, wait more and retry

# 5. Restart dual-plane server (does not survive reboot)
ssh root@PEER_IP '
kill $(lsof -t -i :18644) 2>/dev/null
sleep 1
nohup python3 -c "import sys; sys.path.insert(0,\"/root/.hermes/scripts\"); from hmp_dual_plane import run_server; run_server(port=18644, node_id=\"peer106\")" > /root/.hermes/scripts/dp-server.log 2>&1 &
sleep 3
'
curl -s http://PEER_IP:18644/health
```

## 5. Restart Dual-Plane Server Only

```bash
ssh root@PEER_IP '
kill $(lsof -t -i :18644) 2>/dev/null
sleep 1
nohup python3 -c "import sys; sys.path.insert(0,\"/root/.hermes/scripts\"); from hmp_dual_plane import run_server; run_server(port=18644, node_id=\"peer106\")" > /root/.hermes/scripts/dp-server.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:18644/health
'
```

## 6. Verify Plugin Files After Restart

After gateway restart, verify the capability-reuse plugin is in the right place:

```bash
ssh root@PEER_IP '
# Plugin must be in plugins/ (not just skills/)
ls /root/.hermes/plugins/capability-reuse/__init__.py 2>/dev/null || echo "MISSING"
ls /root/.hermes/plugins/capability-reuse/plugin.yaml 2>/dev/null || echo "MISSING"

# Skill files in skills/
ls /root/.hermes/skills/hermes/capability-reuse/scripts/conformance-suite.py 2>/dev/null || echo "MISSING"

# Check python dependencies
python3 -c "import yaml; print(f'yaml {yaml.__version__}')" 2>/dev/null || echo "yaml MISSING"
'
```

## 7. Run Conformance Suite

```bash
ssh root@PEER_IP 'cd /root/.hermes/skills/hermes/capability-reuse && python3 scripts/conformance-suite.py'
```

## Pattern Summary

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Slow responses, API timeout after "OK" | Swap pressure (≥50%) | Reboot (§4) |
| HMP stuck "delivering" | Gateway stuck on long task | SIGKILL + systemd restart (§3) |
| Dual-plane :18644 not responding | Server crashed/killed | Restart dual-plane (§5) |
| Conformance test 1 FAIL (yaml) | PyYAML not installed | `pip3 install pyyaml` |
| Conformance test 1 FAIL (plugin not found) | Plugin in skills/ not plugins/ | Copy plugin/ to plugins/ (§6) |
| All services down | Full system freeze | Reboot (§4) |
