#!/bin/bash
# hmp-deploy.sh — Deploy HMP plugin a uno o piu peer
# Usage: hmp-deploy.sh <version> [peer_id ...]
set -euo pipefail

HMP_DIR="$HOME/.hermes/plugins/hmp"
BACKUP_DIR="$HMP_DIR/backup"
REMOTE_HMP_DIR=".hermes/plugins/hmp"
REGISTRY="$HOME/.hermes/registry/registry.json"
FILES=("plugin.yaml" "__init__.py" "adapter.py" "core.py")
PEER_MAP=(
  "84:fausto@192.168.178.84:systemctl --user restart hermes-gateway"
  "105:root@192.168.178.105:systemctl --user restart hermes-gateway"
  "106:root@192.168.178.106:systemctl --user kill hermes-gateway -s KILL 2>/dev/null; sleep 1; systemctl --user reset-failed hermes-gateway; systemctl --user start hermes-gateway"
  "128:fausto@192.168.178.112:launchctl kickstart -kp gui/501/ai.hermes.gateway"
)

usage() { echo "Usage: $0 <version> [peer_id ...]"; echo "  es: $0 0.1.2"; echo "  es: $0 0.1.2 84 105"; echo "  es: $0 0.1.2 --rollback"; exit 1; }

rollback_peer() {
  local peer="$1" ssh_user="$2" old_ver="$3"
  echo "  ⮑ Rollback peer${peer} a v${old_ver}..."
  for f in "${FILES[@]}"; do
    scp "$BACKUP_DIR/v${old_ver}/$f" "${ssh_user}:~/${REMOTE_HMP_DIR}/$f" >/dev/null 2>&1
  done
  echo "  ⮑ Pulizia bytecode cache..."
  ssh "$ssh_user" "find ~/${REMOTE_HMP_DIR} -name '__pycache__' -type d -exec rm -rf {} \; 2>/dev/null; touch ~/${REMOTE_HMP_DIR}/*.py 2>/dev/null" || true
  local restart_cmd
  for entry in "${PEER_MAP[@]}"; do
    local p="${entry%%:*}" rest="${entry#*:}"
    if [ "$p" = "$peer" ]; then restart_cmd=$(echo "$rest" | cut -d: -f2-); break; fi
  done
  ssh "$ssh_user" "$restart_cmd" 2>/dev/null || true
  echo "  ✅ Rollback peer${peer} completato"
}

[ $# -lt 1 ] && usage
VERSION="$1"; shift 2>/dev/null

if [ "$VERSION" = "--rollback" ]; then
  echo "=== Rollback ==="; [ ! -d "$BACKUP_DIR" ] && echo "Nessun backup trovato." && exit 1
  OLD_VER=$(ls "$BACKUP_DIR" | sort -V | tail -1)
  echo "Torno a v${OLD_VER}"
  for entry in "${PEER_MAP[@]}"; do
    peer="${entry%%:*}"; ssh_user=$(echo "${entry#*:}" | cut -d: -f1)
    [ $# -gt 0 ] && [[ " $* " != *" $peer "* ]] && continue
    rollback_peer "$peer" "$ssh_user" "$OLD_VER"
  done
  cp "$BACKUP_DIR/v${OLD_VER}/plugin.yaml" "$HMP_DIR/plugin.yaml"
  echo "✅ Rollback completato a v${OLD_VER}"; exit 0
fi

TARGET_PEERS=()
if [ $# -gt 0 ]; then for p in "$@"; do TARGET_PEERS+=("$p"); done
else for entry in "${PEER_MAP[@]}"; do TARGET_PEERS+=("${entry%%:*}"); done; fi

OLD_VER=$(grep '^version:' "$HMP_DIR/plugin.yaml" | head -1 | sed 's/.*: *//')
echo "=== HMP Deploy: v${OLD_VER} → v${VERSION} ==="
echo "Target: peer${TARGET_PEERS[*]}"

echo "1/4 Backup v${OLD_VER}..."; mkdir -p "$BACKUP_DIR/v${OLD_VER}"
for f in "${FILES[@]}"; do cp "$HMP_DIR/$f" "$BACKUP_DIR/v${OLD_VER}/$f"; done

echo "2/4 Bump version a v${VERSION} sul sorgente..."
sed -i "s/^version:.*/version: ${VERSION}/" "$HMP_DIR/plugin.yaml"

echo "3/4 Deploy in corso..."; FAILED=()
for peer in "${TARGET_PEERS[@]}"; do
  echo "── peer${peer} ──"
  ssh_user=""; ip_addr=""; restart_cmd=""
  for entry in "${PEER_MAP[@]}"; do
    p="${entry%%:*}"
    if [ "$p" = "$peer" ]; then
      rest="${entry#*:}"; ssh_user="${rest%%:*}"; ip_addr="${ssh_user#*@}"; restart_cmd="${rest#*:}"
      break
    fi
  done
  [ -z "$ssh_user" ] && echo "  ❌ peer${peer}: sconosciuto" && FAILED+=("$peer") && continue
  ssh "$ssh_user" "mkdir -p ~/${REMOTE_HMP_DIR}/backup/v${OLD_VER} && cp ~/${REMOTE_HMP_DIR}/{plugin.yaml,__init__.py,adapter.py,core.py} ~/${REMOTE_HMP_DIR}/backup/v${OLD_VER}/" 2>/dev/null || true
  for f in "${FILES[@]}"; do scp "$HMP_DIR/$f" "${ssh_user}:~/${REMOTE_HMP_DIR}/$f" 2>&1; done
  echo "  ✅ File copiati"
  echo "  ⮑ Pulizia bytecode cache sul target..."
  ssh "$ssh_user" "find ~/${REMOTE_HMP_DIR} -name '__pycache__' -type d -exec rm -rf {} \; 2>/dev/null; touch ~/${REMOTE_HMP_DIR}/*.py 2>/dev/null" || true
  echo "  ⮑ Restart gateway..."
  ssh "$ssh_user" "$restart_cmd" 2>/dev/null || echo "  ⚠️ Restart fallito (tento comunque health check)"
  echo "  ⮑ Health check :18643..."
  OK=false
  for i in $(seq 1 6); do sleep 5
    if curl -sf "http://${ip_addr}:18643/health" >/dev/null 2>&1; then
      echo "  ✅ peer${peer} online"; OK=true; break
    fi; echo "  ⮑ tentativo ${i}/6..."
  done
  if [ "$OK" = false ]; then
    echo "  ❌ peer${peer} non risponde dopo 30s — rollback!"
    rollback_peer "$peer" "$ssh_user" "$OLD_VER"; FAILED+=("$peer")
  fi
done

echo "4/4 Aggiorno registry..."; NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for peer in "${TARGET_PEERS[@]}"; do
  python3 -c "
import json
with open('$REGISTRY') as f: reg = json.load(f)
p = reg.get('peers', {}).get('peer${peer}', {})
if p:
    old = p.get('plugins_detail', [])
    new = [d for d in old if not d.startswith('hmp ')]
    new.append('hmp v${VERSION}')
    p['plugins_detail'] = new; p['last_seen'] = '$NOW'; p['plugin_deployed_at'] = '$NOW'
with open('$REGISTRY', 'w') as f: json.dump(reg, f, indent=2)
"
done

echo "=== Report ==="; echo "Versione: v${OLD_VER} → v${VERSION}"
echo "Deploy: peer${TARGET_PEERS[*]}"
if [ ${#FAILED[@]} -eq 0 ]; then echo "✅ Tutti OK!"
else echo "❌ Falliti: peer${FAILED[*]} (rollback eseguito)"; fi
