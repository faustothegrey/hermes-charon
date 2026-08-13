# Onboard a Full Hermes Agent Peer into the HMP Network

Procedura per aggiungere un nuovo peer con **Hermes Agent già installato**
ma gateway/HMP non ancora attivi. Dopo l'onboarding, il peer parlerà HMP
su `:18643` e sarà registrato nel registry di peer70.

## Flow overview

```
Verify reachability → Port scan → SSH key setup → SSH in → SCP plugin files
→ Edit config.yaml → Clear __pycache__ → Restart gateway → Verify HMP
→ Register in registry → Test send+poll → Update peer tables
```

## Step-by-step (verified on peer138 onboarding 2026-07-27)

### 1. Find the peer's IP

```bash
arp -n | grep -i '\.138\b'
ping -c2 -W2 192.168.178.138
```

**Never assume IP = peer number.** peer128 is at .112, not .128. Always use ARP.

### 2. Port scan (from peer70)

```bash
for port in 22 80 443 18643 8642 18644 8080; do
  timeout 2 bash -c "echo > /dev/tcp/192.168.178.138/$port" 2>/dev/null \
    && echo ":${port} OPEN" || echo ":${port} CLOSED"
done
```

Typical state for a fresh Hermes install: only **SSH (22)** open. HMP (18643)
and API (8642) need to be configured.

### 3. SSH key setup

New peers don't have the coordinator's SSH key. The user must add it to
`/root/.ssh/authorized_keys` on the target peer:

```bash
# On the NEW peer's console, as root:
echo 'ssh-rsa AAAAB3NzaC1yc2EAAAA... fausto@domotz.com' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

**Key:** `fausto@domotz.com` (see `~/.ssh/id_rsa.pub` on peer70).
Login as **root** on RPi/DietPi peers (they use system-wide systemd, not `--user`).

**⚠️ Not always root/systemd-system (peer141/Stella, 2026-08-13):** fresh
Hermes installs on RPi may run as user `fausto` with **systemd --user**
(`systemctl --user restart hermes-gateway.service`, home `/home/fausto`,
`~/.config/systemd/user/hermes-gateway.service`). Check first:
`ps aux | grep 'hermes_cli.main gateway'` → shows the user; `ls ~/.config/systemd/user/`
→ shows user-units. Use the SAME ssh user the gateway runs as
(peer141 = `fausto@192.168.178.141`, hostname Stella, Hermes v0.20.0).

**⚠️ Variant — fresh Hermes install as a normal user (peer141/Stella):** not
all new peers run as root. A fresh `hermes setup` on RPi/Debian can live
under `/home/fausto/.hermes` with **systemd `--user`** (`hermes-gateway.service`
in `~/.config/systemd/user/`, `enabled`). Detect before assuming root:
`ls ~/.hermes`, `systemctl --user list-unit-files | grep -i hermes`,
`ps aux | grep hermes_cli.main gateway` (user column). If user-mode: SCP to
`fausto@` not `root@`, restart with `systemctl --user restart hermes-gateway.service`,
and use `/home/fausto/.hermes/...` paths in config (database_path, .env).
The gateway process user tells you the home dir — peer141 ran as `fausto`
with PID in `ss -tlnp | grep hermes`.

After setup, verify from peer70:
```bash
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
  root@192.168.178.138 "echo 'SSH OK'; uname -a; hermes --version"
```

### 4. Check peer state

```bash
ssh root@192.168.178.138 "
  hermes --version
  hermes status
  ls ~/.hermes/config.yaml
  grep -c 'plugins:' ~/.hermes/config.yaml
  systemctl is-active hermes-gateway
  ss -tlnp | grep hermes
"
```

**Key checks:**
- Hermes installed and version ≥ 0.19 ✓
- Gateway service active (system-wide systemd, not `--user`) ✓
- HMP plugin absent (`ls ~/.hermes/plugins/hmp/` fails) → needs installation
- No `plugins:` section in config.yaml → needs config update

### 5. Install HMP plugin via SCP

**Do NOT use `hermes plugins install hmp`** — that command may not exist
on all versions. Instead, SCP the 4 plugin files directly from peer70:

```bash
ssh root@192.168.178.138 "mkdir -p ~/.hermes/plugins/hmp/ ~/.hermes/data/hmp_gateway_plugin/"

