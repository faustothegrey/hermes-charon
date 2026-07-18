#!/bin/bash
# daily-digest.sh — Genera il digest giornaliero per questo peer
# Output: ~/.hermes/exchange/<peer_id>/YYYY-MM-DD.md
set -euo pipefail

PEER="${1:-}"
[ -z "$PEER" ] && PEER=$(hostname -s 2>/dev/null || echo "unknown")
DATE=$(date +%Y-%m-%d)
OUTDIR="$HOME/.hermes/exchange/${PEER}"
OUTFILE="${OUTDIR}/${DATE}.md"
mkdir -p "$OUTDIR"

[ -f "$OUTFILE" ] && [ "${2:-}" != "--force" ] && echo "⚠️  $OUTFILE esiste già. Usa --force per sovrascrivere." >&2 && exit 0

PLUGIN_VER=$(grep '^version:' ~/.hermes/plugins/hmp/plugin.yaml 2>/dev/null | sed 's/.*: *//' || echo "sconosciuta")
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

SKILLS=$(find ~/.hermes/skills -name "SKILL.md" -newer "$(date -d '24 hours ago' +%Y%m%d%H%M.%S 2>/dev/null || echo 'yesterday')" 2>/dev/null | head -5 || true)

cat > "$OUTFILE" <<EOF
---
peer: ${PEER}
date: ${DATE}
plugin_version: ${PLUGIN_VER}
type: daily
---

## Sessioni di oggi

$( [ -n "$SESSIONS" ] && echo "$SESSIONS" || echo "  (nessuna)")

## Skill modificate

$( [ -n "$SKILLS" ] && echo "$SKILLS" || echo "  (nessuna)")

## Plugin HMP

Versione plugin: ${PLUGIN_VER}
EOF
echo "✅ Digest generato: $OUTFILE"
