#!/bin/bash
# Direct SQLite update for HMP msg_347714311267
set -e

DB="$HOME/.hermes/data/hmp/agent_messages.db"

# 1) Verify DB exists
echo "DB exists: $([ -f "$DB" ] && echo YES || echo NO)"

# 2) Current state
echo "Current state:"
python3 << 'PYEOF'
import sqlite3
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
c.row_factory = sqlite3.Row
r = c.execute("SELECT message_id, status, progress FROM messages WHERE message_id = ?", ('msg_347714311267',)).fetchone()
if r:
    print('ID: {}  Status: {}  Progress: {}'.format(r['message_id'], r['status'], r['progress']))
else:
    print('Message not found')
c.close()
PYEOF

# 3) Update to WORKING
python3 << 'PYEOF'
import sqlite3, json
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
now = '2026-07-14T21:20:00Z'
c.execute("UPDATE messages SET status=?, updated_at=? WHERE message_id=?", ('working', now, 'msg_347714311267'))
c.commit()
print('-> working OK')
r = c.execute("SELECT status FROM messages WHERE message_id=?", ('msg_347714311267',)).fetchone()
print('  now:', r[0])
c.close()
PYEOF

# 4) Update heartbeat
python3 << 'PYEOF'
import sqlite3
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
now = '2026-07-14T21:21:00Z'
c.execute("UPDATE messages SET progress=?, progress_pct=?, has_progress=1, updated_at=? WHERE message_id=?", ('ricerco novita RISC-V...', 40, now, 'msg_347714311267'))
c.commit()
print('-> heartbeat OK')
c.close()
PYEOF

# 5) Complete with payload
python3 << 'PYEOF'
import sqlite3, json
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
now = '2026-07-14T21:22:00Z'
payload = json.dumps({
    'summary': 'RISC-V boards 2026: SiFive HiFive Premier P550 (flagship, 16/32GB LPDDR5, ~20TOPS NPU), StarFive VisionFive 2 (best value, 2-8GB), Milk-V Mars (Pi-compatible), Banana Pi BPI-F3 (RVV 1.0 vector, 16GB), Milk-V Pioneer (64-core workstation, 128GB). Prezzi: VisionFive 2 da ~$35-90, Milk-V Mars ~$40-80, HiFive P550 ~$299-499, Pioneer ~$2000+.',
    'boards': [
        'SiFive HiFive Premier P550 - 4xP550@1.8GHz, 16/32GB LPDDR5, 128GB eMMC, ~20TOPS NPU, ~$299-499',
        'StarFive VisionFive 2 - JH7110 4xU74@1.5GHz, 2-8GB LPDDR4, dual GbE, M.2, ~$35-90',
        'Milk-V Mars - JH7110, Pi form factor, up to 8GB, PoE, ~$40-80',
        'Banana Pi BPI-F3 - SpacemiT K1 8-core, RVV 1.0, up to 16GB, ~$70-120',
        'Milk-V Jupiter - K1/K1X Mini-ITX, up to 16GB, ~$150-250',
        'Milk-V Pioneer - SG2042 64-core, up to 128GB, workstation, ~$2000+',
        'Canaan CanMV-K230 - dual C908@1.6GHz, RVV 1.0, 6TOPS NPU, edge AI, ~$50-80',
    ],
    'sources': [
        'https://lucaberton.com/blog/risc-v-development-boards-2026-guide/',
        'https://microcontrollerslab.com/best-risc-v-development-boards-buying-guide/',
        'https://riscv.org/blog/5-risc-v-sbcs-that-are-worth-using/',
    ]
})
c.execute("UPDATE messages SET status=?, completed_at=?, payload=?, updated_at=? WHERE message_id=?", ('completed', now, payload, now, 'msg_347714311267'))
c.commit()
r = c.execute("SELECT status, payload FROM messages WHERE message_id=?", ('msg_347714311267',)).fetchone()
print('-> completed OK')
print('  status:', r[0])
pl = json.loads(r[1])
print('  boards:', len(pl['boards']), 'boards listed')
print('  sources:', len(pl['sources']), 'sources')
c.close()
PYEOF

echo "=== ALL DONE ==="