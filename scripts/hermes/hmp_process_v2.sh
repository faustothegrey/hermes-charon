#!/bin/bash
echo "=== HMP PROCESS MSG_347714311267 ==="
DB="/home/fausto/.hermes/data/hmp/agent_messages.db"

# Step 1: Check current state
echo "--- Step 0: Current state ---"
python3 -c "
import sqlite3, json
c = sqlite3.connect('$DB')
c.row_factory = sqlite3.Row
r = c.execute('SELECT message_id, status, progress FROM messages WHERE message_id = ?', ('msg_347714311267',)).fetchone()
if r: print('Current: status=%s progress=%s' % (r['status'], r['progress']))
else: print('Message not found')
c.close()
"

# Step 1: set WORKING
echo "--- Step 1: WORKING ---"
python3 -c "
import sqlite3, json
c = sqlite3.connect('$DB')
now = '2026-07-14T22:05:00Z'
c.execute('UPDATE messages SET status=?, updated_at=? WHERE message_id=?', ('working', now, 'msg_347714311267'))
c.commit()
r = c.execute('SELECT status FROM messages WHERE message_id=?', ('msg_347714311267',)).fetchone()
print('Result:', r[0] if r else 'NOT FOUND')
c.close()
"

# Step 2: Heartbeat
echo "--- Step 2: HEARTBEAT ---"
python3 -c "
import sqlite3
c = sqlite3.connect('$DB')
now = '2026-07-14T22:06:00Z'
c.execute('UPDATE messages SET progress=?, progress_pct=?, has_progress=1, updated_at=? WHERE message_id=?', ('ricerco novita RISC-V...', 40, now, 'msg_347714311267'))
c.commit()
r = c.execute('SELECT progress, progress_pct FROM messages WHERE message_id=?', ('msg_347714311267',)).fetchone()
print('Result: progress=%s pct=%s' % (r[0], r[1]) if r else 'NOT FOUND')
c.close()
"

# Step 3: COMPLETED with payload
echo "--- Step 3: COMPLETED ---"
python3 << 'PYEOF'
import sqlite3, json
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
now = '2026-07-14T22:07:00Z'
payload = json.dumps({
    'summary': "RISC-V boards 2026: SiFive HiFive Premier P550 (flagship, 16/32GB LPDDR5, ~20TOPS NPU), StarFive VisionFive 2 (best value, 2-8GB), Milk-V Mars (Pi-compatible), Banana Pi BPI-F3 (RVV 1.0 vector, 16GB), Milk-V Pioneer (64-core workstation, 128GB). Prezzi: VisionFive 2 da ~$35-90, Milk-V Mars ~$40-80, HiFive P550 ~$299-499, Pioneer ~$2000+.",
    'boards': [
        "SiFive HiFive Premier P550 - 4xP550@1.8GHz, 16/32GB LPDDR5, 128GB eMMC, ~20TOPS NPU, ~$299-499",
        "StarFive VisionFive 2 - JH7110 4xU74@1.5GHz, 2-8GB LPDDR4, dual GbE, M.2, ~$35-90",
        "Milk-V Mars - JH7110, Pi form factor, up to 8GB, PoE, ~$40-80",
        "Banana Pi BPI-F3 - SpacemiT K1 8-core, RVV 1.0, up to 16GB, ~$70-120",
        "Milk-V Jupiter - K1/K1X Mini-ITX, up to 16GB, ~$150-250",
        "Milk-V Pioneer - SG2042 64-core, up to 128GB, workstation, ~$2000+",
        "Canaan CanMV-K230 - dual C908@1.6GHz, RVV 1.0, 6TOPS NPU, edge AI, ~$50-80",
    ],
    'sources': [
        "https://lucaberton.com/blog/risc-v-development-boards-2026-guide/",
        "https://microcontrollerslab.com/best-risc-v-development-boards-buying-guide/",
        "https://riscv.org/blog/5-risc-v-sbcs-that-are-worth-using/",
    ]
})
c.execute("UPDATE messages SET status=?, completed_at=?, payload=?, updated_at=? WHERE message_id=?", ('completed', now, payload, now, 'msg_347714311267'))
c.commit()
r = c.execute("SELECT status, payload FROM messages WHERE message_id=?", ('msg_347714311267',)).fetchone()
if r:
    print('Result: status=%s' % r['status'])
    p = json.loads(r['payload'])
    print('Boards: %d, Sources: %d' % (len(p['boards']), len(p['sources'])))
c.close()
PYEOF

echo "=== ALL DONE ==="