scp ~/.hermes/plugins/hmp/__init__.py  root@192.168.178.138:~/.hermes/plugins/hmp/__init__.py
scp ~/.hermes/plugins/hmp/adapter.py   root@192.168.178.138:~/.hermes/plugins/hmp/adapter.py
scp ~/.hermes/plugins/hmp/core.py      root@192.168.178.138:~/.hermes/plugins/hmp/core.py
scp ~/.hermes/plugins/hmp/plugin.yaml  root@192.168.178.138:~/.hermes/plugins/hmp/plugin.yaml
```

### 5b. Copy the hermes-hmp skill to the new peer (full peers only)

A full Hermes peer must also HAVE the protocol skill locally — the user
explicitly checks "hmp skill active". SCP the whole skill directory:

```bash
scp -qr ~/.hermes/skills/software-development/hermes-hmp \
  fausto@192.168.178.XXX:~/.hermes/skills/software-development/
```

Then have the peer PROVE it read the skill (not just that the files exist):
in the welcome message (step 20) ask it to run `skill_view(name='hermes-hmp')`
and confirm the protocol version. Files present ≠ skill loaded — the
notification-vs-alignment rule applies to onboarding too. Verified on
peer141: the peer answered with the full protocol summary only after being
asked to load it.

### 6. Add plugin + HMP config to config.yaml

Append to the peer's `~/.hermes/config.yaml`:

```yaml
# ── Plugins ─────────────────────────────────────────────────────────
plugins:
  enabled:
    - hmp
  disabled: []

# ── Gateway ─────────────────────────────────────────────────────────
gateway:
  enabled: true
  platforms:
    api_server:
      enabled: true
      extra:
        host: 0.0.0.0
        port: 8642

# ── HMP Platform ────────────────────────────────────────────────────
platforms:
  hmp:
    enabled: true
    extra:
      host: 0.0.0.0
      port: 18643
      node_id: peer138
      database_path: /root/.hermes/data/hmp_gateway_plugin/messages.db
      allow_all_peers: true
      request_timeout_seconds: 900
hmp:
  enabled: true
  host: 0.0.0.0
  port: 18643
  node_id: peer138
  database_path: /root/.hermes/data/hmp_gateway_plugin/messages.db
  allow_all_peers: true
  request_timeout_seconds: 900
