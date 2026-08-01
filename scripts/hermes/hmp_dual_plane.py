#!/usr/bin/env python3
"""
HMP Dual-Plane v2.0.0 — Full version (Hermes Agent)
====================================================
Extends hmp_dual_plane_light.py with Hermes API sessions and agent.
Adds: SQLite SessionStore, Hermes API /api/sessions, /v1/chat/completions.
"""
import json, time, os, sys, sqlite3
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ── Capability Reuse event store integration ──
try:
    SKILL_DIR = Path.home() / ".hermes" / "skills" / "hermes" / "capability-reuse" / "plugin"
    if SKILL_DIR.exists() and str(SKILL_DIR) not in sys.path:
        sys.path.insert(0, str(SKILL_DIR))
    from event_store import emit_retrieval, emit_observation, emit_execute_code_start, emit_execute_code_complete
    HAS_EVENT_STORE = True
except ImportError:
    HAS_EVENT_STORE = False

# ── Import base from light version ──
BASE_DIR = Path(__file__).parent.resolve()
import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import everything from the light module
from hmp_dual_plane_light import (
    VERSION as LIGHT_VERSION,
    now_iso, new_id, MAX_CONTEXT,
    ContextStore, LLMInterface,    # base classes
    LightDualPlaneServer,          # will extend
    LightDualPlaneHandler,         # will extend
    run_server as light_run_server, # will wrap
)

VERSION = "2.0.0"
DB_PATH = Path.home() / ".hermes" / "data" / "hmp" / "dual-plane.db"
KEYS_PATH = Path.home() / ".hermes" / "peer-network" / "peer-api-keys.json"
PEER_HOSTS = {
    "peer70":  "127.0.0.1",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer58":  "192.168.178.58",
    "peer136": "192.168.178.136",
    "peer128": "192.168.178.112",
}

# ── Override: Hermes API LLM ──

class HermesLLM(LLMInterface):
    """LLM backend via Hermes API chat completions with session support."""

    def __init__(self, node_id="peer70"):
        super().__init__()
        self._my_name = node_id
        self._keys = self._load_keys()

    def _load_keys(self):
        if KEYS_PATH.exists():
            try:
                with open(KEYS_PATH) as f:
                    return json.load(f).get("peers", {})
            except: return {}
        return {}

    def _api_key(self, peer_name):
        info = self._keys.get(peer_name, {})
        return info.get("api_key", "")

    def ask_with_session(self, session_id, text, max_tokens=1024):
        """Send via Hermes /v1/chat/completions with session context."""
        key = self._api_key(self._my_name)
        body = json.dumps({
            "model": "hermes-agent",
            "messages": [{"role": "user", "content": text}],
            "session_id": session_id,
            "max_tokens": max_tokens,
        }).encode()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            r = urlopen(Request("http://127.0.0.1:8642/v1/chat/completions",
                data=body, headers=headers), timeout=60)
            result = json.loads(r.read())
            return result["choices"][0].get("message", {}).get("content", "")
        except Exception as e:
            return f"Errore Hermes: {e}"

# ── Override: SQLite SessionStore ──

class SessionStore(ContextStore):
    """
    Persistent session store via SQLite with WAL.
    Extends ContextStore with SQLite-backed session_id → remote_session_id mapping.
    """

    def __init__(self, db_path=None):
        super().__init__()
        self.db_path = str(db_path or DB_PATH)
        basedir = os.path.dirname(self.db_path)
        if basedir:
            os.makedirs(basedir, exist_ok=True)
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

    def get_remote_session(self, pair):
        row = self._conn.execute(
            "SELECT remote_session_id FROM sessions WHERE peer_pair_id=? AND status='active'",
            (pair,)).fetchone()
        return row[0] if row else None

    def save_remote_session(self, pair, session_id):
        now = now_iso()
        self._conn.execute("""INSERT OR REPLACE INTO sessions
            (peer_pair_id, remote_session_id, created_at, updated_at, status)
            VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE peer_pair_id=?), ?), ?, 'active')""",
            (pair, session_id, pair, now, now))
        self._conn.commit()

# ── Override: Full Dual-Plane Server ──

