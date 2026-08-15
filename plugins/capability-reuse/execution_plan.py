from __future__ import annotations
"""Canonical deterministic execution plans for capability-reuse v2.4.6.

Preview and dispatch must derive from this module so reviewer artifacts describe
exactly the operation an active dispatcher would perform. This module is pure,
network-free, and secret-free.
"""
from typing import Any

PREVIEW_SCHEMA_VERSION = "1.0"

PEER_MAP = {
    "peer58": ("192.168.178.58", "/hmp/health"),
    "peer70": ("192.168.178.70", "/hmp/health"),
    "peer84": ("192.168.178.84", "/hmp/health"),
    "peer105": ("192.168.178.105", "/hmp/health"),
    "peer106": ("192.168.178.106", "/hmp/health"),
    "peer128": ("192.168.178.112", "/hmp/health"),
    "peer138": ("192.168.178.138", "/hmp/health"),
    "peer141": ("192.168.178.141", "/hmp/health"),
    "trixie": ("192.168.178.136", "/health"),
    "peer136": ("192.168.178.136", "/health"),
}


def _normalize_peer(peer: Any) -> str:
    return str(peer or "").strip().lower()


def resolve_peer(peer: Any) -> dict[str, Any]:
    label = _normalize_peer(peer)
    if not label:
        return {"target_peer_id": "", "ip": "", "path": "/hmp/health", "status": "invalid_input"}
    if label in PEER_MAP:
        ip, path = PEER_MAP[label]
        return {"target_peer_id": label, "ip": ip, "path": path, "status": "exact"}
    return {"target_peer_id": label, "ip": "", "path": "/hmp/health", "status": "unsupported"}


def _peer_list(validated_inputs: dict[str, Any]) -> list[str]:
    if not isinstance(validated_inputs, dict):
        return []
    peers = validated_inputs.get("peer_list")
    if isinstance(peers, list):
        return [_normalize_peer(p) for p in peers if _normalize_peer(p)]
    peer = _normalize_peer(validated_inputs.get("peer") or validated_inputs.get("target_peer_id"))
    return [peer] if peer else []


def build_execution_plan(capability_id: str, capability_version: str, validated_inputs: dict[str, Any] | None) -> dict[str, Any]:
    """Return the exact deterministic plan used for preview and dispatch.

    The plan is intentionally non-executable for unsupported targets or unknown
    capabilities. Target addresses come only from PEER_MAP, never from user text.
    """
    inputs = validated_inputs if isinstance(validated_inputs, dict) else {}
    cap_id = (capability_id or "").strip()
    cap_ver = (capability_version or "").strip()
    if cap_id == "hmp-healthcheck" and cap_ver == "1.0.0":
        peers = _peer_list(inputs)
        try:
            timeout = int(inputs.get("timeout_seconds", 5))
        except Exception:
            timeout = 5
        timeout = max(1, min(timeout, 30))
        base = {
            "preview_schema_version": PREVIEW_SCHEMA_VERSION,
            "capability_id": cap_id,
            "capability_version": cap_ver,
            "effect_class": "read_only",
            "timeout_seconds": timeout,
            "auth_mode": "none",
            "mutation_possible": False,
            "credentials_exposed_in_preview": False,
        }
        if not peers:
            base.update({
                "target_peer_id": "",
                "target_resolution_source": "unavailable",
                "executor_kind": "unresolved",
                "method": None,
                "endpoint": None,
                "preview_status": "invalid_input",
                "command_preview": "NOT EXECUTABLE: missing target peer",
                "targets": [],
            })
            return base
        targets = []
        unsupported = []
        for peer in peers:
            resolved = resolve_peer(peer)
            if resolved["status"] != "exact":
                unsupported.append(resolved["target_peer_id"] or peer)
                targets.append({"target_peer_id": resolved["target_peer_id"] or peer, "preview_status": resolved["status"], "endpoint": None})
            else:
                endpoint = "http://%s:18643%s" % (resolved["ip"], resolved["path"])
                targets.append({"target_peer_id": resolved["target_peer_id"], "preview_status": "exact", "method": "GET", "endpoint": endpoint})
        base["targets"] = targets
        base["target_peer_id"] = peers[0] if len(peers) == 1 else ",".join(peers)
        if unsupported:
            base.update({
                "preview_status": "unsupported",
                "target_resolution_source": "unavailable",
                "executor_kind": "unresolved",
                "method": None,
                "endpoint": None,
                "command_preview": "NOT EXECUTABLE: unsupported target peer %s" % unsupported[0],
            })
        else:
            endpoints = [t["endpoint"] for t in targets]
            base.update({
                "preview_status": "exact",
                "target_resolution_source": "peer_map",
                "executor_kind": "http_get" if len(targets) == 1 else "batch_http_get",
                "method": "GET",
                "endpoint": endpoints[0] if len(endpoints) == 1 else None,
                "command_preview": "GET " + " ; GET ".join(endpoints),
            })
        return base
    return {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "capability_id": cap_id,
        "capability_version": cap_ver,
        "effect_class": "unknown",
        "target_peer_id": None,
        "target_resolution_source": "unavailable",
        "executor_kind": "unresolved",
        "method": None,
        "endpoint": None,
        "timeout_seconds": None,
        "auth_mode": "unknown",
        "mutation_possible": False,
        "credentials_exposed_in_preview": False,
        "preview_status": "unsupported",
        "command_preview": "NOT EXECUTABLE: unsupported capability %s@%s" % (cap_id, cap_ver),
    }


def redact_execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a secret-free reviewer preview for an already-built plan."""
    safe = dict(plan or {})
    safe["credentials_exposed_in_preview"] = False
    endpoint = safe.get("endpoint")
    if isinstance(endpoint, str) and "@" in endpoint.split("//", 1)[-1].split("/", 1)[0]:
        safe["endpoint"] = None
        safe["command_preview"] = "NOT EXECUTABLE: credential-bearing endpoint redacted"
        safe["preview_status"] = "invalid_input"
    return safe
