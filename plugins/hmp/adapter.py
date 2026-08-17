"""HMP platform adapter for Hermes Gateway.

This adapter owns a small HTTP listener and converts inbound HMP requests into
Hermes MessageEvent objects.  The important reliability property is that
/hmp/send calls BasePlatformAdapter.handle_message(), so message execution is
performed by the normal gateway session machinery rather than by an external
DB-polling worker or `hermes chat` subprocess.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult

from .core import (
    DEFAULT_DB_PATH,
    HMPStatusStore,
    extract_peer,
    extract_text,
    make_message_id,
    truthy,
)

# ── Capability Reuse event store integration (dual-plane parity) ──
# Resolution order (G2b/G0 review blocker fix, 2026-08-17):
#   1. CANONICAL runtime plugin path first:  $HERMES_HOME/plugins/capability-reuse
#      (profile-safe via get_hermes_home() when available). This is where the
#      accepted v2.6.0 artifact lives; the legacy skills copy may be stale.
#   2. LEGACY fallback ONLY if compatible:  $HERMES_HOME/skills/hermes/
#      capability-reuse/plugin — used only when it exposes the full G0/G2b
#      event-store surface (emit_retrieval, emit_observation,
#      emit_surface_execution_start, emit_surface_execution_complete).
#      A legacy copy at v2.2.0 (missing surface fns) is NOT used → the adapter
#      degrades cleanly (HAS_EVENT_STORE=False) instead of crashing at runtime.

def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore
        return Path(get_hermes_home())
    except Exception:
        return Path.home() / ".hermes"


_EVENT_STORE_REQUIRED = (
    "emit_retrieval",
    "emit_observation",
    "emit_surface_execution_start",
    "emit_surface_execution_complete",
)


def _try_load_event_store(candidate_dir: Path):
    """Import event_store from candidate_dir if it exposes the full surface.

    Returns the module, or None when the candidate is missing/incompatible.
    sys.path is only mutated for a candidate that actually passes the surface
    check, so a stale legacy copy cannot shadow the canonical one.
    """
    if not candidate_dir or not candidate_dir.exists():
        return None
    module_file = candidate_dir / "event_store.py"
    if not module_file.exists():
        return None
    if str(candidate_dir) not in sys.path:
        sys.path.insert(0, str(candidate_dir))
    try:
        import event_store  # type: ignore
    except Exception:
        return None
    if all(hasattr(event_store, name) for name in _EVENT_STORE_REQUIRED):
        return event_store
    return None


_HERMES_HOME = _hermes_home()
_event_store_module = (
    _try_load_event_store(_HERMES_HOME / "plugins" / "capability-reuse")
    or _try_load_event_store(_HERMES_HOME / "skills" / "hermes" / "capability-reuse" / "plugin")
)
HAS_EVENT_STORE = _event_store_module is not None
if HAS_EVENT_STORE:
    emit_retrieval = _event_store_module.emit_retrieval
    emit_observation = _event_store_module.emit_observation
    emit_surface_execution_start = _event_store_module.emit_surface_execution_start
    emit_surface_execution_complete = _event_store_module.emit_surface_execution_complete
else:
    emit_retrieval = emit_observation = None
    emit_surface_execution_start = emit_surface_execution_complete = None


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18643
MAX_MESSAGE_BYTES = 2048


class HMPAdapter(BasePlatformAdapter):
    """Hermes gateway platform adapter for HMP peer messages."""

    def __init__(self, config: PlatformConfig) -> None:
        super().__init__(config, Platform("hmp"))
        extra = getattr(config, "extra", {}) or {}
        self.host = str(extra.get("host") or os.getenv("HMP_HOST") or DEFAULT_HOST)
        self.port = int(extra.get("port") or os.getenv("HMP_PORT") or DEFAULT_PORT)
        self.node_id = str(extra.get("node_id") or os.getenv("HMP_NODE_ID") or "hermes")
        self.shared_secret = str(extra.get("shared_secret") or os.getenv("HMP_SHARED_SECRET") or "")
        allowed = extra.get("allowed_peers") or os.getenv("HMP_ALLOWED_PEERS") or ""
        if isinstance(allowed, (list, tuple, set)):
            self.allowed_peers = {str(v).strip() for v in allowed if str(v).strip()}
        else:
            self.allowed_peers = {p.strip() for p in str(allowed).split(",") if p.strip()}
        self.allow_all_peers = bool(extra.get("allow_all_peers")) or truthy(os.getenv("HMP_ALLOW_ALL_PEERS"))
        self.request_timeout_seconds = float(extra.get("request_timeout_seconds") or os.getenv("HMP_REQUEST_TIMEOUT_SECONDS") or 900)
        db_path = str(extra.get("database_path") or os.getenv("HMP_DB_PATH") or DEFAULT_DB_PATH)
        self.store = HMPStatusStore(db_path)
        self._runner = None
        self._site = None
        self._consumer_task = None
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/health", self.health),
                web.get("/hmp/health", self.health),
                web.get("/hmp/agent-card", self.agent_card),
                web.post("/hmp/send", self.hmp_send),
                web.post("/hmp/send_and_wait", self.hmp_send_and_wait),
                web.post("/send", self.hmp_dualplane_alias),
                web.get(r"/hmp/poll/{message_id}", self.hmp_poll),
            ]
        )

    async def connect(self, *args: Any, **kwargs: Any) -> bool:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._consumer_task = asyncio.ensure_future(self._consumer_loop())
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        self._consumer_task = None
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        self._mark_disconnected()

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        # HMP exposes status via /hmp/poll rather than typing indicators.
        return None

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        response_message_id = "hmp_resp_" + uuid.uuid4().hex[:12]
        original_id = reply_to or (metadata or {}).get("hmp_message_id")
        if original_id:
            self.store.complete(
                str(original_id),
                str(content),
                sent_to_chat_id=str(chat_id),
                response_message_id=response_message_id,
            )
        return SendResult(success=True, message_id=response_message_id)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"id": chat_id, "name": chat_id, "type": "dm"}

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "service": "hmp-gateway",
                "gateway_adapter": True,
                "node_id": self.node_id,
                "bind": "%s:%s" % (self.host, self.port),
            }
        )

    async def agent_card(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "agent": self.node_id,
                "platform": "hmp",
                "service": "hermes-gateway-hmp",
                "endpoints": [
                    "/health",
                    "/hmp/health",
                    "/hmp/agent-card",
                    "/hmp/send",
                    "/hmp/send_and_wait",
                    "/send",
                    "/hmp/poll/{message_id}",
                ],
                "max_text_length": MAX_MESSAGE_BYTES,
                "version": "0.1.5",
            }
        )

    async def hmp_send(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"accepted": False, "error": "invalid_json"}, status=400)
        accepted, status_code = await self._accept_hmp_message(request, body)
        return web.json_response(accepted, status=status_code)

    async def hmp_send_and_wait(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"accepted": False, "error": "invalid_json"}, status=400)
        accepted, status_code = await self._accept_hmp_message(request, body)
        if status_code >= 300:
            return web.json_response(accepted, status=status_code)
        message_id = accepted.get("message_id")
        deadline = asyncio.get_event_loop().time() + self.request_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            item = self.store.get(str(message_id))
            if item and item.get("status") in {"completed", "failed"}:
                return web.json_response(item, status=200 if item.get("status") == "completed" else 500)
            await asyncio.sleep(0.2)
        self.store.mark_status(str(message_id), "timed_out", error="send_and_wait timed out")
        return web.json_response(self.store.get(str(message_id)) or {"message_id": message_id, "status": "timed_out"}, status=504)

    async def hmp_poll(self, request: web.Request) -> web.Response:
        message_id = request.match_info["message_id"]
        item = self.store.get(message_id)
        if not item:
            return web.json_response({"message_id": message_id, "status": "not_found"}, status=404)
        return web.json_response(item)

    async def hmp_dualplane_alias(self, request: web.Request) -> web.Response:
        """Backward-compatible alias for the retired :18644 /send endpoint.

        Accepts the old dual-plane body shape {session_id, text, max_tokens}
        and routes it through the standard HMP pipeline. Blocks (send_and_wait
        semantics) so old clients get a synchronous response like before.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "error": "invalid_json"}, status=400)
        text = str(body.get("text") or "")
        if not text:
            return web.json_response({"status": "error", "error": "empty_text"}, status=400)
        session_id = str(body.get("session_id") or "").strip()
        # Wrap into the canonical HMP message shape (peer_pair_id as session_id).
        wrapped = {
            "hmp_version": "1.0",
            "message_id": make_message_id("dp"),
            "from": extract_peer(body) or self.node_id,
            "to": self.node_id,
            "type": "request",
            "timeout": int(body.get("timeout") or 120),
            "payload": {"text": text},
        }
        if session_id:
            wrapped["session_id"] = session_id
        accepted, status_code = await self._accept_hmp_message(request, wrapped)
        if status_code >= 300:
            return web.json_response(accepted, status=status_code)
        message_id = accepted.get("message_id")
        deadline = asyncio.get_event_loop().time() + self.request_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            item = self.store.get(str(message_id))
            if item and item.get("status") in {"completed", "failed"}:
                ok = item.get("status") == "completed"
                return web.json_response(
                    {
                        "status": "ok" if ok else "error",
                        "response": item.get("response_text") or "",
                        "session_id": session_id or item.get("chat_id") or "",
                    },
                    status=200 if ok else 500,
                )
            await asyncio.sleep(0.2)
        self.store.mark_status(str(message_id), "timed_out", error="send alias timed out")
        return web.json_response(
            {"status": "error", "error": "timed_out", "message_id": message_id},
            status=504,
        )

    async def _accept_hmp_message(self, request: web.Request, body: Dict[str, Any]):
        auth_error = self._authorize_request(request, body)
        if auth_error:
            return {"accepted": False, "error": auth_error}, 403

        message_id = str(body.get("message_id") or body.get("id") or make_message_id())
        idempotency_key = str(body.get("idempotency_key") or message_id)
        existing = self.store.get_by_idempotency_key(idempotency_key)
        if existing and existing.get("message_id") != message_id:
            return {
                "accepted": True,
                "duplicate": True,
                "message_id": existing.get("message_id"),
                "status": existing.get("status"),
            }, 202

        from_peer = extract_peer(body)
        to_peer = str(body.get("to") or body.get("to_peer") or self.node_id)
        text = extract_text(body)
        if not text:
            return {"accepted": False, "message_id": message_id, "error": "empty_text"}, 400
        text_size = len(text.encode("utf-8"))
        if text_size > MAX_MESSAGE_BYTES:
            return {
                "accepted": False,
                "message_id": message_id,
                "error": "message_too_large",
                "max_bytes": MAX_MESSAGE_BYTES,
                "actual_bytes": text_size,
            }, 413

        # Dual-plane parity: an explicit session_id becomes the chat id, so the
        # gateway keeps per-peer-pair conversational context (like the retired
        # :18644 server did with API sessions keyed by peer_pair_id).
        session_id = str(body.get("session_id") or "").strip()
        chat_id = session_id or from_peer

        queued = self.store.queue(message_id, body, from_peer, to_peer, text, chat_id=chat_id)
        queued["chat_id"] = chat_id
        if session_id:
            queued["session_id"] = session_id
        return {
            "accepted": True,
            "message_id": message_id,
            "status": "queued",
        }, 202

    def _classify_traffic(self, body_meta: Dict[str, Any], requester_peer: str):
        """Fail-closed provenance classification (fix 2.6.0, P0).

        Explicit automation markers win; declared traffic_type next; only an
        explicit positive organic declaration (with no automation marker)
        yields organic_peer. from_peer alone NEVER implies organic.
        Returns (traffic_type, provenance, provenance_detail).
        """
        declared_traffic = str(body_meta.get("traffic_type") or body_meta.get("traffic") or "").strip().lower()
        declared_prov = str(body_meta.get("provenance") or "").strip().lower()
        is_sched = bool(body_meta.get("scheduled") or body_meta.get("is_scheduled") or body_meta.get("cron") or body_meta.get("is_cron") or "scheduled" in declared_traffic or "scheduled" in declared_prov)
        is_calib = bool(body_meta.get("calibration") or body_meta.get("is_calibration") or "calibration" in declared_traffic or "calibration" in declared_prov)
        is_test = bool(body_meta.get("test") or body_meta.get("is_test") or body_meta.get("acceptance") or "test" in declared_traffic or "acceptance" in declared_traffic)
        is_solicited = bool(body_meta.get("operator_solicited") or body_meta.get("is_solicited") or body_meta.get("solicited") or "operator_solicited" in declared_traffic or "operator_solicited" in declared_prov)
        is_seeded = bool(body_meta.get("operator_seeded") or body_meta.get("is_seeded") or body_meta.get("seeded") or "operator_seeded" in declared_traffic or "operator_seeded" in declared_prov)
        is_retry = bool(body_meta.get("retry") or body_meta.get("is_retry") or body_meta.get("retry_of") or "retry" in declared_traffic)
        if is_sched:
            return "scheduled_protocol", "scheduled", "body.scheduled"
        if is_calib:
            return "calibration", "calibration_probe", "body.calibration"
        if is_test:
            return "test", "test", "body.test"
        if is_solicited:
            return "operator_solicited", "operator_solicited", "body.operator_solicited"
        if is_seeded:
            return "operator_seeded", "operator_seeded", "body.operator_seeded"
        if is_retry:
            return "retry", "retry", "body.retry"
        if declared_traffic in ("organic_peer", "organic_user", "organic_live", "unknown", "cron", "registry_sync"):
            return declared_traffic, declared_traffic, "body.traffic_type"
        if declared_prov == "organic_live" and requester_peer:
            return "organic_peer", "organic_live", "body.provenance"
        if requester_peer:
            # from_peer alone is INSUFFICIENT for organic (P0): missing
            # explicit provenance → fail closed → unknown.
            return "unknown", "unknown", "missing_provenance"
        return "unknown", "unknown", "missing_provenance"

    async def _process_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process one dequeued HMP message end-to-end (G0).

        Returns {"trace_id", "outcome", "error", "traffic_type", "surf_id"}.
        trace_id is a request-unique UUID v4 (P0-10): generated once per
        request, propagated across the whole chain (retrieval → intervention →
        invocation → feedback sink → tombstone). The retriever's
        trace→chat→sender→requester→session fallback is never used for
        holdout-eligible records because an explicit UUID is always supplied.
        """
        message_id = str(item.get("message_id"))
        from_peer = str(item.get("from_peer") or item.get("chat_id") or "unknown")
        chat_id = str(item.get("chat_id") or item.get("from_peer") or "unknown")
        text = str(item.get("text") or "")
        raw = item.get("raw") or {}
        # G0 (P0-10): request-unique trace_id — UUID v4, generated BEFORE the
        # MessageEvent so it can ride the event into the agent hook context.
        trace_id = str(uuid.uuid4())
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=self.build_source(
                chat_id=chat_id,
                chat_name=chat_id,
                chat_type="dm",
                user_id=from_peer,
                user_name=from_peer,
                message_id=message_id,
            ),
            raw_message=raw,
            message_id=message_id,
            trace_id=trace_id,
            capability_reuse_context=self._capability_context(raw),
        )
        # ── LIVE-SHADOW (dual-plane parity): emit retrieval chain ──
        surf_id = None
        _t0 = time.monotonic()
        traffic_type = "unknown"
        if HAS_EVENT_STORE:
            try:
                requester_peer = str(from_peer or "").strip()
                # --- classify traffic from explicit body metadata (fail-closed) ---
                body_meta = raw if isinstance(raw, dict) else {}
                traffic_type, prov, prov_detail = self._classify_traffic(body_meta, requester_peer)
                emit_retrieval(
                    session_id=chat_id,
                    user_message_preview=text[:200],
                    candidates=[],
                    top_score=0.0,
                    intervened=False,
                    latency_ms=0.0,
                    traffic_type=traffic_type,
                    provenance=prov,
                    provenance_source="hmp_plugin.consumer_loop",
                    provenance_detail=prov_detail,
                    requester={
                        "actor_type": "agent",
                        "actor_id": "hmp:%s" % requester_peer if requester_peer else "unknown",
                        "request_channel": "hmp",
                        "requester_peer_id": requester_peer,
                        "processing_peer_id": self.node_id,
                    } if requester_peer else None,
                    # v2.4.18 envelope
                    trace_id=trace_id,
                    requester_peer_id=requester_peer,
                    processing_peer_id=self.node_id,
                    collector_peer_id=self._extract_collector(raw),
                    producer_surface="hmp_ingress",
                )
                # v2.4.18: surface_execution_* replaces execute_code_* for
                # generic HMP processing (execute_code_* is reserved for
                # real execute_code only).
                surf_id = emit_surface_execution_start(
                    execution_surface="hmp_plugin",
                    surface_preview=text[:100],
                    session_id=chat_id,
                    requester_peer_id=requester_peer,
                    processing_peer_id=self.node_id,
                    trace_id=trace_id,
                    traffic_type=traffic_type,
                    producer_surface="hmp_ingress",
                )
            except Exception:
                surf_id = None
        try:
            await self.handle_message(event)
            outcome, err = "success", None
        except asyncio.CancelledError:
            self.store.mark_status(message_id, "queued")
            raise
        except Exception as exc:
            self.store.fail(message_id, "handle_message failed: %s" % exc)
            outcome, err = "failure", str(exc)
        if HAS_EVENT_STORE and surf_id:
            try:
                emit_surface_execution_complete(
                    execution_surface="hmp_plugin",
                    outcome=outcome,
                    duration_ms=(time.monotonic() - _t0) * 1000.0,
                    error=err,
                    session_id=chat_id,
                    requester_peer_id=requester_peer,
                    processing_peer_id=self.node_id,
                    trace_id=trace_id,
                    traffic_type=traffic_type,
                    producer_surface="hmp_ingress",
                )
                emit_observation(
                    capability_id="hmp",
                    capability_version="0.1.5",
                    effect_class="read_only",
                )
            except Exception:
                pass
        return {
            "trace_id": trace_id,
            "outcome": outcome,
            "error": err,
            "traffic_type": traffic_type,
            "surf_id": surf_id,
        }

    def _extract_collector(self, raw: Dict[str, Any]) -> str:
        """collector_peer_id propagation (envelope v2.4.18).

        Priority: explicit body field > env var > empty (fail open, absent
        is legal — the collector may be unknown on non-central peers).
        """
        if isinstance(raw, dict):
            body_collector = raw.get("collector_peer_id") or raw.get("collector") or ""
            if isinstance(body_collector, str) and body_collector.strip():
                return body_collector.strip()
        return os.environ.get("CAPABILITY_REUSE_COLLECTOR_PEER_ID", "")

    def _capability_context(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Request-scoped capability-reuse metadata from the HMP body (G2b).

        Carries the EXPLICIT provenance declaration + exclusion markers to the
        real Capability Reuse retrieval (via MessageEvent → hook kwargs).
        NEVER infers organic from platform identity: only declared values are
        forwarded. Exclusion markers keep priority downstream (fail-closed).
        """
        if not isinstance(raw, dict):
            return None
        ctx: Dict[str, Any] = {}
        prov = raw.get("provenance")
        if isinstance(prov, str) and prov.strip():
            ctx["capability_reuse_provenance"] = prov.strip()
        elif isinstance(prov, dict):
            stream = prov.get("stream") or prov.get("type") or prov.get("name")
            if isinstance(stream, str) and stream.strip():
                ctx["capability_reuse_provenance"] = stream.strip()
        # Exclusion / automation markers — forwarded verbatim; downstream
        # _extract_traffic_type gives them priority over any organic claim.
        for key in (
            "operator_solicited", "is_solicited", "solicited",
            "operator_seeded", "is_seeded", "seeded",
            "is_test", "test", "acceptance", "is_acceptance",
            "calibration", "is_calibration",
            "is_retry", "retry_of",
            "scheduled", "is_scheduled", "cron", "is_cron",
            "traffic_type", "capability_reuse_traffic_type",
        ):
            if key in raw and raw[key] is not None:
                ctx[key] = raw[key]
        return ctx or None

    async def _consumer_loop(self) -> None:
        while True:
            item = self.store.dequeue()
            if not item:
                await asyncio.sleep(2)
                continue
            try:
                await self._process_item(item)
            except asyncio.CancelledError:
                raise
            except Exception:
                # _process_item handles per-message failures internally;
                # this is a safety net so one bad message never kills the loop.
                try:
                    self.store.fail(str(item.get("message_id") or "?"), "consumer loop error")
                except Exception:
                    pass

    def _authorize_request(self, request: web.Request, body: Dict[str, Any]) -> Optional[str]:
        if self.shared_secret:
            header = request.headers.get("Authorization", "")
            bearer = "Bearer " + self.shared_secret
            alt = request.headers.get("X-HMP-Secret", "")
            if header != bearer and alt != self.shared_secret:
                return "unauthorized"
        peer = extract_peer(body)
        if self.allow_all_peers:
            return None
        if self.allowed_peers and peer in self.allowed_peers:
            return None
        if not self.allowed_peers and self.host in {"127.0.0.1", "localhost", "::1"}:
            # Safe staging default: localhost-only listener can accept local tests.
            return None
        return "peer_not_allowed"


