#!/bin/bash
# daily-publish.sh — Solo genera il digest (senza SCP)
# La copia a peer70 la fa il cron su peer70 via SSH+SCP
# Usage: daily-publish.sh <peer_id>
# Esempio: daily-publish.sh peer106

set -euo pipefail

PEER="${1:-}"
[ -z "$PEER" ] && echo "Usage: $0 <peer_id>" && exit 1

bash ~/.hermes/scripts/daily-digest.sh "$PEER" --force
