#!/usr/bin/env python3
"""
HMP — Hermes Mesh Protocol v0.2
Core module: bus, models, errors, client, server.

Zero dependencies (stdlib only: sqlite3, json, http.server, uuid, datetime).
"""

import json
import sqlite3
import uuid
import datetime
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
HMP_VERSION = "1.0"
DEFAULT_DB_DIR = os.path.expanduser("~/.hermes/data/hmp")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "agent_messages.db")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.hermes/hmp-config.json")
DEFAULT_SERVER_PORT = 8643

# ──────────────────────────────────────────────
# Error Codes
# ──────────────────────────────────────────────
ERROR_CODES = {
    "model_unavailable": {"retryable": True},
    "resource_exhausted": {"retryable": True},
    "timeout": {"retryable": True},
    "invalid_request": {"retryable": False},
    "internal_error": {"retryable": True},
    "not_implemented": {"retryable": False},
    "cancelled": {"retryable": False},
}

# Task lifecycle states
STATE_PENDING = "pending"
STATE_QUEUED = "queued"
STATE_DELIVERED = "delivered"
STATE_WORKING = "working"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_NEEDS_INPUT = "needs_input"
STATE_TIMED_OUT = "timed_out"
STATE_CANCELLED = "cancelled"

VALID_STATES = {
    STATE_PENDING, STATE_QUEUED, STATE_DELIVERED, STATE_WORKING,
    STATE_COMPLETED, STATE_FAILED, STATE_NEEDS_INPUT,
    STATE_TIMED_OUT, STATE_CANCELLED,
}

# Terminal states — no transitions allowed from these
TERMINAL_STATES = {STATE_COMPLETED, STATE_FAILED, STATE_TIMED_OUT, STATE_CANCELLED}

# Allowed transitions
TRANSITIONS = {
    STATE_PENDING: [STATE_QUEUED, STATE_WORKING, STATE_CANCELLED],
    STATE_QUEUED: [STATE_DELIVERED, STATE_CANCELLED],
    STATE_DELIVERED: [STATE_WORKING, STATE_FAILED, STATE_TIMED_OUT, STATE_CANCELLED],
    STATE_WORKING: [STATE_COMPLETED, STATE_FAILED, STATE_NEEDS_INPUT, STATE_TIMED_OUT],
    STATE_NEEDS_INPUT: [STATE_WORKING, STATE_CANCELLED],
}

# Message types
MSG_REQUEST = "request"
MSG_RESPONSE = "response"
MSG_HEARTBEAT = "heartbeat"
MSG_ACK = "ack"
MSG_CANCEL = "cancel"
VALID_TYPES = {MSG_REQUEST, MSG_RESPONSE, MSG_HEARTBEAT, MSG_ACK, MSG_CANCEL}

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
def default_config():
    return {
        "peer_name": "peer70",
        "peer_role": "coordinator",
        "cluster_role": "primary",
        "db_path": DEFAULT_DB_PATH,
        "server_port": DEFAULT_SERVER_PORT,
        "timezone": "Europe/Rome",
        "skills": [],
        "max_concurrent_tasks": 3,
        "max_timeout": 300,
        "supported_types": ["research", "query", "delegate"],
        "tasks_per_minute": 10,
        "tags": [],
        "agent_card_ttl": 300,
    }

def load_config(path=DEFAULT_CONFIG_PATH):
    cfg = default_config()
    if os.path.exists(path):
        with open(path) as f:
            user_cfg = json.load(f)
            cfg.update(user_cfg)
    return cfg

# ──────────────────────────────────────────────
# Models / Helpers
# ──────────────────────────────────────────────
def new_message_id():
    return "msg_" + uuid.uuid4().hex[:12]