```

Replace `peer138` and paths with the actual peer ID/IP.

**⚠️ Hermes v0.20.0+ (2026.8+): api_server needs `API_SERVER_KEY`.** Without
it the gateway logs `[Api_Server] Refusing to start: API_SERVER_KEY is
required for the API server, including loopback-only binds on 0.0.0.0.` and
`:8642` never listens. Generate one and append to the peer's `~/.hermes/.env`
(before restarting the gateway):

```bash
KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ssh fausto@<peer> "grep -q API_SERVER_KEY ~/.hermes/.env || echo API_SERVER_KEY=$KEY >> ~/.hermes/.env"
```

Verify with `curl :8642/health` → `{"status":"ok","platform":"hermes-agent","version":...}`.

**Safer than sed — temp-file append:** write the config block locally, SCP
it, then `cat /tmp/hmp-append.yaml >> ~/.hermes/config.yaml` on the peer.
Verify YAML parses before restarting:
`python3 -c "import yaml; print(yaml.safe_load(open('/home/fausto/.hermes/config.yaml'))['hmp'])"`
This avoids the sed `enabled:`-matches-everything corruption pitfall entirely.

### 6b. API_SERVER_KEY required on Hermes v0.20.0+ (verified peer141, 2026-08-13)

Hermes v0.20.0+ refuses to start the `api_server` platform (:8642) without
`API_SERVER_KEY`, even for loopback/0.0.0.0 binds:

```
ERROR gateway.platforms.api_server: [Api_Server] Refusing to start:
API_SERVER_KEY is required for the API server, including loopback-only binds on 0.0.0.0.
```

**Symptom:** `:18643/health` OK, but `:8642` dead — the API plane (dual-plane
fallback, agent sessions) never comes up. peer70 keeps its key in
`~/.hermes/.env` (`API_SERVER_KEY=...`). The onboarding config in step 6 does
NOT include it, so a fresh v0.20.0 peer will silently lack :8642.

**Fix on the peer** (as the gateway user):

```bash
KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "API_SERVER_KEY=$KEY" >> ~/.hermes/.env
systemctl --user restart hermes-gateway.service   # or systemctl restart for root/system-wide
```

Verify both planes after restart: `curl :18643/health` AND `curl :8642/health`
→ both must return JSON (api_server: `{"status":"ok","platform":"hermes-agent",...}`).

### 7. Clear __pycache__ and restart gateway

```bash
ssh root@192.168.178.138 "
  find ~/.hermes/plugins/hmp -name '__pycache__' -type d -exec rm -rf {} \; 2>/dev/null
  find ~/.hermes/plugins/hmp -name '*.pyc' -delete 2>/dev/null
  touch ~/.hermes/plugins/hmp/*.py
  systemctl restart hermes-gateway.service
  sleep 5
  systemctl is-active hermes-gateway.service
"
```

**⚠️ Pitfall: Gateway crash on first restart with new config.** The first
`systemctl restart` may fail (exit status 1) because the old gateway process
dies and the new one has issues loading the plugin. If this happens:

```bash
ssh root@192.168.178.138 "
  systemctl reset-failed hermes-gateway.service
  systemctl restart hermes-gateway.service
  sleep 5
  systemctl is-active hermes-gateway.service
"
```

The gateway may also need 5-10s to fully start listening. Use a polling loop
from peer70 if `curl` fails immediately after restart.

**⚠️ First start after plugin install is SLOW on RPi (15-30s+):** the gateway
process shows `active` but `ss -tln` has no `:18643`/`:8642` listener for a
while (bytecode compilation, plugin import). Do NOT declare failure on the
first curl — poll:

```bash
for i in $(seq 1 15); do
  curl -sf --connect-timeout 2 http://192.168.178.141:18643/health && break
  sleep 2
done
```

**⚠️ journalctl may be EMPTY on user-mode installs:** `journalctl --user -u
hermes-gateway.service` can return "No journal files were found" (user
journal not persisted). Read `~/.hermes/logs/gateway.log` on the peer
instead — it carries the platform start/error lines (including the
API_SERVER_KEY refusal and the "Gateway running with N platform(s)" line).

### 8. Verify HMP endpoints

```bash
curl -s --connect-timeout 3 http://192.168.178.138:18643/health
curl -s --connect-timeout 3 http://192.168.178.138:18643/hmp/agent-card
curl -s --connect-timeout 3 http://192.168.178.138:18643/hmp/health
```

Expected output:
- `/health` → `{"status":"ok","service":"hmp-gateway","gateway_adapter":true,"node_id":"peer138",...}`
- `/hmp/agent-card` → shows `version: "0.1.3"` and all 6 endpoints

### 9. Test HMP send+poll

```bash
MSGID="test_$(date +%s%N)"
curl -s -X POST http://192.168.178.138:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d "{\"hmp_version\":\"1.0\",\"message_id\":\"${MSGID}\",\"from\":\"peer70\",\"to\":\"peer138\",\"type\":\"request\",\"timeout\":60,\"payload\":{\"text\":\"Ciao! Rispondi con OK.\"}}"

for i in $(seq 1 20); do
  sleep 3
  data=$(curl -s http://192.168.178.138:18643/hmp/poll/${MSGID})
  status=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "[${i}x3s] $status"
  if [ "$status" = "completed" ]; then
    echo "RESPONSE:" 
    echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_text',''))"
    break
  fi
  if [ "$status" = "failed" ]; then echo "FAILED: $data"; break; fi
done
```

### 10. Register in registry.json

Add the new peer to `~/.hermes/registry/registry.json` on peer70:

```json
"peer138": {
  "last_seen": "2026-07-27T12:12:31Z",
  "host": "192.168.178.138",
  "skills": [],
  "skill_count": 0,
  "plugins": ["hmp"],
  "plugins_detail": ["hmp v0.1.3"],
  "plugin_deployed_at": "2026-07-27T12:12:31Z"
}
```

Also update the `"updated_at"` timestamp at the top of the file.

### 11. Update peer tables in SKILL.md

Add the new peer to the peer table in:
- `hermes-hmp/SKILL.md` → "Peer della rete" and "Peer registrati" tables
- `references/onboard-full-peer.md` (this file) — update detection checklist

### 12. Create peer-map.json

If not present, create `~/.hermes/peer-network/peer-map.json`:

```json
{
  "updated_at": "2026-07-27T12:15:00Z",
  "peers": {
    "peer70":  "192.168.178.70",
    "peer58":  "192.168.178.58",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer128": "192.168.178.112",
    "peer136": "192.168.178.136",
    "peer138": "192.168.178.138"
  }
}
```

### 13. Save in memory

```python
memory(action="add", target="memory",
  content="peer138: RPi 3B (arm64, 955MB RAM), DietPi/Debian 13 Trixie, "
          "Hermes v0.19.0, IP 192.168.178.138, HMP :18643 plugin v0.1.3, "
          "gateway systemd active.")
```

### 14. (Optional) Deploy capability-reuse plugin

If the peer should also run the capability-reuse plugin:

```bash
ssh root@192.168.178.138 "mkdir -p ~/.hermes/plugins/capability-reuse/"
scp ~/.hermes/plugins/capability-reuse/*.py   root@192.168.178.138:~/.hermes/plugins/capability-reuse/
scp ~/.hermes/plugins/capability-reuse/plugin.yaml root@192.168.178.138:~/.hermes/plugins/capability-reuse/
```

Then add `capability-reuse` to the `plugins.enabled` list in config.yaml:

```bash
ssh root@192.168.178.138 "sed -i '/^  enabled:/a\    - capability-reuse' ~/.hermes/config.yaml"
```

**⚠️ PITFALL: sed 'a' matches ALL `enabled:` keys — not just `plugins.enabled`.**

```bash
# WRONG — matches compression.enabled, stt.enabled, streaming.enabled, hmp.enabled too:
sed -i '/^  enabled:/a\    - capability-reuse' ~/.hermes/config.yaml

# RIGHT — target the plugins section specifically. If corruption happened:
sed -i '/^    - capability-reuse/d' ~/.hermes/config.yaml      # remove all spurious lines
sed -i '/^plugins:/,/^[a-z]/s/^  enabled:/  enabled:\n    - capability-reuse/'   # add only under plugins
```

**Symptom of corruption:** gateway starts but says "No messaging platforms enabled"
and `ss -tlnp` shows no hermes listener. The YAML parser silently ignores the
corrupted sections under `hmp:`, `compression:`, `stt:`, etc.

Always run `grep -n 'capability-reuse\|enabled:' ~/.hermes/config.yaml` after
the sed to verify the line appears exactly once and in the right section.

After adding, clear caches and restart:
```bash
find ~/.hermes/plugins -name '__pycache__' -type d -exec rm -rf {} \;
find ~/.hermes/plugins -name '*.pyc' -delete
touch ~/.hermes/plugins/*/*.py
systemctl restart hermes-gateway.service
```

### 15. Debugging plugin loading failures

If the gateway fails to load plugins (status=1, "No messaging platforms enabled"):

1. Enable plugin debug logging: `export HERMES_PLUGINS_DEBUG=1` before starting
2. Check journal: `journalctl -u hermes-gateway.service --no-pager | grep -i 'plugin\|capability\|hmp'`
3. This shows every manifest parsed, every plugin loaded, and every hook registered
4. Common issue: relative imports in `__init__.py` (`from . import module`) work
   correctly under Hermes' loader (`hermes_plugins.<slug>` namespace), but the
   `__package__` and `__path__` must be properly set — which the gateway does.

**Do NOT modify `from . import` to `import` in plugin __init__.py** — this breaks
the import system. If you accidentally did this, revert with:
```bash
sed -i 's|import protocol as ctrl|from . import protocol as ctrl|' __init__.py
```

### 16. Add to registry.json

Add the new peer to `~/.hermes/registry/registry.json` on peer70:

```json
"peer138": {
  "last_seen": "2026-07-27T12:12:31Z",
  "host": "192.168.178.138",
  "skills": [],
  "skill_count": 0,
  "plugins": ["hmp"],
  "plugins_detail": ["hmp v0.1.3"],
  "plugin_deployed_at": "2026-07-27T12:12:31Z"
}
```

Also update the `"updated_at"` timestamp at the top of the file.

### 17. Update peer tables in SKILL.md

Add the new peer to the peer table in:
- `hermes-hmp/SKILL.md` → "Peer della rete" and "Peer registrati" tables
- `references/onboard-full-peer.md` (this file) — update detection checklist

### 18. Create peer-map.json

If not present, create `~/.hermes/peer-network/peer-map.json`:

```json
{
  "updated_at": "2026-07-27T12:15:00Z",
  "peers": {
    "peer70":  "192.168.178.70",
    "peer58":  "192.168.178.58",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer128": "192.168.178.112",
    "peer136": "192.168.178.136",
    "peer138": "192.168.178.138"
  }
}
```

### 19. Save in memory

```python
memory(action="add", target="memory",
  content="peer138: RPi 3B (arm64, 955MB RAM), DietPi/Debian 13 Trixie, "
          "Hermes v0.19.0, IP 192.168.178.138, HMP :18643 plugin v0.1.3, "
          "gateway systemd active.")