class DualPlaneServer(LightDualPlaneServer):
    """Full dual-plane server with Hermes API sessions."""

    def __init__(self, node_id=None):
        self._my_name = node_id or os.environ.get("HMP_NODE_ID", "peer70")
        self._context = SessionStore()          # SQLite-backed
        self._llm = HermesLLM(node_id=self._my_name)  # Hermes Agent
        self._api_keys = self._load_keys()
        print(f"DualPlaneServer starting as {self._my_name}")

    def _load_keys(self):
        if KEYS_PATH.exists():
            try:
                with open(KEYS_PATH) as f:
                    return json.load(f).get("peers", {})
            except: return {}
        return {}

    def _api_key(self, peer_name):
        info = self._api_keys.get(peer_name, {})
        return info.get("api_key", "")

    def _api_call(self, method, path, body=None):
        """Call Hermes API on localhost."""
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

    def _get_or_create_session(self, session_id):
        cached = self._context.get_remote_session(session_id)
        if cached:
            if self._api_call("GET", f"/api/sessions/{cached}"):
                return cached
        result = self._api_call("GET", f"/api/sessions?peer_pair_id={session_id}")
        if result and "data" in result:
            sessions = result.get("data", [])
            if sessions:
                sid = sessions[0].get("id") or sessions[0].get("session", {}).get("id")
                if sid:
                    self._context.save_remote_session(session_id, sid)
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
                self._context.save_remote_session(session_id, sid)
                return sid
        return None

    def process_message(self, session_id, text):
        """Full version: Hermes API session → chat completions → HMP fallback.
        Integrated with capability-reuse event_store for live-shadow data acquisition."""

        # ── LIVE-SHADOW: emit retrieval event ──
        if HAS_EVENT_STORE:
            emit_retrieval(
                session_id=session_id,
                user_message_preview=text[:200],
                candidates=[],
                top_score=0.0,
                intervened=False,
                latency_ms=0.0,
            )
            ec_id = emit_execute_code_start(
                code_preview=f"dual-plane: {text[:100]}",
                session_id=session_id,
            )
        else:
            ec_id = None

        api_session = self._get_or_create_session(session_id)
        if api_session:
            try:
                response = self._llm.ask_with_session(api_session, text)
                # ── LIVE-SHADOW: emit observation ──
                if HAS_EVENT_STORE and ec_id:
                    emit_execute_code_complete(
                        code_hash=ec_id,
                        outcome="success",
                        duration_ms=0.0,
                    )
                    emit_observation(
                        capability_id="dual-plane",
                        capability_version=VERSION,
                        effect_class="read_only",
                    )
                return {
                    "status": "ok",
                    "channel": "api_session",
                    "response": response,
                    "session_id": api_session,
                }
            except Exception:
                pass

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
            # ── LIVE-SHADOW: emit fallback outcome ──
            if HAS_EVENT_STORE and ec_id:
                emit_execute_code_complete(
                    code_hash=ec_id,
                    outcome="success" if "error" not in hmp_result else "failure",
                    duration_ms=0.0,
                )
            return {"status": "ok", "channel": "hmp_fallback", "hmp_result": hmp_result}
        except Exception as e:
            if HAS_EVENT_STORE and ec_id:
                emit_execute_code_complete(
                    code_hash=ec_id,
                    outcome="failure",
                    error=str(e),
                )
            return {"status": "error", "error": str(e), "channel": "none"}

# ── Override: HTTP Handler ──

class DualPlaneHandler(LightDualPlaneHandler):
    """Same handler, reports full version info."""
    SERVICE_NAME = "dual-plane"
    SERVICE_VERSION = VERSION

# ── Override: Client ──

def send_to_peer(peer_name, text, session_id=None, timeout=120, max_tokens=1024):
    """CLIENT: one call to any peer's :18644."""
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

def run_server(host="0.0.0.0", port=18644, node_id=None):
    """Start the full dual-plane server."""
    server = DualPlaneServer(node_id=node_id)
    DualPlaneHandler.server_instance = server
    srv = ThreadingHTTPServer((host, port), DualPlaneHandler)
    print(f"Dual-Plane Server on {host}:{port} (v{VERSION}, node={server._my_name})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