def now_iso():
    """ISO 8601 timestamp in UTC. Compatible with Python 3.7+ (also 3.12+ where utcnow is deprecated)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def validate_message(msg):
    """Validate required fields. Returns list of errors (empty = valid)."""
    errors = []
    for field in ["hmp_version", "message_id", "idempotency_key", "from", "to", "type", "timestamp"]:
        if field not in msg:
            errors.append(f"Missing required field: {field}")
    if msg.get("type") not in VALID_TYPES:
        errors.append(f"Invalid type: {msg.get('type')}. Must be one of {VALID_TYPES}")
    if not msg.get("from") or not msg.get("to"):
        errors.append("from and to must be non-empty")
    return errors

def build_error(code, message, cause=None, retryable=None, retry_after_s=None):
    err = {"code": code, "message": message}
    if cause:
        err["cause"] = cause
    if retryable is not None:
        err["retryable"] = retryable
    elif code in ERROR_CODES:
        err["retryable"] = ERROR_CODES[code]["retryable"]
    if retry_after_s:
        err["retry_after_s"] = retry_after_s
    return err

def build_ack(in_reply_to, from_peer, to_peer, timeout_confirmed=None):
    return {
        "hmp_version": HMP_VERSION,
        "message_id": new_message_id(),
        "idempotency_key": new_message_id(),
        "in_reply_to": in_reply_to,
        "from": from_peer,
        "to": to_peer,
        "type": MSG_ACK,
        "status": STATE_DELIVERED,
        "timestamp": now_iso(),
        "timeout_confirmed": timeout_confirmed,
    }

def build_heartbeat(message_id, from_peer, to_peer, progress=None, progress_pct=None):
    return {
        "hmp_version": HMP_VERSION,
        "message_id": new_message_id(),
        "idempotency_key": new_message_id(),
        "in_reply_to": message_id,
        "from": from_peer,
        "to": to_peer,
        "type": MSG_HEARTBEAT,
        "status": STATE_WORKING,
        "timestamp": now_iso(),
        "progress": progress,
        "progress_pct": progress_pct,
        "has_progress": progress_pct is not None,
    }


def build_response(in_reply_to, from_peer, to_peer, status, payload=None, error=None):
    """Build a terminal response message (completed/failed)."""
    return {
        "hmp_version": HMP_VERSION,
        "message_id": new_message_id(),
        "idempotency_key": new_message_id(),
        "in_reply_to": in_reply_to,
        "from": from_peer,
        "to": to_peer,
        "type": MSG_RESPONSE,
        "status": status,
        "timestamp": now_iso(),
        "payload": payload or {},
        "error": error,
    }


def build_ack_msg(in_reply_to, from_peer, to_peer, accepted=True, reason=None, timeout_confirmed=None):
    """Build an ACK message confirming or rejecting a task."""
    ack = build_ack(in_reply_to, from_peer, to_peer, timeout_confirmed)
    ack["payload"] = {"accepted": accepted}
    if reason:
        ack["payload"]["reason"] = reason
    return ack


# ──────────────────────────────────────────────
# Peer Registry — DNS-free peer name resolution
# ──────────────────────────────────────────────
DEFAULT_PEER_REGISTRY = {
    "peer70": "http://192.168.178.70:8643",
    "peer84": "http://192.168.178.84:8643",
    "peer105": "http://192.168.178.105:8643",
    "peer106": "http://192.168.178.106:8643",
    "peer128": "http://192.168.178.128:8643",
}


def peer_url(peer_name, registry=None):
    """Resolve a peer name to its HMP URL."""
    reg = registry or DEFAULT_PEER_REGISTRY
    if peer_name in reg:
        return reg[peer_name]
    # Fallback: try peer{num} convention
    if peer_name.startswith("peer") and peer_name[4:].isdigit():
        return f"http://192.168.178.{peer_name[4:]}:8643"
    return None

# ──────────────────────────────────────────────
# HMPBus — SQLite interface
# ──────────────────────────────────────────────
class HMPBus:
    def __init__(self, db_path=None):
        self.db_path = os.path.expanduser(db_path or DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._init_schema()
        self._lock = threading.Lock()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                idempotency_key TEXT NOT NULL,
                in_reply_to TEXT,
                from_peer TEXT NOT NULL,
                to_peer TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                thread_id TEXT,
                correlation_id TEXT,
                routing_path TEXT,
                timeout INTEGER,
                timeout_confirmed INTEGER,
                ttl TEXT,
                payload TEXT,
                error TEXT,
                stats TEXT,
                progress TEXT,
                progress_pct REAL,
                has_progress INTEGER DEFAULT 0,
                cause TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                delivered_at TEXT,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_messages_to_peer_status
                ON messages(to_peer, status);
            CREATE INDEX IF NOT EXISTS idx_messages_correlation
                ON messages(correlation_id);
            CREATE INDEX IF NOT EXISTS idx_messages_thread
                ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created
                ON messages(created_at);
        """)
        self._conn.commit()

    def _row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        for json_field in ["payload", "error", "stats", "routing_path"]:
            if d.get(json_field) and isinstance(d[json_field], str):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    # ── Write operations ──

    def create_message(self, msg):
        """Insert a new message. Returns message_id or error dict for duplicates."""
        with self._lock:
            # Idempotency check
            existing = self._conn.execute(
                "SELECT message_id, status FROM messages WHERE idempotency_key = ?",
                (msg.get("idempotency_key"),)
            ).fetchone()
            if existing:
                return {"duplicate": True, "message_id": existing["message_id"], "status": existing["status"]}

            now = now_iso()
            mid = msg.get("message_id", new_message_id())
            self._conn.execute("""
                INSERT INTO messages
                    (message_id, idempotency_key, in_reply_to, from_peer, to_peer,
                     type, status, thread_id, correlation_id, routing_path,
                     timeout, timeout_confirmed, ttl, payload, error, stats,
                     progress, progress_pct, has_progress, cause,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mid,
                msg.get("idempotency_key", mid),
                msg.get("in_reply_to"),
                msg.get("from"),
                msg.get("to"),
                msg.get("type", MSG_REQUEST),
                msg.get("status", STATE_PENDING),
                msg.get("thread_id"),
                msg.get("correlation_id"),
                json.dumps(msg.get("routing_path")) if msg.get("routing_path") else None,
                msg.get("timeout"),
                msg.get("timeout_confirmed"),
                msg.get("ttl"),
                json.dumps(msg.get("payload")) if msg.get("payload") else None,
                json.dumps(msg.get("error")) if msg.get("error") else None,
                json.dumps(msg.get("stats")) if msg.get("stats") else None,
                msg.get("progress"),
                msg.get("progress_pct"),
                1 if msg.get("progress_pct") is not None else 0,
                msg.get("cause"),
                msg.get("timestamp", now),
                now,
            ))
            self._conn.commit()
            return {"duplicate": False, "message_id": mid}

    def update_status(self, message_id, new_status, **kwargs):
        """Update status and optional fields. Validates transition."""
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            if not row:
                return {"error": "message_not_found"}
            old = row["status"]
            if old == new_status:
                return {"ok": True, "message_id": message_id, "status": new_status}
            if old in TERMINAL_STATES:
                return {"error": f"Invalid transition: {old} is terminal, cannot transition to {new_status}"}
            allowed = TRANSITIONS.get(old, [])
            if new_status not in allowed:
                return {"error": f"Invalid transition: {old} → {new_status}"}

            now = now_iso()
            updates = ["status = ?", "updated_at = ?"]
            params = [new_status, now]

            if new_status == STATE_DELIVERED:
                updates.append("delivered_at = ?")
                params.append(now)
            if new_status in (STATE_COMPLETED, STATE_FAILED):
                updates.append("completed_at = ?")
                params.append(now)
            if "cause" in kwargs:
                updates.append("cause = ?")
                params.append(kwargs["cause"])
            if "error" in kwargs:
                updates.append("error = ?")
                params.append(json.dumps(kwargs["error"]))
            if "progress" in kwargs:
                updates.append("progress = ?")
                params.append(kwargs["progress"])
            if "progress_pct" in kwargs:
                updates.append("progress_pct = ?")
                params.append(kwargs["progress_pct"])
                updates.append("has_progress = ?")
                params.append(1 if kwargs["progress_pct"] is not None else 0)
            if "payload" in kwargs:
                updates.append("payload = ?")
                params.append(json.dumps(kwargs["payload"]))

            params.append(message_id)
            query = f"UPDATE messages SET {', '.join(updates)} WHERE message_id = ?"
            self._conn.execute(query, params)
            self._conn.commit()
            return {"ok": True, "message_id": message_id, "status": new_status}

    def update_heartbeat(self, message_id, progress, progress_pct=None):
        """Quick heartbeat update (lightweight path)."""
        with self._lock:
            now = now_iso()
            self._conn.execute(
                "UPDATE messages SET progress=?, progress_pct=?, has_progress=?, updated_at=? WHERE message_id=?",
                (progress, progress_pct, 1 if progress_pct is not None else 0, now, message_id)
            )
            self._conn.commit()

    # ── Read operations ──

    def get_message(self, message_id):
        row = self._conn.execute(
            "SELECT * FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def get_pending(self, to_peer=None, limit=50):
        """Get messages in pending or queued state."""
        if to_peer:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE to_peer = ? AND status IN (?, ?) ORDER BY created_at ASC LIMIT ?",
                (to_peer, STATE_PENDING, STATE_QUEUED, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE status IN (?, ?) ORDER BY created_at ASC LIMIT ?",
                (STATE_PENDING, STATE_QUEUED, limit)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_working(self):
        """Get messages in working state."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE status = ? ORDER BY updated_at ASC",
            (STATE_WORKING,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_stalled(self, max_age_seconds=300):
        """Get messages in working state with no heartbeat update for > max_age_seconds."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max_age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE status = ? AND updated_at < ? ORDER BY updated_at ASC",
            (STATE_WORKING, cutoff)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_thread(self, thread_id, limit=50):
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC LIMIT ?",
            (thread_id, limit)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_old_messages(self, days=30):
        """Get messages older than N days for cleanup."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self._conn.execute(
            "SELECT message_id FROM messages WHERE created_at < ?",
            (cutoff,)
        ).fetchall()
        return [r["message_id"] for r in rows]

    def count_pending(self):
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE status IN (?, ?)",
            (STATE_PENDING, STATE_QUEUED)
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Maintenance ──

    def archive_old_messages(self, days=30):
        """Delete messages older than N days that are in terminal states."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        terminal = [STATE_COMPLETED, STATE_FAILED, STATE_TIMED_OUT, STATE_CANCELLED]
        placeholders = ",".join("?" for _ in terminal)
        with self._lock:
            deleted = self._conn.execute(
                f"DELETE FROM messages WHERE created_at < ? AND status IN ({placeholders})",
                [cutoff] + terminal
            ).rowcount
            self._conn.commit()
            return deleted

    def cleanup_idempotency_keys(self, days=7):
        """Delete idempotency records older than N days to keep the table lean."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            deleted = self._conn.execute(
                "DELETE FROM messages WHERE created_at < ? AND idempotency_key IS NOT NULL",
                (cutoff,)
            ).rowcount
            self._conn.commit()
            return deleted

    def compact(self):
        """Run VACUUM to reclaim space."""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            self._conn.execute("VACUUM;")
            return True

    def close(self):
        self._conn.close()

