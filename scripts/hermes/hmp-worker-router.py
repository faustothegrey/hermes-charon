#!/usr/bin/env python3
import json, os, time, sqlite3
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PEER_NAME = 'peer70'
HMP_COORDINATOR = 'http://127.0.0.1:8643'
DB_PATH = os.path.expanduser('~/.hermes/data/hmp/agent_messages.db')

def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def send_via_hmp(to_peer, msg_id, payload, in_reply_to=None):
    resp_id = 'resp_' + PEER_NAME + '_' + str(int(time.time()))
    msg = {'hmp_version': '1.0', 'message_id': resp_id, 'idempotency_key': resp_id,
        'from': PEER_NAME, 'to': to_peer, 'type': 'response',
        'timestamp': now_iso(), 'timeout': 30, 'payload': payload}
    if in_reply_to: msg['in_reply_to'] = in_reply_to
    data = json.dumps(msg).encode()
    req = Request(HMP_COORDINATOR + '/hmp/send', data=data, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=10) as resp: return json.loads(resp.read())
    except (HTTPError, URLError) as ex: return {"error": str(ex)}

def process_message(msg):
    p = msg.get('payload', {})
    if isinstance(p, str):
        try: p = json.loads(p)
        except: pass
    task = p.get('task_type', 'general') if isinstance(p, dict) else 'general'
    if task == 'ping': return {'answer': 'Pong da peer70!', 'status': 'online', 'hostname': 'raspberrypi'}
    return {'answer': 'peer70: ricevuto e processato', 'status': 'ok'}

def main():
    if not os.path.exists(DB_PATH): print('hmp-worker(peer70): DB non trovato'); return
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    pending = conn.execute("SELECT * FROM messages WHERE to_peer = ? AND status IN ('delivered', 'working') AND from_peer != ? ORDER BY created_at ASC LIMIT 10", (PEER_NAME, PEER_NAME)).fetchall()
    processed = 0
    for row in pending:
        msg = dict(row); mid = msg['message_id']
        rp = process_message(msg)
        result = send_via_hmp(msg['from_peer'], mid, rp, in_reply_to=mid)
        if 'message_id' in result or 'duplicate' in result:
            conn.execute("UPDATE messages SET status='completed', completed_at=? WHERE message_id=?", (now_iso(), mid)); conn.commit()
            print(f'  ✅ {mid}: risposto a {msg["from_peer"]}'); processed += 1
        else:
            print(f'  ❌ {mid}: {result}')
    conn.close()
    if processed == 0: print('hmp-worker(peer70): idle')
    else: print(f'hmp-worker(peer70): {processed} processati')

main()