```

### 20. Inform the peer about the cluster

Send an HMP message explaining the network context (recommended):

```bash
MSGID="cluster_$(date +%s%N)"
curl -s -X POST http://192.168.178.138:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d "{\"hmp_version\":\"1.0\",\"message_id\":\"${MSGID}\",\"from\":\"peer70\",\"to\":\"peer138\",\"type\":\"request\",\"timeout\":60,\"payload\":{\"text\":\"Benvenuto nella rete Hermes! ...\"}}"
# Then poll for completed
```

## Common issues

| Problem | Likely cause | Action |
|---------|-------------|--------|
| SSH "Permission denied" | Key not in `/root/.ssh/authorized_keys` | User must copy key manually on the peer |
| `:18643` Connection refused after restart | Gateway needs 5-10s to bind | Retry after sleep; check `systemctl status` |
| Gateway exits with status 1 | Plugin loading error or config parse error | Check journal: `journalctl -u hermes-gateway -n 20` |
| `systemctl restart` fails, then `reset-failed` succeeds | First restart killed old proc, new one failed | Always `reset-failed` before retry restart |
| No `plugins:` section in config.yaml | Fresh Hermes install | Must add it via SSH (see step 6) |
| "No messaging platforms enabled" in logs | YAML corrupted by sed | Check config for spurious `- capability-reuse` lines; clean with `sed -i '/^    - capability-reuse/d'` |
| Gateway active but no listener on :18643 | Plugin failed; check journal with HERMES_PLUGINS_DEBUG=1 | Enable debug logging, check plugin loading phase |
| `:8642` never listens; "API_SERVER_KEY is required" in gateway.log | Hermes v0.20.0+ requires the key even for loopback binds | Add `API_SERVER_KEY=<hex>` to `~/.hermes/.env`, restart |
| Gateway `active` but no :18643/:8642 listener for 15-30s | First start after plugin install (RPi slow, bytecode compile) | Poll /health every 2s up to 30s before declaring failure |
| `journalctl --user -u hermes-gateway` → "No journal files were found" | User journal not persisted on some images | Read `~/.hermes/logs/gateway.log` on the peer instead |
| Fresh install is user-mode (fausto, not root) | `hermes setup` as normal user on RPi/Debian | Use `fausto@`, `systemctl --user`, `/home/fausto/.hermes/...` paths |
| Peer answers welcome message but can't confirm skill loaded | Skill files present but never loaded via skill_view | Ask peer to run `skill_view(name='hermes-hmp')` and report protocol version |

## Detection checklist (from peer70)

Before starting SSH, check from peer70:

```bash
ping -c2 -W2 192.168.178.XXX           # host alive?
for P in 22 80 443 18643 8642 18644; do
  timeout 2 bash -c "echo > /dev/tcp/192.168.178.138/$P" 2>/dev/null \
    && echo ":${P} OPEN" || echo ":${P} CLOSED"