# ──────────────────────────────────────────────
# HMPClient — for non-coordinator peers
# ──────────────────────────────────────────────
class HMPClient:
    def __init__(self, coordinator_url="http://peer70:8643"):
        self.coordinator_url = coordinator_url.rstrip("/")

    def send_message(self, msg, timeout=30):
        url = f"{self.coordinator_url}/hmp/send"
        data = json.dumps(msg).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            body = e.read().decode()
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"error": f"HTTP {e.code}", "body": body}
        except URLError as e:
            return {"error": str(e.reason)}

    def poll_message(self, message_id, timeout=30):
        url = f"{self.coordinator_url}/hmp/poll/{message_id}"
        try:
            with urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            return {"error": f"HTTP {e.code}"}
        except URLError as e:
            return {"error": str(e.reason)}

    def discover_peers(self, timeout=30):
        url = f"{self.coordinator_url}/hmp/discover"
        try:
            with urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (HTTPError, URLError) as e:
            return {"error": str(e)}

    def get_agent_card(self, peer_url=None, timeout=30):
        url = peer_url or self.coordinator_url
        url = url.rstrip("/") + "/hmp/agent-card"
        try:
            with urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (HTTPError, URLError) as e:
            return {"error": str(e)}

    def cancel_message(self, message_id, from_peer, timeout=30):
        url = f"{self.coordinator_url}/hmp/cancel/{message_id}"
        data = json.dumps({"from": from_peer}).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            return {"error": f"HTTP {e.code}"}


