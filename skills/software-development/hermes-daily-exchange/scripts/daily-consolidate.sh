#!/bin/bash
# daily-consolidate.sh — Consolida i digest di tutti i peer
set -euo pipefail
DATE="${1:-$(date +%Y-%m-%d)}"
EXCHANGE="$HOME/.hermes/exchange"
DAILY_DIR="$EXCHANGE/daily"
mkdir -p "$DAILY_DIR"
CONSOLIDATED="$DAILY_DIR/${DATE}.md"
echo "=== Consolidamento $DATE ==="
{ echo "# Daily Exchange — $DATE"; echo; echo "Generato il $(date '+%Y-%m-%d %H:%M:%S') da peer70"; echo; } > "$CONSOLIDATED"
COUNT=0
for peer_dir in "$EXCHANGE"/peer*/; do
  PEER=$(basename "$peer_dir"); FILE="${peer_dir}${DATE}.md"
  if [ -f "$FILE" ]; then
    { echo "---"; echo "## $PEER"; echo; cat "$FILE"; echo; } >> "$CONSOLIDATED"
    COUNT=$((COUNT + 1)); echo "  ✅ $PEER"
  else echo "  ⏳ $PEER: nessun digest per $DATE"; fi
done
echo; echo "Consolidato: $CONSOLIDATED ($(wc -l < "$CONSOLIDATED") righe, $COUNT peer)"
# Copia nel vault Obsidian
VAULT_DIR="$HOME/Documents/Obsidian Vault"
if [ -d "$VAULT_DIR" ]; then
  mkdir -p "$VAULT_DIR/Exchange"
  cp "$CONSOLIDATED" "$VAULT_DIR/Exchange/${DATE}.md"
  echo "✅ Copiato nel vault Obsidian: Exchange/${DATE}.md"
fi
