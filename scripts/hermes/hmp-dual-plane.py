#!/usr/bin/env python3
"""
HMP Dual-Plane v2.0.0 — Server-Side Protocol
=============================================

PRINCIPIO: ogni peer espone :18644 che accetta {session_id, text}.
Il server locale gestisce internamente tutto: sessioni API, invio
all'agente, fallback HMP. Il client manda una sola richiesta.

USAGE (server, su ogni peer):
  from hmp_dual_plane import run_server
  run_server(host="0.0.0.0", port=18644, node_id="peer70")

USAGE (client, da coordinator):
  from hmp_dual_plane import send_to_peer
  resp = send_to_peer("peer106", "Ciao!", session_id="peer70_peer106")
"""
import json, time, os, uuid, sqlite3
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ── Config ──
DB_PATH = Path.home() / ".hermes" / "data" / "hmp" / "dual-plane.db"
KEYS_PATH = Path.home() / ".hermes" / "peer-network" / "peer-api-keys.json"
DEFAULT_MAX_TOKENS = 1024

PEER_HOSTS = {
    "peer70":  "127.0.0.1",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer58":  "192.168.178.58",
    "peer136": "192.168.178.136",
    "peer128": "192.168.178.112",
}

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def new_id(prefix="msg"):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

def load_api_keys():
    if KEYS_PATH.exists():
        try:
            with open(KEYS_PATH) as f:
                return json.load(f).get("peers", {})
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

# ── Session Store ──

class SessionStore:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            peer_pair_id TEXT PRIMARY KEY,
            remote_session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )""")
        self._conn.commit()

    def get(self, pair):
        row = self._conn.execute(
            "SELECT remote_session_id FROM sessions WHERE peer_pair_id=? AND status='active'",
            (pair,)).fetchone()
        return row[0] if row else None

    def save(self, pair, session_id):
        now = now_iso()
        self._conn.execute("""INSERT OR REPLACE INTO sessions
            (peer_pair_id, remote_session_id, created_at, updated_at, status)
            VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE peer_pair_id=?), ?), ?, 'active')""",
            (pair, session_id, pair, now, now))
        self._conn.commit()

    def close(self):
        self._conn.close()

# ── Core Logic (server-side) ──

class DualPlaneServer:
    def __init__(self, node_id=None):
        self._keys = load_api_keys()
        self._store = SessionStore()
        self._my_name = node_id or os.environ.get("HMP_NODE_ID", "peer70")
        print(f"DualPlaneServer starting as {self._my_name}")

    def _api_key(self, peer_name):
        info = self._keys.get(peer_name, {})
        return info.get("api_key", "")

    def _get_or_create_session(self, session_id):
        cached = self._store.get(session_id)
        if cached:
            if self._api_call("GET", f"/api/sessions/{cached}"):
                return cached
        result = self._api_call("GET", f"/api/sessions?peer_pair_id={session_id}")
        if result and "data" in result:
            sessions = result.get("data", [])
            if sessions:
                sid = sessions[0].get("id") or sessions[0].get("session", {}).get("id")
                if sid:
                    self._store.save(session_id, sid)
                    return sid
        participants = session_id.split("_")
        create = self._api_call("POST", "/api/sessions", {
            "peer_pair_id": session_id,
            "kind": "peer_conversation",
            "participants": participants,
            "created_by": self._my_name,
        })
        if create:
            sid = create.get("session", {}).get("id") or create.get("id")
            if sid:
                self._store.save(session_id, sid)
                return sid
        return None

    def _api_call(self, method, path, body=None):
        url = f"http://127.0.0.1:8642{path}"
        headers = {"Content-Type": "application/json"}
        key = self._api_key(self._my_name)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        data = json.dumps(body).encode() if body else None
        try:
            r = urlopen(Request(url, data=data, headers=headers, method=method), timeout=10)
            return json.loads(r.read())
        except (HTTPError, URLError) as e:
            return {"error": str(e)}

    def process_message(self, session_id, text, max_tokens=DEFAULT_MAX_TOKENS):
        """SERVER-SIDE: process incoming message with API session + HMP fallback."""
        api_session = self._get_or_create_session(session_id)
        if api_session:
            body = {
                "model": "hermes-agent",
                "messages": [{"role": "user", "content": text}],
                "session_id": api_session,
                "max_tokens": max_tokens,
            }
            result = self._api_call("POST", "/v1/chat/completions", body)
            if "error" not in result and "choices" in result:
                response_text = result["choices"][0].get("message", {}).get("content", "")
                return {
                    "status": "ok",
                    "channel": "api_session",
                    "response": response_text,
                    "session_id": api_session,
                }
        # Fallback: HMP puro
        hmp_body = json.dumps({
            "message_id": new_id("fb"),
            "from": self._my_name, "to": self._my_name,
            "payload": {"text": text}
        }).encode()
        try:
            r = urlopen(Request("http://127.0.0.1:18643/hmp/send",
                data=hmp_body, headers={"Content-Type": "application/json"}), timeout=15)
            hmp_result = json.loads(r.read())
            return {
                "status": "ok",
                "channel": "hmp_fallback",
                "hmp_result": hmp_result,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "channel": "none"}

# ── HTTP Server (threaded) ──

class DualPlaneHandler(BaseHTTPRequestHandler):
    server_instance = None

    def log_message(self, format, *args):
        pass

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode() if length else "{}"
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "invalid_request"})
            return

        try:
            if self.path == "/send":
                session_id = body.get("session_id", body.get("peer_pair_id", ""))
                text = body.get("text", body.get("content", ""))
                max_tk = body.get("max_tokens", 1024)
                if not session_id or not text:
                    self._json(400, {"error": "missing session_id or text"})
                    return
                result = self.server_instance.process_message(session_id, text, max_tk)
                self._json(200, result)
            else:
                self._json(404, {"error": "not_found"})
        except Exception as e:
            self._json(500, {"error": str(e), "trace": "server_error"})

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": "dual-plane", "version": "2.0.0"})
        else:
            self._json(404, {"error": "not_found"})

def run_server(host="0.0.0.0", port=18644, node_id=None):
    server = DualPlaneServer(node_id=node_id)
    DualPlaneHandler.server_instance = server
    srv = ThreadingHTTPServer((host, port), DualPlaneHandler)
    print(f"Dual-Plane Server on {host}:{port} (v2.0.0, node={server._my_name})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()

def send_to_peer(peer_name, text, session_id=None, timeout=120, max_tokens=1024):
    """CLIENT-SIDE: one call to a peer's dual-plane server."""
    ip = PEER_HOSTS.get(peer_name)
    if not ip:
        return {"error": f"unknown_peer: {peer_name}"}
    if not session_id:
        session_id = "_".join(sorted(["peer70", peer_name]))
    body = json.dumps({
        "session_id": session_id,
        "text": text,
        "max_tokens": max_tokens,
    }).encode()
    try:
        r = urlopen(Request(f"http://{ip}:18644/send",
            data=body, headers={"Content-Type": "application/json"}), timeout=timeout)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}