# ──────────────────────────────────────────────
# HMPWorker — agent loop per-peer
# ──────────────────────────────────────────────
class HMPWorker:
    """Polls the local HMP bus, processes pending messages, sends ACK/responses."""

    def __init__(self, bus, config, client=None, poll_interval=5):
        self.bus = bus
        self.config = config
        self.peer_name = config.get("peer_name", "unknown")
        self.supported_types = set(config.get("supported_types", []))
        self.poll_interval = poll_interval
        self.client = client or HMPClient()
        self._running = False
        self._thread = None
        # Handler registry: payload_type -> callable(msg) -> (status, payload, error)
        self.handlers = {}

    def register_handler(self, payload_type, fn):
        """Register a handler for a specific payload.type.
           fn receives (message_dict) and returns (status, payload_dict, error_dict_or_None)."""
        self.handlers[payload_type] = fn

    def _send_to_peer(self, msg):
        """Send a message to the target peer's HMP server."""
        url = peer_url(msg["to"])
        if not url:
            print(f"  [WORKER] Cannot resolve peer: {msg['to']}")
            return None
        try:
            client = HMPClient(coordinator_url=url)
            return client.send_message(msg)
        except Exception as e:
            print(f"  [WORKER] Send failed to {msg['to']}: {e}")
            return None

    def _process_message(self, msg):
        """Process a single pending message. Returns True if handled."""
        mid = msg["message_id"]
        sender = msg.get("from_peer", msg.get("from", "unknown"))
        payload = msg.get("payload", {})
        ptype = payload.get("type", "") if isinstance(payload, dict) else ""

        print(f"  [WORKER] Processing {mid} from {sender}, type={ptype}")

        # 1. Capability validation
        if ptype and self.supported_types and ptype not in self.supported_types:
            reason = f"Unsupported payload type: {ptype}. Supported: {sorted(self.supported_types)}"
            print(f"  [WORKER] Rejecting: {reason}")
            # Send failed response back to sender
            resp = build_response(mid, self.peer_name, sender, STATE_FAILED,
                                  error={"code": "not_implemented", "message": reason})
            self._send_to_peer(resp)
            self.bus.update_status(mid, STATE_FAILED, cause=reason)
            return False

        # 2. Send ACK
        ack = build_ack_msg(mid, self.peer_name, sender,
                            accepted=True,
                            timeout_confirmed=msg.get("timeout"))
        ack_result = self._send_to_peer(ack)
        print(f"  [WORKER] ACK sent: {ack_result}")

        # 3. Update local status to working
        self.bus.update_status(mid, STATE_WORKING, progress="accepted", progress_pct=0)

        # 4. Route to registered handler or default handler
        handler = self.handlers.get(ptype) if ptype else None
        try:
            if handler:
                result_status, result_payload, result_error = handler(msg)
            else:
                result_status, result_payload, result_error = self._default_handler(msg)
        except Exception as e:
            print(f"  [WORKER] Handler exception: {e}")
            result_status, result_payload, result_error = STATE_FAILED, {}, \
                {"code": "internal_error", "message": str(e)}

        # 5. Send terminal response
        resp = build_response(mid, self.peer_name, sender, result_status,
                              payload=result_payload, error=result_error)
        self._send_to_peer(resp)
        self.bus.update_status(mid, result_status,
                               payload=result_payload,
                               error=result_error,
                               progress="done" if result_status == STATE_COMPLETED else result_status,
                               progress_pct=100 if result_status == STATE_COMPLETED else None)
        print(f"  [WORKER] Done: {mid} -> {result_status}")
        return True

    def _default_handler(self, msg):
        """Default handler: echo pong for ping, acknowledge for others."""
        payload = msg.get("payload", {})
        ptype = payload.get("type", "") if isinstance(payload, dict) else ""
        action = payload.get("action", "") if isinstance(payload, dict) else ""

        if ptype == "ping" or action == "ping":
            return STATE_COMPLETED, {"type": "pong", "echo": payload}, None

        if ptype == "health_report":
            # Health reports are one-way; just acknowledge
            return STATE_COMPLETED, {"type": "acknowledged", "original": ptype}, None

        if ptype == "code_review":
            return STATE_COMPLETED, {"type": "review_received", "status": "read"}, None

        if ptype and not self.supported_types:
            # No supported_types configured — accept everything
            return STATE_COMPLETED, {"type": "acknowledged", "original": ptype}, None

        return STATE_COMPLETED, {"type": "acknowledged", "original": ptype}, None

    def poll_once(self):
        """Poll and process pending messages. Returns count processed."""
        pending = self.bus.get_pending(to_peer=self.peer_name, limit=10)
        processed = 0
        for msg in pending:
            try:
                if self._process_message(msg):
                    processed += 1
            except Exception as e:
                print(f"  [WORKER] Error processing {msg.get('message_id','?')}: {e}")
        return processed

    def run_forever(self):
        """Main loop: poll -> process -> sleep."""
        self._running = True
        print(f"[WORKER] Starting on {self.peer_name}, poll every {self.poll_interval}s")
        print(f"         Supported types: {sorted(self.supported_types) if self.supported_types else '(all)'}")
        while self._running:
            try:
                count = self.poll_once()
                if count:
                    print(f"[WORKER] Processed {count} message(s)")
            except Exception as e:
                print(f"[WORKER] Poll error: {e}")
            threading.Event().wait(self.poll_interval)

    def start(self, daemon=True):
        """Start worker in background thread."""
        self._thread = threading.Thread(target=self.run_forever, daemon=daemon)
        self._thread.start()
        return self._thread

    def stop(self):
        self._running = False


