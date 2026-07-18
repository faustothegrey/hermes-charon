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
import uuid
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


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18643


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
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/health", self.health),
                web.get("/hmp/health", self.health),
                web.get("/hmp/agent-card", self.agent_card),
                web.post("/hmp/send", self.hmp_send),
                web.post("/hmp/send_and_wait", self.hmp_send_and_wait),
                web.get(r"/hmp/poll/{message_id}", self.hmp_poll),
            ]
        )

    async def connect(self, *args: Any, **kwargs: Any) -> bool:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
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
                    "/hmp/poll/{message_id}",
                ],
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

        self.store.accept(message_id, body, from_peer, to_peer, text)
        self.store.mark_status(message_id, "gateway_accepted")
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=self.build_source(
                chat_id=from_peer,
                chat_name=from_peer,
                chat_type="dm",
                user_id=from_peer,
                user_name=from_peer,
                message_id=message_id,
            ),
            raw_message=body,
            message_id=message_id,
        )
        try:
            await self.handle_message(event)
        except Exception as exc:
            self.store.fail(message_id, "handle_message failed: %s" % exc)
            return {"accepted": False, "message_id": message_id, "status": "failed", "error": str(exc)}, 500
        self.store.mark_status(message_id, "working")
        return {"accepted": True, "message_id": message_id, "status": "working"}, 202

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
