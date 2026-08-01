#!/bin/bash
# daily-digest.sh — Genera il digest giornaliero per questo peer
# Output: ~/.hermes/exchange/<peer_id>/YYYY-MM-DD.md
# Usage: daily-digest.sh [peer_id]
#   default peer_id: letto da HMP_NODE_ID, HMP config, o hostname

set -euo pipefail

PEER="${1:-}"
if [ -z "$PEER" ]; then
  # Auto-detect peer id
  if [ -n "${HMP_NODE_ID:-}" ]; then
    PEER="$HMP_NODE_ID"
  elif [ -f ~/.hermes/config.yaml ] && grep -q 'node_id:' ~/.hermes/config.yaml 2>/dev/null; then
    PEER=$(grep 'node_id:' ~/.hermes/config.yaml | head -1 | sed 's/.*node_id: *//')
  else
    PEER=$(hostname -s 2>/dev/null || echo "unknown")
  fi
fi

DATE=$(date +%Y-%m-%d)
OUTDIR="$HOME/.hermes/exchange/${PEER}"
OUTFILE="${OUTDIR}/${DATE}.md"
mkdir -p "$OUTDIR"

# Se esiste già, non sovrascrivere
if [ -f "$OUTFILE" ]; then
  echo "⚠️  $OUTFILE esiste già. Usa --force per sovrascrivere." >&2
  [ "${2:-}" != "--force" ] && exit 0
fi

# ── Raccogli dati ──────────────────────────────────────────────

# Skill modificate oggi
SKILLS=$(find ~/.hermes/skills -name "SKILL.md" -newer "$(date -d '24 hours ago' +%Y%m%d%H%M.%S 2>/dev/null || echo 'yesterday')" 2>/dev/null | head -5 || true)

# Sessioni recenti (ultime 24h da session_search o fallback a state.db)
SESSIONS=""
if command -v python3 &>/dev/null; then
  SESSIONS=$(python3 -c "
import json, sqlite3, time
from pathlib import Path
db = Path.home() / '.hermes' / 'state.db'
if db.exists():
    cutoff = time.time() - 86400
    conn = sqlite3.connect(str(db))
    cur = conn.execute('SELECT id, title, started_at FROM sessions WHERE started_at > ? ORDER BY started_at DESC LIMIT 5', (cutoff,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            dt = time.strftime('%H:%M', time.localtime(r[2]))
            print(f'  - {dt} | {r[1] or \"(senza titolo)\"}')
    conn.close()
" 2>/dev/null) || SESSIONS=""
fi

# Plugin version corrente
PLUGIN_VER=$(grep '^version:' ~/.hermes/plugins/hmp/plugin.yaml 2>/dev/null | sed 's/.*: *//' || echo "sconosciuta")

# ── Genera file ─────────────────────────────────────────────────

cat > "$OUTFILE" <<EOF
---
peer: ${PEER}
date: ${DATE}
plugin_version: ${PLUGIN_VER}
type: daily
---

## Sessioni di oggi

$( [ -n "$SESSIONS" ] && echo "$SESSIONS" || echo "  (nessuna sessione registrata)")

## Skill modificate

$( [ -n "$SKILLS" ] && echo "$SKILLS" || echo "  (nessuna skill modificata)")

## Plugin HMP

Versione plugin: ${PLUGIN_VER}
EOF

echo "✅ Digest generato: $OUTFILE"
wc -l "$OUTFILE"
