from __future__ import annotations
"""
dispatcher.py — Capability Reuse Plugin: Phase 1B deterministic dispatchers
============================================================================

Only exact-version, allowlisted, audited executors live here. This module must
never synthesize code for execution. Phase 1B initially enables the read-only
hmp-healthcheck@1.0.0 capability only.
"""
import json
import time
import urllib.error
import urllib.request
from typing import Any
try:
    from .execution_plan import PEER_MAP, build_execution_plan
except Exception:
    from execution_plan import PEER_MAP, build_execution_plan

# PEER_MAP is imported from execution_plan so preview and dispatch share one peer allowlist.

def _resolve_peer(peer: str):
    p = (peer or "").strip()
    if not p:
        return "", "", "/hmp/health"
    key = p.lower()
    if key in PEER_MAP:
        ip, path = PEER_MAP[key]
        return key, ip, path
    return p, "", "/hmp/health"


def _probe_hmp_health(peer: str, timeout_seconds: int) -> dict[str, Any]:
    label, ip, path = _resolve_peer(peer)
    if not ip:
        return {"peer": label or peer, "status": "error", "latency_ms": None, "error": "unknown_peer"}
    url = f"http://{ip}:18643{path}"
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as r:
            body = r.read(65536)
            status_code = getattr(r, "status", 200)
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        parsed = None
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            parsed = {"raw": body.decode("utf-8", "replace")[:200]}
        ok = status_code == 200 and (not isinstance(parsed, dict) or parsed.get("status") in (None, "ok", "healthy"))
        return {
            "peer": label or peer,
            "status": "ok" if ok else "error",
            "latency_ms": latency_ms,
            "error": None if ok else f"http_{status_code}",
            "detail": parsed if isinstance(parsed, dict) else None,
        }
    except urllib.error.HTTPError as e:
        return {"peer": label or peer, "status": "error", "latency_ms": None, "error": f"http_{e.code}"}
    except TimeoutError:
        return {"peer": label or peer, "status": "timeout", "latency_ms": None, "error": "timeout"}
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        code = "timeout" if "timed out" in msg.lower() else "unavailable"
        return {"peer": label or peer, "status": "timeout" if code == "timeout" else "error", "latency_ms": None, "error": code}


def hmp_healthcheck(inputs: dict[str, Any]) -> dict[str, Any]:
    peers = inputs.get("peer_list") if isinstance(inputs, dict) else None
    if not isinstance(peers, list) or not peers:
        return {"success": False, "error": "invalid_input", "output": None}
    # Build the same canonical plans used by reviewer previews before any network call.
    plans = [build_execution_plan("hmp-healthcheck", "1.0.0", {"peer_list": [str(peer)], "timeout_seconds": (inputs or {}).get("timeout_seconds", 5)}) for peer in peers]
    for plan in plans:
        if plan.get("preview_status") == "unsupported":
            return {"success": False, "error": "unsupported_target", "output": {"peer": plan.get("target_peer_id")}}
        if plan.get("preview_status") != "exact":
            return {"success": False, "error": "invalid_input", "output": None}
    timeout = plans[0].get("timeout_seconds") or 5
    rows = [_probe_hmp_health(str(peer), int(timeout)) for peer in peers]
    failures = [row for row in rows if row.get("status") != "ok"]
    if failures:
        first_error = failures[0].get("error") or failures[0].get("status") or "healthcheck_failed"
        return {"success": False, "output": rows, "error": first_error}
    return {"success": True, "output": rows, "error": None}


def dispatch(capability_id: str, capability_version: str, inputs: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    if capability_id == "hmp-healthcheck" and capability_version == "1.0.0":
        return hmp_healthcheck(inputs)
    return {"success": False, "error": "unsupported_capability", "output": None}
