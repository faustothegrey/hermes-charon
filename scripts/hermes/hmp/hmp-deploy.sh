#!/bin/bash
# hmp-deploy.sh — Deploy HMP plugin a uno o piu peer
# Usage: hmp-deploy.sh <version> [peer_id ...]
#   es: hmp-deploy.sh 0.2.0              # deploy a tutti
#   es: hmp-deploy.sh 0.2.0 84 105       # solo peer84 e peer105
#   es: hmp-deploy.sh 0.2.0 --rollback   # ripristina backup su tutti
#
# Strategia:
#   - Source of truth: ~/.hermes/plugins/hmp/ su peer70
#   - Backup pre-deploy in ~/.hermes/plugins/hmp/backup/<old_version>/
#   - Scp dei 4 file su ogni peer + restart gateway + health check
#   - Se un peer fallisce: rollback immediato su quel peer

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

usage() {
  echo "Usage: $0 <version> [peer_id ...]"
  echo "  es: $0 0.2.0              # deploy a tutti"
  echo "  es: $0 0.2.0 84 105       # solo peer84 e 105"
  echo "  es: $0 0.2.0 --rollback   # rollback all'ultimo backup"
  exit 1
}

rollback_peer() {
  local peer="$1" ssh_user="$2" old_ver="$3"
  echo "  ⮑ Rollback peer${peer} a v${old_ver}..."
  for f in "${FILES[@]}"; do
    scp "$BACKUP_DIR/v${old_ver}/$f" "${ssh_user}:~/${REMOTE_HMP_DIR}/$f" >/dev/null 2>&1
  done
  echo "  ⮑ Restart gateway peer${peer}..."
  local restart_cmd
  for entry in "${PEER_MAP[@]}"; do
    local p="${entry%%:*}"
    local rest="${entry#*:}"
    if [ "$p" = "$peer" ]; then
      restart_cmd=$(echo "$rest" | cut -d: -f2-)
      break
    fi
  done
  ssh "$ssh_user" "$restart_cmd" 2>/dev/null || true
  echo "  ✅ Rollback peer${peer} completato"
}

[ $# -lt 1 ] && usage
VERSION="$1"
shift 2>/dev/null

# ── Rollback mode ──
if [ "$VERSION" = "--rollback" ]; then
  echo "=== Rollback ==="
  if [ ! -d "$BACKUP_DIR" ]; then
    echo "Nessun backup trovato."; exit 1
  fi
  OLD_VER=$(ls "$BACKUP_DIR" | sort -V | tail -1)
  echo "Torno a v${OLD_VER}"
  for entry in "${PEER_MAP[@]}"; do
    peer="${entry%%:*}"
    ssh_user=$(echo "${entry#*:}" | cut -d: -f1)
    [ $# -gt 0 ] && [[ " $* " != *" $peer "* ]] && continue
    rollback_peer "$peer" "$ssh_user" "$OLD_VER"
  done
  # Ripristina anche su peer70
  cp "$BACKUP_DIR/v${OLD_VER}/plugin.yaml" "$HMP_DIR/plugin.yaml"
  echo "✅ Rollback completato a v${OLD_VER}"
  exit 0
fi

# ── Determina peer target ──
TARGET_PEERS=()
if [ $# -gt 0 ]; then
  for p in "$@"; do TARGET_PEERS+=("$p"); done
else
  for entry in "${PEER_MAP[@]}"; do
    TARGET_PEERS+=("${entry%%:*}")
  done
fi

# ── Leggi versione corrente ──
OLD_VER=$(grep '^version:' "$HMP_DIR/plugin.yaml" | head -1 | sed 's/.*: *//')
echo "=== HMP Deploy: v${OLD_VER} → v${VERSION} ==="
echo "Target: peer${TARGET_PEERS[*]}"

# ── Backup versione corrente su peer70 ──
echo "1/4 Backup v${OLD_VER}..."
mkdir -p "$BACKUP_DIR/v${OLD_VER}"
for f in "${FILES[@]}"; do
  cp "$HMP_DIR/$f" "$BACKUP_DIR/v${OLD_VER}/$f"
done

# ── Bump version su peer70 ──
echo "2/4 Bump version a v${VERSION} sul sorgente..."
sed -i "s/^version:.*/version: ${VERSION}/" "$HMP_DIR/plugin.yaml"

# ── Deploy su ogni peer target ──
echo "3/4 Deploy in corso..."
FAILED=()
for peer in "${TARGET_PEERS[@]}"; do
  echo "── peer${peer} ──"

  # Trova ssh_user, ip_addr e restart_command
  ssh_user=""; ip_addr=""; restart_cmd=""
  for entry in "${PEER_MAP[@]}"; do
    p="${entry%%:*}"
    if [ "$p" = "$peer" ]; then
      rest="${entry#*:}"
      ssh_user="${rest%%:*}"
      ip_addr="${ssh_user#*@}"
      restart_cmd="${rest#*:}"
      break
    fi
  done
  [ -z "$ssh_user" ] && echo "  ❌ peer${peer}: sconosciuto" && FAILED+=("$peer") && continue

  # Backup remoto
  ssh "$ssh_user" "mkdir -p ~/${REMOTE_HMP_DIR}/backup/v${OLD_VER} && \
    cp ~/${REMOTE_HMP_DIR}/{plugin.yaml,__init__.py,adapter.py,core.py} ~/${REMOTE_HMP_DIR}/backup/v${OLD_VER}/" 2>/dev/null || true

  # Copia file
  for f in "${FILES[@]}"; do
    scp "$HMP_DIR/$f" "${ssh_user}:~/${REMOTE_HMP_DIR}/$f" 2>&1  # visibile per debug
  done
  echo "  ✅ File copiati"

  # Restart gateway
  echo "  ⮑ Restart gateway..."
  ssh "$ssh_user" "$restart_cmd" 2>/dev/null || echo "  ⚠️ Restart fallito (tento comunque health check)"

  # Health check (max 30s)
  echo "  ⮑ Health check :18643..."
  OK=false
  for i in $(seq 1 6); do
    sleep 5
    if curl -sf "http://${ip_addr}:18643/health" >/dev/null 2>&1; then
      echo "  ✅ peer${peer} online"
      OK=true
      break
    fi
    echo "  ⮑ tentativo ${i}/6..."
  done
  if [ "$OK" = false ]; then
    echo "  ❌ peer${peer} non risponde dopo 30s — rollback!"
    rollback_peer "$peer" "$ssh_user" "$OLD_VER"
    FAILED+=("$peer")
  fi
done

# ── Aggiorna registry ──
echo "4/4 Aggiorno registry..."
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for peer in "${TARGET_PEERS[@]}"; do
  python3 -c "
import json
with open('$REGISTRY') as f:
    reg = json.load(f)
p = reg.get('peers', {}).get('peer${peer}', {})
if p:
    old_detail = p.get('plugins_detail', [])
    new_detail = []
    for d in old_detail:
        if d.startswith('hmp '):
            new_detail.append('hmp v${VERSION}')
        else:
            new_detail.append(d)
    p['plugins_detail'] = new_detail
    p['last_seen'] = '$NOW'
    p['plugin_deployed_at'] = '$NOW'
with open('$REGISTRY', 'w') as f:
    json.dump(reg, f, indent=2)
"
done

# ── Report finale ──
echo "=== Report ==="
echo "Versione: v${OLD_VER} → v${VERSION}"
echo "Deploy: peer${TARGET_PEERS[*]}"
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "✅ Tutti OK!"
else
  echo "❌ Falliti: peer${FAILED[*]} (rollback eseguito)"
fi
