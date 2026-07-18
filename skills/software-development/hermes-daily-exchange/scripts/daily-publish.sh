#!/bin/bash
# daily-publish.sh — Genera digest e lo invia a peer70 via SCP
set -euo pipefail
PEER="${1:-}"; [ -z "$PEER" ] && echo "Usage: $0 <peer_id>" && exit 1
DATE=$(date +%Y-%m-%d)
bash ~/.hermes/scripts/daily-digest.sh "$PEER" --force
DIGEST_FILE="$HOME/.hermes/exchange/${PEER}/${DATE}.md"
[ ! -f "$DIGEST_FILE" ] && echo "❌ Digest non trovato" && exit 1
REMOTE="fausto@192.168.178.70"
REMOTE_DIR=".hermes/exchange/${PEER}"
ssh "$REMOTE" "mkdir -p $REMOTE_DIR" 2>/dev/null || true
scp "$DIGEST_FILE" "${REMOTE}:${REMOTE_DIR}/${DATE}.md" >/dev/null 2>&1 && \
  echo "✅ Digest di ${PEER} inviato a peer70" || echo "❌ Invio fallito"
