#!/bin/bash
OUTFILE="/tmp/hmp_verify_result.txt"
DB="/home/fausto/.hermes/data/hmp/agent_messages.db"
python3 << 'PYEOF' > /tmp/hmp_verify_result.txt
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
    print('Created:', r['created_at'])
    print('Updated:', r['updated_at'])
    print('Completed:', r['completed_at'])
    if r['payload']:
        p = json.loads(r['payload']) if isinstance(r['payload'], str) else r['payload']
        print('---')
        print('Summary:', p.get('summary', '')[:100])
        print('Boards:')
        for b in p.get('boards', []):
            print('  -', b)
        print('Sources:')
        for s in p.get('sources', []):
            print('  -', s)
else:
    print('NOT FOUND')
c.close()
PYEOF
echo "DONE"