def check_requirements() -> bool:
    try:
        import aiohttp  # noqa: F401
        return True
    except Exception:
        return False


def validate_config(config: PlatformConfig) -> bool:
    extra = getattr(config, "extra", {}) or {}
    try:
        int(extra.get("port") or os.getenv("HMP_PORT") or DEFAULT_PORT)
    except Exception:
        return False
    return True


def is_connected(config: PlatformConfig) -> bool:
    return bool(getattr(config, "enabled", False)) and validate_config(config)


def _env_enablement() -> Optional[Dict[str, Any]]:
    if not (os.getenv("HMP_ENABLED") or os.getenv("HMP_PORT") or os.getenv("HMP_HOST")):
        return None
    return {
        "host": os.getenv("HMP_HOST") or DEFAULT_HOST,
        "port": int(os.getenv("HMP_PORT") or DEFAULT_PORT),
        "node_id": os.getenv("HMP_NODE_ID") or "hermes",
        "database_path": os.getenv("HMP_DB_PATH") or DEFAULT_DB_PATH,
        "allow_all_peers": truthy(os.getenv("HMP_ALLOW_ALL_PEERS")),
    }


def _apply_yaml_config(yaml_cfg: Dict[str, Any], platform_cfg: Dict[str, Any]) -> Dict[str, Any]:
    extra = dict(platform_cfg.get("extra") or {})
    for key in (
        "host",
        "port",
        "node_id",
        "database_path",
        "shared_secret",
        "allowed_peers",
        "allow_all_peers",
        "request_timeout_seconds",
    ):
        if key in platform_cfg and key not in extra:
            extra[key] = platform_cfg[key]

    # Bridge YAML auth knobs into env vars because GatewayRunner._is_user_authorized()
    # consults the PlatformEntry allowed_users_env / allow_all_env names.
    if "allow_all_peers" in extra and not os.getenv("HMP_ALLOW_ALL_PEERS"):
        os.environ["HMP_ALLOW_ALL_PEERS"] = "true" if truthy(extra.get("allow_all_peers")) else "false"
    if "allowed_peers" in extra and not os.getenv("HMP_ALLOWED_PEERS"):
        allowed = extra.get("allowed_peers")
        if isinstance(allowed, (list, tuple, set)):
            allowed = ",".join(str(v) for v in allowed)
        os.environ["HMP_ALLOWED_PEERS"] = str(allowed)
    if "node_id" in extra and not os.getenv("HMP_NODE_ID"):
        os.environ["HMP_NODE_ID"] = str(extra.get("node_id"))
    if "host" in extra and not os.getenv("HMP_HOST"):
        os.environ["HMP_HOST"] = str(extra.get("host"))
    if "port" in extra and not os.getenv("HMP_PORT"):
        os.environ["HMP_PORT"] = str(extra.get("port"))
    if "database_path" in extra and not os.getenv("HMP_DB_PATH"):
        os.environ["HMP_DB_PATH"] = str(extra.get("database_path"))
    return extra


def register(ctx) -> None:
    ctx.register_platform(
        name="hmp",
        label="HMP",
        adapter_factory=lambda cfg: HMPAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        env_enablement_fn=_env_enablement,
        apply_yaml_config_fn=_apply_yaml_config,
        allowed_users_env="HMP_ALLOWED_PEERS",
        allow_all_env="HMP_ALLOW_ALL_PEERS",
        emoji="🕸️",
        pii_safe=True,
        platform_hint=(
            "You are communicating through HMP, a peer-to-peer Hermes Message Protocol. "
            "Treat peer ids as chat ids. Replies are delivered through HMP poll/status endpoints."
        ),
        install_hint="aiohttp is required and is already bundled with Hermes gateway installs.",
    )