# ──────────────────────────────────────────────
# HMPCoordinator — timeout enforcement on peer70
# ──────────────────────────────────────────────
class HMPCoordinator:
    """Monitors message lifecycle on the coordinator bus:
       - stale deliveries (no ACK within ACK_TIMEOUT)
       - stale workers (no heartbeat within configured timeout)
       - max_timeout exceeded
    """

    def __init__(self, bus, config, poll_interval=15, ack_timeout=15):
        self.bus = bus
        self.config = config
        self.peer_name = config.get("peer_name", "unknown")
        self.max_timeout = config.get("max_timeout", 300)
        self.poll_interval = poll_interval
        self.ack_timeout = ack_timeout
        self._running = False
        self._thread = None

    def check_stale_deliveries(self):
        """Find messages delivered to this peer that never got an ACK response."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(seconds=self.ack_timeout)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale = self.bus._conn.execute(
            """SELECT m.* FROM messages m
               WHERE m.to_peer = ? AND m.status = 'pending'
               AND m.created_at < ?
               AND m.message_id NOT IN (
                   SELECT r.in_reply_to FROM messages r WHERE r.type = 'ack'
               )
               LIMIT 20""",
            (self.peer_name, cutoff)
        ).fetchall()
        return [self.bus._row_to_dict(r) for r in stale]

    def check_stale_workers(self):
        """Find outgoing messages that are working but past their timeout."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(seconds=self.max_timeout)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale = self.bus._conn.execute(
            """SELECT * FROM messages
               WHERE from_peer = ? AND status = 'working' AND updated_at < ?
               LIMIT 20""",
            (self.peer_name, cutoff)
        ).fetchall()
        return [self.bus._row_to_dict(r) for r in stale]

    def check_timed_out(self):
        """Find outgoing messages past max_timeout in any pre-terminal state."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(seconds=self.max_timeout)).strftime("%Y-%m-%dT%H:%M:%SZ")
        timed_out = self.bus._conn.execute(
            """SELECT * FROM messages
               WHERE from_peer = ? AND status NOT IN ('completed','failed','timed_out','cancelled')
               AND created_at < ?
               LIMIT 20""",
            (self.peer_name, cutoff)
        ).fetchall()
        return [self.bus._row_to_dict(r) for r in timed_out]

    def run_cycle(self):
        """One full enforcement cycle."""
        # Stale deliveries (messages sent TO us that no agent picked up)
        stale_deliveries = self.check_stale_deliveries()
        for msg in stale_deliveries:
            print(f"  [COORD] Stale delivery: {msg['message_id']} from {msg['from_peer']}")
            self.bus.update_status(msg["message_id"], STATE_TIMED_OUT,
                                   cause=f"No ACK within {self.ack_timeout}s")

        # Stale workers (messages WE sent that are working but past timeout)
        stale_workers = self.check_stale_workers()
        for msg in stale_workers:
            print(f"  [COORD] Stale worker: {msg['message_id']} to {msg['to_peer']}")
            self.bus.update_status(msg["message_id"], STATE_TIMED_OUT,
                                   cause=f"No completion within {self.max_timeout}s")

        # Timed out (messages WE sent that never completed)
        timed_out = self.check_timed_out()
        for msg in timed_out:
            if msg["message_id"] not in {m["message_id"] for m in stale_workers}:
                print(f"  [COORD] Timed out: {msg['message_id']} to {msg['to_peer']}")
                self.bus.update_status(msg["message_id"], STATE_TIMED_OUT,
                                       cause=f"Exceeded max_timeout ({self.max_timeout}s)")

        total = len(stale_deliveries) + len(stale_workers) + len(timed_out)
        if total:
            print(f"[COORD] Enforced {total} timeout(s)")
        return total

    def run_forever(self):
        self._running = True
        print(f"[COORD] Starting on {self.peer_name}, timeout={self.max_timeout}s, ack_window={self.ack_timeout}s")
        while self._running:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"[COORD] Cycle error: {e}")
            threading.Event().wait(self.poll_interval)

    def start(self, daemon=True):
        self._thread = threading.Thread(target=self.run_forever, daemon=daemon)
        self._thread.start()
        return self._thread

    def stop(self):
        self._running = False

# ──────────────────────────────────────────────
# HMPServer — HTTP endpoints
# ──────────────────────────────────────────────
AGENT_CARD_CACHE = {}

class HMPRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for HMP endpoints. Runs alongside Hermes API on a separate port."""

    # Shared bus instance (set by HMPServer)
    bus = None
    config = None
    agent_card = None

    def log_message(self, format, *args):
        """Log to stderr with timestamp. Overrides BaseHTTPRequestHandler default."""
        import sys
        timestamp = now_iso()
        sys.stderr.write(f"[HMP {timestamp}] {self.address_string()} - {format % args}\n")

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/health":
            self._send_json({"status": "ok", "service": "hmp", "version": HMP_VERSION})

        elif path == "/hmp/agent-card":
            self._send_json(self.agent_card or {})

        elif path == "/hmp/discover":
            # For now, return our own card. In future: cached cards from all peers.
            self._send_json({"peers": [self.agent_card]})

        elif path.startswith("/hmp/poll/"):
            message_id = path[len("/hmp/poll/"):]
            msg = self.bus.get_message(message_id)
            if msg:
                self._send_json(msg)
            else:
                self._send_json({"error": "message_not_found"}, 404)

        else:
            self._send_json({"error": "not_found"}, 404)

    def do_POST(self):
        path = self.path.rstrip("/")
        body = self._read_body()
        if body is None:
            self._send_json({"error": "invalid_json", "cause": "invalid_request"}, 400)
            return

        if path == "/hmp/send":
            errors = validate_message(body)
            if errors:
                self._send_json({"error": "validation_failed", "errors": errors}, 400)
                return
            result = self.bus.create_message(body)
            status = 200 if not result.get("duplicate") else 200
            self._send_json(result, status)

        elif path.startswith("/hmp/cancel/"):
            message_id = path[len("/hmp/cancel/"):]
            msg = self.bus.get_message(message_id)
            if not msg:
                self._send_json({"error": "message_not_found"}, 404)
                return
            canceller = body.get("from", "unknown")
            if msg["status"] not in (STATE_PENDING, STATE_QUEUED, STATE_DELIVERED, STATE_NEEDS_INPUT):
                self._send_json({
                    "error": "cannot_cancel",
                    "message": f"Message in state {msg['status']} cannot be cancelled"
                }, 409)
                return
            result = self.bus.update_status(message_id, STATE_CANCELLED, cause=f"Cancelled by {canceller}")
            self._send_json(result)

        else:
            self._send_json({"error": "not_found"}, 404)

class ThreadingHMPHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server for HMP. Handles concurrent requests."""
    daemon_threads = True
    allow_reuse_address = True


class HMPServer:
    """HTTP server for HMP protocol."""

    def __init__(self, bus, config, host="0.0.0.0", port=None):
        self.bus = bus
        self.config = config
        self.host = host
        self.port = port or int(config.get("server_port", DEFAULT_SERVER_PORT))
        self._httpd = None
        self._thread = None
        self._build_agent_card()

    def _build_agent_card(self):
        self.agent_card = {
            "agent": self.config.get("peer_name", "unknown"),
            "role": self.config.get("peer_role", "worker"),
            "cluster_role": self.config.get("cluster_role", "observer"),
            "version": f"hmp-{HMP_VERSION}",
            "timezone": self.config.get("timezone", "UTC"),
            "skills": self.config.get("skills", []),
            "constraints": {
                "max_concurrent_tasks": self.config.get("max_concurrent_tasks", 1),
                "max_timeout": self.config.get("max_timeout", 180),
                "supported_types": self.config.get("supported_types", []),
                "availability_window": self.config.get("availability_window", {"always_available": True}),
            },
            "rate_limits": {
                "max_concurrent_tasks": self.config.get("max_concurrent_tasks", 1),
                "tasks_per_minute": self.config.get("tasks_per_minute", 3),
            },
            "tags": self.config.get("tags", []),
            "health": "/health",
            "agent_card_ttl": self.config.get("agent_card_ttl", 300),
        }

    def start(self):
        HMPRequestHandler.bus = self.bus
        HMPRequestHandler.config = self.config
        HMPRequestHandler.agent_card = self.agent_card

        self._httpd = ThreadingHMPHTTPServer((self.host, self.port), HMPRequestHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self._httpd, self._thread

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()

# ──────────────────────────────────────────────
# Cron helper — shared logic for cron scripts
# ──────────────────────────────────────────────
def init_cron(db_path=None):
    """Initialize bus for cron scripts. Returns (bus, config)."""
    cfg_path = os.environ.get("HMP_CONFIG", DEFAULT_CONFIG_PATH)
    config = load_config(cfg_path)
    bus = HMPBus(db_path or config.get("db_path", DEFAULT_DB_PATH))
    return bus, config

# ──────────────────────────────────────────────
# Command-line entry point
# ──────────────────────────────────────────────
def main():
    """Run HMP component: server, worker, or coordinator."""
    import sys
    config = load_config()

    if len(sys.argv) < 2:
        print("Usage: hmp.py <command> [args]")
        print("Commands:")
        print("  server [port]        — Run HMP HTTP server")
        print("  worker               — Run HMP worker agent (poll + ACK + process)")
        print("  coordinator          — Run HMP timeout enforcer (peer70 only)")
        print("  once                 — Poll and process pending messages once")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "server":
        bus = HMPBus()
        port = int(sys.argv[2]) if len(sys.argv) > 2 else config.get("server_port", DEFAULT_SERVER_PORT)
        server = HMPServer(bus, config, port=port)
        httpd, thread = server.start()
        print(f"HMP server running on port {port} (peer: {config.get('peer_name', 'unknown')})")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.shutdown()
            bus.close()

    elif cmd == "worker":
        bus = HMPBus()
        client = HMPClient()
        worker = HMPWorker(bus, config, client=client)
        print(f"HMP worker starting for peer: {config.get('peer_name', 'unknown')}")
        worker.run_forever()

    elif cmd == "coordinator":
        bus = HMPBus()
        coordinator = HMPCoordinator(bus, config)
        print(f"HMP coordinator starting for peer: {config.get('peer_name', 'unknown')}")
        coordinator.run_forever()

    elif cmd == "once":
        bus = HMPBus()
        client = HMPClient()
        worker = HMPWorker(bus, config, client=client)
        count = worker.poll_once()
        print(f"Processed {count} message(s)")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()