done
```

Typical fresh state: only port 22 (SSH) open. After onboarding: 18643 (HMP)
and optionally 8642 (API) should be open.

## Replacing a retired peer (e.g. peer105 → peer141)

When a new machine takes over a dead peer's slot, do the same onboarding but
ALSO remove the old peer everywhere, or scripts keep pinging the corpse:

1. registry.json: delete the old peer object, add the new one (skills,
   plugins_detail), bump `updated_at`
2. `peers/peer141.json` manifest: create for the new peer (peer_id, host,
   hostname, os, hermes_version, notes: "replaces peer105")
3. peer-map.json: remove old IP, add new IP
4. Delete stale per-peer files in `~/.hermes/peer-network/`:
   `peer105-registry.json`, `peer105-status.json` (and any peer105.json in
   `registry/peers/` if no longer relevant)
5. SKILL.md peer tables ("Peer della rete", "Peer registrati") + deploy
   pipeline note: old peer out, new peer in, mark "sostituisce peer105"
6. memory: record the replacement so future sessions don't quote the dead peer

Verified 2026-08-13: peer141 (Stella, RPi, Hermes v0.20.0, fausto user)
replaced peer105; keys were ALREADY exchanged both ways (check
`ssh -o BatchMode=yes fausto@IP 'hostname'` + `grep -c Stella
~/.ssh/authorized_keys` before assuming you must push keys).
