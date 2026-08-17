#!/bin/bash
# daily-collect.sh — Eseguito su peer70. Genera digest su ogni peer via SSH e copia i file.
# Usage: daily-collect.sh [date]
#   default: oggi

set -euo pipefail

DATE="${1:-$(date +%Y-%m-%d)}"
EXCHANGE="$HOME/.hermes/exchange"

# (peer_id ssh_user remote_home_dir)
PEERS=(
  "peer84 fausto@192.168.178.84 /home/fausto"
  "peer106 root@192.168.178.106 /root"
  "peer128 fausto@192.168.178.112 /Users/fausto"
  "peer136 fausto@192.168.178.136 /home/fausto"
)

echo "=== Raccolta digest $DATE ==="

for entry in "${PEERS[@]}"; do
  read -r peer ssh_user remote_home <<< "$entry"

  # 1. Genera digest via SSH
  echo -n "  $peer: generazione... "
  if ssh "$ssh_user" "bash ~/.hermes/scripts/daily-publish.sh $peer" 2>/dev/null; then
    echo -n "✅ "
  else
    echo -n "❌ "
    continue
  fi

  # 2. Copia file da peer a peer70
  REMOTE_FILE="${remote_home}/.hermes/exchange/${peer}/${DATE}.md"
  LOCAL_DIR="${EXCHANGE}/${peer}"
  mkdir -p "$LOCAL_DIR"

  if scp "${ssh_user}:${REMOTE_FILE}" "${LOCAL_DIR}/${DATE}.md" >/dev/null 2>&1; then
    echo "✅ copiato"
  else
    echo "❌ copia fallita"
  fi
done

echo
echo "Raccolta completata"
