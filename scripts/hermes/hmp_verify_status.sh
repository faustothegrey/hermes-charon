#!/bin/bash
echo "=== HMP Status Check ==="
DB="/home/fausto/.hermes/data/hmp/agent_messages.db"
python3 << 'PYEOF'
import sqlite3, json
c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
c.row_factory = sqlite3.Row
r = c.execute("SELECT message_id, status, from_peer, to_peer, progress, progress_pct, has_progress, created_at, updated_at, completed_at, payload FROM messages WHERE message_id = ?", ('msg_347714311267',)).fetchone()
if r:
    print('Message:', r['message_id'])
    print('Status:', r['status'])
    print('From:', r['from_peer'], '-> To:', r['to_peer'])
    print('Progress:', r['progress'])
    print('Progress%:', r['progress_pct'])
    print('Has progress:', r['has_progress'])
    print('Created:', r['created_at'])
    print('Updated:', r['updated_at'])
    print('Completed:', r['completed_at'])
    if r['payload']:
        p = json.loads(r['payload'])
        print('Summary:', p.get('summary', '')[:100])
        print('Boards:', len(p.get('boards', [])))
        print('Sources:', len(p.get('sources', [])))
        for b in p.get('boards', []):
            print('  -', b[:80])
else:
    print('NOT FOUND')
c.close()
PYEOF
echo "=== END ==="