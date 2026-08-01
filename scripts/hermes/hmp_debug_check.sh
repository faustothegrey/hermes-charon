#!/bin/bash
echo "=== HMP DB Check ==="
DB="/home/fausto/.hermes/data/hmp/agent_messages.db"
echo "DB path: $DB"
echo "DB exists: $(test -f "$DB" && echo YES || echo NO)"
echo "DB size: $(stat -c%s "$DB" 2>/dev/null || echo '?')"
echo "Python3: $(which python3 2>/dev/null || echo 'NOT FOUND')"
echo "=== Checking message ==="
python3 -c "
import sqlite3, json
c = sqlite3.connect('$DB')
c.row_factory = sqlite3.Row
r = c.execute('SELECT message_id, status, progress, from_peer, to_peer, type, payload, created_at, updated_at FROM messages WHERE message_id = ?', ('msg_347714311267',)).fetchone()
if r:
    print('Found:')
    for k in r.keys():
        print(f'  {k}: {r[k]}')
else:
    print('Message NOT found in DB')
    count = c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    print(f'Total messages in DB: {count}')
    rows = c.execute('SELECT message_id, status, from_peer, to_peer FROM messages ORDER BY created_at DESC LIMIT 5').fetchall()
    for row in rows:
        print(f'  - {row[\"message_id\"]} [{row[\"status\"]}] {row[\"from_peer\"]} -> {row[\"to_peer\"]}')
c.close()
"