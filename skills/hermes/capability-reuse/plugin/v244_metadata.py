"""
v244_metadata.py — v2.4.4 mandatory event metadata enrichment.
Implements spec: request-scoped provenance, peer_id, traffic_type,
chain correlation, CSV neutralization.
"""
from __future__ import annotations
import json, os, re, uuid, socket, hashlib
from pathlib import Path
from datetime import datetime, timezone

PLUGIN_VERSION = "2.6.0"
SCHEMA_VERSION = "1.3"

def peer_id() -> str:
    """Resolve peer_id from config/registry, never from env."""
    for p in [
        Path.home() / ".hermes" / "peer-network" / "node-id",
        Path.home() / ".hermes" / "node-id",
    ]:
        try:
            if p.exists():
                v = p.read_text().strip()
                if v: return v
        except Exception: pass
    cfg = Path.home() / ".hermes" / "config.yaml"
    try:
        if cfg.exists():
            m = re.search(r"node_id:\s*[\"']?([\w-]+)", cfg.read_text())
            if m: return m.group(1)
    except Exception: pass
    return f"host-{socket.gethostname()}"

def resolve_provenance(stream=None, source=None, detail=None, context=None):
    """Request-scoped provenance. Missing -> legacy_unclassified; invalid -> unknown.
    NEVER reads a process-wide env var."""
    if context and isinstance(context, dict):
        if context.get("provenance") and isinstance(context["provenance"], dict):
            pv = context["provenance"]
            stream = pv.get("stream") or "unknown"
            valid = stream in ("organic_live", "operator_seeded", "calibration_probe")
            return {"stream": stream,
                    "source": pv.get("source") or "gateway",
                    "detail": pv.get("detail") or "explicit_request",
                    "valid": valid,
                    "reason": "" if valid else "invalid_provenance"}
    if stream:
        s = str(stream)
        if s not in ("organic_live", "operator_seeded", "calibration_probe"):
            return {"stream": "unknown", "source": source or "gateway", "detail": detail or "invalid_value", "valid": False, "reason": "invalid_provenance"}
        return {"stream": s, "source": source or "gateway", "detail": detail or "", "valid": True, "reason": ""}
    return {"stream": "legacy_unclassified", "source": source or "unknown", "detail": detail or "missing_metadata", "valid": False, "reason": "missing_provenance"}

def traffic_type(parent_task_id=None, schedule_id=None, retry_of=None, is_cron=False, is_test=False):
    if is_test: return "test"
    if is_cron: return "cron"
    if retry_of: return "retry"
    if parent_task_id: return "organic_user"
    if schedule_id: return "cron"
    return "unknown"

def chain_context(session_id=None, episode_id=None, turn_id=None, task_id=None,
                  tool_call_id=None, retrieval_event_id=None, code_hash=None):
    return {
        "session_id": session_id or "",
        "episode_id": episode_id or "",
        "turn_id": turn_id or "",
        "task_id": task_id or "",
        "tool_call_id": tool_call_id or "",
        "retrieval_event_id": retrieval_event_id or "",
        "code_hash": code_hash or "",
    }

def neutralize_csv(text):
    """Prepend ' to cells starting with = + - @ to prevent formula injection."""
    if not isinstance(text, str): return text
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text

def cohort_fields():
    cf = Path.home() / ".hermes" / "data" / "reuse-observer" / "cohort.json"
    try:
        d = json.loads(cf.read_text())
        return {
            "deployment_id": d.get("deployment_id"),
            "deployment_timestamp": d.get("deployment_timestamp"),
            "plugin_version": d.get("plugin_version"),
            "plugin_artifact_hash": d.get("plugin_artifact_hash"),
            "schema_version": d.get("schema_version"),
            "cohort_label": d.get("cohort_label"),
        }
    except Exception:
        return {"deployment_id": None, "deployment_timestamp": None,
                "plugin_version": PLUGIN_VERSION, "plugin_artifact_hash": None,
                "schema_version": SCHEMA_VERSION, "cohort_label": "uncohortable"}

def mandatory(event_type: str, data: dict, context=None) -> dict:
    """Attach mandatory v2.4.4 fields to any event payload."""
    out = dict(data)
    out["event_id"] = data.get("event_id") or f"evt-{uuid.uuid4().hex[:12]}"
    out["timestamp"] = data.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["peer_id"] = data.get("peer_id") or peer_id()
    out["plugin_version"] = data.get("plugin_version") or PLUGIN_VERSION
    out["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    pv = data.get("provenance")
    if not pv and context: pv = context.get("provenance")
    out["provenance"] = resolve_provenance(
        (pv or {}).get("stream") if isinstance(pv, dict) else None,
        (pv or {}).get("source") if isinstance(pv, dict) else None,
        (pv or {}).get("detail") if isinstance(pv, dict) else None,
        context=context)
    # requester identity (v2.4.5): actor and transport are orthogonal.
    req = out.get("requester") if isinstance(out.get("requester"), dict) else {}
    if context and isinstance(context.get("requester"), dict):
        req = {**req, **context["requester"]}
    out["requester"] = {
        "actor_type": req.get("actor_type") or "unknown",
        "actor_id": req.get("actor_id") or "unknown",
        "request_channel": req.get("request_channel") or "unknown",
        "requester_peer_id": req.get("requester_peer_id") or "",
        "processing_peer_id": req.get("processing_peer_id") or out.get("peer_id") or peer_id(),
    }
    # traffic_type: inherit request-scoped value from retrieval context.
    # Treat blank/unknown as missing so execution-chain events cannot overwrite
    # an organic retrieval's traffic_type with a fail-open default.
    tt = context or {}
    if not out.get("traffic_type") or out.get("traffic_type") == "unknown":
        out["traffic_type"] = tt.get("traffic_type") or traffic_type(
            parent_task_id=tt.get("parent_task_id"), schedule_id=tt.get("schedule_id"),
            retry_of=tt.get("retry_of"), is_cron=tt.get("is_cron"), is_test=tt.get("is_test"))
    for k in ("parent_task_id", "retry_of", "schedule_id"):
        if k not in out and context and context.get(k):
            out[k] = context[k]
    # chain correlation
    for k in ("session_id", "episode_id", "turn_id", "task_id", "tool_call_id",
              "retrieval_event_id", "code_hash"):
        if k not in out or not out[k]:
            if context and context.get(k):
                out[k] = context[k]
            else:
                out[k] = ""
    # Ensure retrieval top-level processor mirrors the authoritative requester
    # processor after requester normalization. Earlier v2.4.10 builds populated
    # requester.processing_peer_id but left retrieval_event.processing_peer_id
    # blank because emit_retrieval constructed the top-level field before
    # mandatory requester enrichment.
    if event_type == "retrieval_event" and not out.get("processing_peer_id"):
        out["processing_peer_id"] = out.get("requester", {}).get("processing_peer_id") or out.get("peer_id") or peer_id()
    # cohort
    for k, v in cohort_fields().items():
        if k not in out:
            out[k] = v
    return out
