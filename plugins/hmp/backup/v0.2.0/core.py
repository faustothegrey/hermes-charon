"""Small reusable core for the HMP Hermes gateway adapter.

This module intentionally contains protocol/status-store helpers, keeping
adapter.py focused on Hermes gateway glue.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

try:
    from hermes_constants import get_hermes_home
except Exception:  # pragma: no cover - fallback for standalone import tests
    def get_hermes_home():  # type: ignore
        return Path.home() / ".hermes"


DEFAULT_DB_PATH = str(get_hermes_home() / "data" / "hmp_gateway_plugin" / "messages.db")


def now_ts() -> float:
    return time.time()


def make_message_id(prefix: str = "hmp") -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:16])


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def extract_peer(body: Dict[str, Any]) -> str:
    return str(
        body.get("from")
        or body.get("from_peer")
        or body.get("peer")
        or body.get("sender")
        or "unknown"
    )


def extract_text(body: Dict[str, Any]) -> str:
    payload = body.get("payload")
    if isinstance(payload, dict):
        for key in ("text", "content", "message", "query"):
            value = payload.get(key)
            if value is not None:
                return str(value)
    for key in ("text", "content", "message", "query"):
        value = body.get(key)
        if value is not None:
            return str(value)
    return ""


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_loads(text: Optional[str], default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


# ── In-memory SSE event store ────────────────────────────────────────────

class SSEEvent:
    """A single SSE event to push to subscribers."""
    def __init__(self, event_type: str, data: str) -> None:
        self.event_type = event_type
        self.data = data


class SSEStreamStore:
    """In-memory asyncio.Queue per message_id for live progress streaming.

    Each message gets a queue.  When the producer pushes events, all
    subscribers (SSE connections) receive them in real time.  After the
    final "*done*" event the queue is cleaned up.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue[Optional[SSEEvent]]] = {}
        self._lock = asyncio.Lock()

    async def _queue(self, message_id: str) -> asyncio.Queue:
        async with self._lock:
            if message_id not in self._queues:
                self._queues[message_id] = asyncio.Queue()
            return self._queues[message_id]

    async def push_progress(self, message_id: str, text: str) -> None:
        """Push a progress event for live streaming."""
        q = await self._queue(message_id)
        await q.put(SSEEvent("progress", text))

    async def push_complete(self, message_id: str, text: str) -> None:
        """Push the final result and signal end-of-stream."""
        q = await self._queue(message_id)
        await q.put(SSEEvent("complete", text))
        await q.put(None)  # sentinel: stream should close

    async def push_error(self, message_id: str, error: str) -> None:
        q = await self._queue(message_id)
        await q.put(SSEEvent("error", error))
        await q.put(None)

    async def subscribe(self, message_id: str) -> AsyncIterator[SSEEvent]:
        """Async generator: yields SSE events as they arrive, stops on None."""
        q = await self._queue(message_id)
        while True:
            event = await q.get()
            if event is None:
                break
            yield event

    async def cleanup(self, message_id: str) -> None:
        """Remove the queue after stream is done."""
        async with self._lock:
            self._queues.pop(message_id, None)


# ── SQLite status store (unchanged semantics) ────────────────────────────

class HMPStatusStore(object):
    """SQLite-backed request/response status store for HMP messages."""

    def __init__(self, path: str = DEFAULT_DB_PATH) -> None:
        self.path = str(Path(path).expanduser())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hmp_gateway_messages (
                    message_id TEXT PRIMARY KEY,
                    idempotency_key TEXT,
                    from_peer TEXT,
                    to_peer TEXT,
                    chat_id TEXT,
                    text TEXT,
                    status TEXT NOT NULL,
                    response_text TEXT,
                    error TEXT,
                    raw_json TEXT,
                    accepted_at REAL,
                    updated_at REAL,
                    completed_at REAL,
                    sent_to_chat_id TEXT,
                    response_message_id TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hmp_gateway_idempotency ON hmp_gateway_messages(idempotency_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hmp_gateway_status ON hmp_gateway_messages(status)"
            )

    def get_by_idempotency_key(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hmp_gateway_messages WHERE idempotency_key = ? ORDER BY accepted_at DESC LIMIT 1",
                (key,),
            ).fetchone()
        return self._row_to_dict(row)

    def accept(self, message_id: str, body: Dict[str, Any], from_peer: str, to_peer: str, text: str) -> Dict[str, Any]:
        ts = now_ts()
        idempotency_key = str(body.get("idempotency_key") or message_id)
        chat_id = from_peer
        raw_json = json_dumps(body)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO hmp_gateway_messages
                (message_id, idempotency_key, from_peer, to_peer, chat_id, text, status, response_text,
                 error, raw_json, accepted_at, updated_at, completed_at, sent_to_chat_id, response_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, NULL)
                """,
                (message_id, idempotency_key, from_peer, to_peer, chat_id, text, "accepted", raw_json, ts, ts),
            )
        return self.get(message_id) or {"message_id": message_id, "status": "accepted"}

    def mark_status(self, message_id: str, status: str, error: Optional[str] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE hmp_gateway_messages SET status = ?, error = ?, updated_at = ? WHERE message_id = ?",
                (status, error, now_ts(), message_id),
            )

    def complete(self, message_id: str, response_text: str, sent_to_chat_id: str, response_message_id: str) -> None:
        ts = now_ts()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE hmp_gateway_messages
                SET status = ?, response_text = ?, sent_to_chat_id = ?, response_message_id = ?,
                    updated_at = ?, completed_at = ?
                WHERE message_id = ?
                """,
                ("completed", response_text, sent_to_chat_id, response_message_id, ts, ts, message_id),
            )

    def fail(self, message_id: str, error: str) -> None:
        self.mark_status(message_id, "failed", error=error)

    def get(self, message_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hmp_gateway_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def _row_to_dict(self, row: Any) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["raw"] = json_loads(item.pop("raw_json", None), default={})
        return item
