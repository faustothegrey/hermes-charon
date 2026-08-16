from __future__ import annotations
"""
event_store.py — Capability Reuse Plugin: Immutable Event Log
=============================================================
Append-only JSONL event stream. Thread-safe writes. No mutation of past events.

Event types (§10.1):
  hook_conformance_event     — Conformance suite results
  controller_health_event    — Plugin health heartbeat
  retrieval_event            — Retrieval attempt (shadow or active)
  intervention_event         — Intervention created
  protocol_state_transition  — State machine transition
  capability_invocation_event — invoke_capability call
  fallback_authorization_event — Token issued/consumed/expired
  post_failure_escalation_event — After mutating/unknown failure
  bypass_event               — Bypass record submitted
  execute_code_started_event  — execute_code attempt
  execute_code_completed_event — execute_code result
  alternate_execution_event  — Monitored non-execute_code surface used
  observation_event           — Post-execution observation
  outcome_event               — Episode outcome summary
  review_event                — Human review record
  validation_event            — Validation result
  trust_transition_event     — Capability version trust change
"""
import json, os, re, uuid, threading, sys
from pathlib import Path
try:
    from .v244_metadata import mandatory as _mandatory244
except Exception:
    plugin_dir = str(Path(__file__).resolve().parent)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    from v244_metadata import mandatory as _mandatory244
from datetime import datetime, timezone
from typing import Optional

PROVENANCE_STREAMS = {"organic_live", "operator_solicited", "operator_seeded", "calibration_probe", "legacy_unclassified", "unknown"}

def candidate_label(candidate: dict) -> str:
    """Return capability@version for both canonical and legacy candidate shapes."""
    if not isinstance(candidate, dict):
        return ""
    cap = candidate.get("capability")
    if cap:
        return str(cap)
    cid = candidate.get("capability_id") or candidate.get("id") or ""
    ver = candidate.get("capability_version") or candidate.get("version") or ""
    return (str(cid) + "@" + str(ver)) if cid and ver else str(cid or "")

EVENT_DIR = Path.home() / ".hermes" / "data" / "reuse-observer"
EVENT_LOG = EVENT_DIR / "events.jsonl"
SESSION_LOG = EVENT_DIR / "session-context.jsonl"

# ── Lock for thread-safe writes ──
_write_lock = threading.Lock()
_event_counter = 0
_CHAIN_CONTEXT_BY_INTERVENTION: dict[str, dict] = {}

# ── Schema version ──
SCHEMA_VERSION = "1.3"

# ── v2.5.0 correlation envelope ──────────────────────────────────────
# One immutable envelope propagated through the entire chain:
# retrieval → decision → invocation → completion → review.
# Consumers join on trace_id (top-level), never reconstruct from timestamps.
ENVELOPE_KEYS = (
    "trace_id", "session_id", "episode_id", "turn_id", "task_id",
    "tool_call_id", "retrieval_event_id", "requester_peer_id",
    "processing_peer_id", "target_peer_id", "collector_peer_id",
    "traffic_type", "provenance",
)

# Producer identity: exactly which component emitted the event.
DEFAULT_PRODUCER = {
    "component": "capability_reuse_plugin",
    "version": "2.6.0",
    "surface": "unknown",
}

VALID_SURFACES = {
    "hermes_cli", "gateway", "hmp_ingress", "execute_code_hook",
    "delegated_agent", "unknown",
}

# ── Emitting surface (v2.5.0, spec 2) ────────────────────────────────
# Hook-emitted events run inside the Hermes runtime; the hooks stamp the
# surface they execute under (gateway / execute_code_hook) via a
# thread-local, because hook kwargs are raw and cannot carry producer
# metadata reliably. Explicit data/context values always win over it.
import threading as _threading
_surface_stack = _threading.local()

def push_surface(surface: str) -> None:
    """Stamp the emitting surface for the current thread (hook boundary)."""
    if surface not in VALID_SURFACES or surface == "unknown":
        return
    stack = getattr(_surface_stack, "stack", None)
    if stack is None:
        stack = _surface_stack.stack = []
    stack.append(surface)

def pop_surface() -> None:
    stack = getattr(_surface_stack, "stack", None)
    if stack:
        stack.pop()

def current_surface() -> str:
    stack = getattr(_surface_stack, "stack", None)
    return stack[-1] if stack else ""

# ── v2.5.0 traffic taxonomy ─────────────────────────────────────────
# Explicit categories so protocol traffic (registry sync, health pings)
# never contaminates ordinary organic reuse statistics.
VALID_TRAFFIC_TYPES = {
    "organic_user",      # human-initiated request (Telegram, CLI, ...)
    "organic_peer",      # peer-initiated organic request via HMP
    "scheduled_protocol",  # scheduled/periodic protocol traffic
    "registry_sync",     # registry sync messages ("registry sync?")
    "cron",              # scheduled job traffic
    "retry",             # retried delivery
    "test",              # test traffic
    "acceptance",        # acceptance/validation suite traffic
    "calibration",       # calibration traffic
    "unknown",
}

# Traffic classification helper: registry-sync phrases must map to
# registry_sync, not organic_peer, so repeated sync messages do not
# dominate recurrence/precision statistics.
REGISTRY_SYNC_PATTERNS = (
    "registry sync", "registry_sync", "sync registry",
    "registry status", "registry check", "sync?",
)

# ── Valid event types ──
VALID_EVENTS = {
    "hook_conformance_event",
    "controller_health_event",
    "retrieval_event",
    "intervention_event",
    "protocol_state_transition",
    "capability_invocation_event",
    "fallback_authorization_event",
    "post_failure_escalation_event",
    "bypass_event",
    "execute_code_started_event",
    "execute_code_completed_event",
    "surface_execution_started_event",
    "surface_execution_completed_event",
    "alternate_execution_event",
    "observation_event",
    "outcome_event",
    "review_event",
    "validation_event",
    "trust_transition_event",
}

# ── Block origin tracking ──
BLOCK_ORIGIN_PROTOCOL = "protocol"
BLOCK_ORIGIN_CO_RESIDENT = "co_resident_plugin"
BLOCK_ORIGIN_SHELL_HOOK = "shell_hook"
BLOCK_ORIGIN_APPROVAL = "approval_pipeline"
BLOCK_ORIGIN_UNKNOWN = "unknown"

def _ensure_dir():
    EVENT_DIR.mkdir(parents=True, exist_ok=True)

def _uuid():
    return uuid.uuid4().hex[:16]

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _next_seq_unlocked():
    global _event_counter
    _event_counter += 1
    return _event_counter

_REDACT_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)[^\s,;&]+"), r"\1\2[REDACTED]"),
    (re.compile(r"https?://([^:/\s]+):([^@/\s]+)@"), "https://[REDACTED]@"),
    (re.compile(r"([?&](?:token|key|password|secret|api_key)=)[^&#\s]+", re.I), r"\1[REDACTED]"),
    (re.compile(r'/(?:home|root)/[^\s,;:\'\"]+'), "[PATH]"),
]

def redact_preview(value, max_len: int = 500) -> str:
    """Best-effort redaction for persisted previews; never raises."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text[:max_len]

def normalize_provenance(stream: str | None = None, detail: str = "", source: str = "") -> dict:
    """Classify collection provenance without contaminating organic holdout.

    v2.4.3 rule: missing provenance is legacy_unclassified, invalid provenance is
    unknown. Request-scoped hook_context provenance should be passed explicitly by
    the retriever; CAPABILITY_REUSE_PROVENANCE remains a compatibility fallback
    and is marked as process_env so it cannot be mistaken for request-scoped
    evidence.
    """
    raw = stream
    provenance_source = source or ("request" if stream is not None else "")
    if raw is None:
        raw = os.environ.get("CAPABILITY_REUSE_PROVENANCE")
        if raw is not None:
            provenance_source = "process_env"
    if raw is None or str(raw).strip() == "":
        requested = "legacy_unclassified"
        valid = False
        reason = "missing_provenance"
    else:
        requested = str(raw).strip().lower().replace("-", "_")
        if requested not in PROVENANCE_STREAMS - {"legacy_unclassified"}:
            requested = "unknown"
            valid = False
            reason = "invalid_provenance"
        else:
            valid = True
            reason = ""
    return {
        "stream": requested,
        "valid": valid,
        "source": provenance_source or "missing",
        "reason": reason,
        "detail": redact_preview(detail or os.environ.get("CAPABILITY_REUSE_PROVENANCE_DETAIL", ""), 120),
    }


def classify_traffic_type(text: str = "", channel: str = "", is_cron: bool = False,
                          is_test: bool = False, requester_peer: str = "") -> str:
    """v2.5.0: classify request traffic into the explicit taxonomy.

    Registry-sync / protocol phrases are detected BEFORE generic
    organic_peer classification so repeated sync messages never dominate
    organic reuse statistics.
    """
    q = (text or "").lower()
    ch = (channel or "").lower()

    if is_test or ch == "test":
        return "acceptance"
    if is_cron or ch == "cron":
        return "cron"
    if ch == "retry":
        return "retry"
    if ch == "registry_sync" or any(p in q for p in REGISTRY_SYNC_PATTERNS):
        return "registry_sync"
    if ch in ("organic_peer", "organic_user", "scheduled_protocol", "calibration"):
        return ch
    if requester_peer:
        return "organic_peer"
    if ch in ("telegram", "cli", "gateway") or (q and not requester_peer):
        return "organic_user"
    return "unknown"


def _context_for_retrieval_id(retrieval_event_id: str) -> dict:
    if not retrieval_event_id:
        return {}
    try:
        if not EVENT_LOG.exists():
            return {}
        # Scan backwards: events are append-only and the target is normally recent.
        for line in reversed(EVENT_LOG.read_text(errors="replace").splitlines()):
            if retrieval_event_id not in line:
                continue
            event = json.loads(line)
            if event.get("event_type") != "retrieval_event":
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if data.get("retrieval_event_id") == retrieval_event_id or data.get("event_id") == retrieval_event_id or event.get("event_id") == retrieval_event_id:
                # v2.5.0 B4: propagate the FULL envelope, not a subset.
                # retrieval_event_id is injected by emit() for retrieval events.
                ctx = {_k: data.get(_k, "") for _k in ENVELOPE_KEYS}
                ctx["provenance"] = data.get("provenance")
                ctx["requester"] = data.get("requester")
                ctx["retrieval_event_id"] = (
                    data.get("retrieval_event_id") or retrieval_event_id
                )
                return ctx
    except Exception:
        return {}
    return {}

def _context_for_payload(event_type: str, data: dict, context: dict | None = None) -> dict | None:
    if context:
        return context
    if not isinstance(data, dict):
        return None
    iid = data.get("intervention_id", "")
    if iid and iid in _CHAIN_CONTEXT_BY_INTERVENTION:
        return dict(_CHAIN_CONTEXT_BY_INTERVENTION[iid])
    rid = data.get("retrieval_event_id", "")
    if rid:
        ctx = _context_for_retrieval_id(rid)
        if ctx and iid:
            _CHAIN_CONTEXT_BY_INTERVENTION[iid] = dict(ctx)
        return ctx or None
    return None

def _remember_chain_context(event_type: str, data: dict) -> None:
    if not isinstance(data, dict):
        return
    iid = data.get("intervention_id", "")
    if not iid:
        return
    if event_type == "intervention_event" and data.get("retrieval_event_id"):
        # v2.5.0 B4: remember the FULL envelope for downstream events
        # (invocation/completion/outcome), not a subset. requester stays as
        # the nested object; the flat peer ids are part of the envelope.
        ctx = {_k: data.get(_k, "") for _k in ENVELOPE_KEYS}
        ctx["provenance"] = data.get("provenance")
        ctx["requester"] = data.get("requester")
        ctx["retrieval_event_id"] = data.get("retrieval_event_id", "")
        _CHAIN_CONTEXT_BY_INTERVENTION[iid] = ctx

# ── Core emit ──

def emit(event_type: str, data: dict, context: dict | None = None) -> Optional[str]:
    """
    Emit an event to the JSONL log. Thread-safe, append-only.
    Returns event_id or None on error (never blocks the caller).
    """
    context = _context_for_payload(event_type, data, context)
    data = _mandatory244(event_type, data, context=context)
    if context:
        for _k in ENVELOPE_KEYS:
            if _k == "provenance":
                if _k not in data or not data.get(_k):
                    data[_k] = context.get(_k, {})
            elif _k not in data or not data.get(_k):
                data[_k] = context.get(_k, "")
    # v2.5.0: producer identity — every event states which component emitted it.
    producer = data.get("producer")
    if not isinstance(producer, dict):
        surface = ((context or {}).get("producer_surface", "") or data.get("producer_surface", "")
                   or current_surface() or "")
        if surface not in VALID_SURFACES:
            surface = "unknown"
        producer = {
            "component": "capability_reuse_plugin",
            "version": "2.6.0",
            "surface": surface,
        }
        data["producer"] = producer
    # v2.5.0: top-level trace_id for trivial joins across the chain.
    if not data.get("trace_id"):
        trace_id = (context or {}).get("trace_id", "")
        if not trace_id:
            trace_id = data.get("session_id") or ""
        if trace_id:
            data["trace_id"] = trace_id
    _remember_chain_context(event_type, data)
    if event_type not in VALID_EVENTS:
        return None

    event_id = _uuid()
    if event_type == "retrieval_event":
        data = dict(data)
        data["event_id"] = event_id
        data["retrieval_event_id"] = event_id
    try:
        _ensure_dir()
        with _write_lock:
            event = {
                "event_id": event_id,
                "event_type": event_type,
                "schema_version": SCHEMA_VERSION,
                "timestamp": _now(),
                "seq": _next_seq_unlocked(),
                # v2.5.0 (spec 4): top-level trace_id for trivial joins across
                # the whole chain — consumers never reconstruct IDs from
                # timestamps.
                "trace_id": data.get("trace_id", ""),
                "data": data,
            }
            with open(EVENT_LOG, "a") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event_id
    except OSError:
        return None  # silent — never block execution for logging

# ── Event-specific helpers ──

def emit_hook_conformance(hermes_version: str, plugin_version: str,
                          platform: str, results: list[dict],
                          passed: int, failed: int, skipped: int,
                          plugin_source: str = "", artifact_hash: str = "",
                          active_same_name: list[str] | None = None):
    """§3.3 conformance suite result."""
    return emit("hook_conformance_event", {
        "hermes_version": hermes_version,
        "plugin_version": plugin_version,
        "platform": platform,
        "results": results,
        "total_passed": passed,
        "total_failed": failed,
        "total_skipped": skipped,
        "plugin_source": plugin_source,
        "artifact_hash": artifact_hash,
        "active_same_name": active_same_name or [],
    })

def emit_controller_health(integration_mode: str, healthy: bool,
                           intervention_count: int, pre_flight_ms: float):
    """Periodic controller health heartbeat."""
    return emit("controller_health_event", {
        "integration_mode": integration_mode,
        "healthy": healthy,
        "intervention_count": intervention_count,
        "pre_flight_latency_ms": round(pre_flight_ms, 2),
    })

def emit_retrieval(session_id: str, user_message_preview: str,
                   candidates: list[dict], top_score: float,
                   intervened: bool, latency_ms: float,
                   episode_id: str = "", turn_id: str = "", task_id: str = "",
                   tool_call_id: str = "", shadow_mode: bool = True,
                   config_version: str = "text-v1", provenance: str | None = None,
                   provenance_detail: str = "", provenance_source: str = "",
                   requester: dict | None = None, validated_inputs: dict | None = None,
                   redaction_status: str = "applied", traffic_type: str = "",
                   second_score: float = 0.0, score_margin: float = 0.0,
                   intervention_threshold: float = 0.0, minimum_margin: float = 0.0,
                   request_effect: str = "", capability_effect: str = "",
                   whole_request_covered: bool | None = None, eligibility: str = "",
                   eligibility_reason: str = "", dispatch: str = "none",
                   trace_id: str = "", requester_peer_id: str = "",
                   processing_peer_id: str = "", target_peer_id: str = "",
                   collector_peer_id: str = "", producer_surface: str = "",
                   retriever_executed: bool | None = None,
                   retriever_version: str = "", registry_version: str = "",
                   retrieval_threshold: float = 0.0, candidate_count: int | None = None,
                   filter_rejection_reasons: list | None = None,
                   retrieval_stages: dict | None = None):
    """Retrieval attempt result (shadow or active), with labelable candidate evidence."""
    safe_candidates = []
    for c in candidates[:10]:
        item = dict(c)
        if "preview" in item:
            item["preview"] = redact_preview(item["preview"], 200)
        safe_candidates.append(item)
    return emit("retrieval_event", {
        "session_id": redact_preview(session_id, 120),
        "episode_id": episode_id or redact_preview(session_id, 120),
        "turn_id": turn_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "user_message_preview": redact_preview(user_message_preview, 200),
        "redacted_text": redact_preview(user_message_preview, 500),
        "redaction_status": redaction_status,
        "requester": requester or {"actor_type": "unknown", "actor_id": "unknown", "request_channel": "unknown", "requester_peer_id": "", "processing_peer_id": ""},
        "validated_inputs": validated_inputs or {},
        "traffic_type": traffic_type or "unknown",
        "target_peer_id": target_peer_id or ((validated_inputs or {}).get("target_peer_id") or (((validated_inputs or {}).get("peer_list") or [""])[0] if isinstance((validated_inputs or {}).get("peer_list"), list) else "")),
        "processing_peer_id": processing_peer_id or (requester or {}).get("processing_peer_id", ""),
        "requester_peer_id": requester_peer_id or (requester or {}).get("requester_peer_id", ""),
        "collector_peer_id": collector_peer_id,
        "trace_id": trace_id or session_id,
        "retriever_executed": retriever_executed,
        "retriever_version": retriever_version,
        "registry_version": registry_version,
        "retrieval_threshold": retrieval_threshold,
        "filter_rejection_reasons": filter_rejection_reasons or [],
        # v2.5.0 (spec 5): explicit stage semantics. When the caller does not
        # supply stages (observer path), default to honest non-evaluation:
        # coverage/eligibility are NOT evaluated and never default to values
        # that imply a successful evaluation. Zero candidates after a real
        # retrieval → eligibility = not_applicable, never False/True.
        "retrieval_stages": retrieval_stages or {
            "retrieval": {"executed": retriever_executed is True, "candidate_count": len(candidates)},
            "coverage": {
                "evaluated": bool(candidates),
                "whole_request_covered": whole_request_covered if candidates else None,
            },
            "eligibility": {
                "evaluated": bool(candidates),
                "eligible": (eligibility == "accepted") if candidates else ("not_applicable" if retriever_executed is True else None),
            },
        },
        "producer_surface": producer_surface,
        "top_capability": (candidate_label(safe_candidates[0]) if safe_candidates else ""),
        "candidate_count": len(candidates) if candidate_count is None else candidate_count,
        "candidates": safe_candidates,
        "top_score": round(top_score, 4),
        "second_score": round(second_score, 4),
        "score_margin": round(score_margin, 4),
        "intervention_threshold": round(intervention_threshold, 4),
        "minimum_margin": round(minimum_margin, 4),
        "request_effect": request_effect or "unknown",
        "capability_effect": capability_effect or "unknown",
        # v2.5.0 (spec 5): never claim coverage with zero candidates —
        # whole_request_covered is null when nothing was evaluated.
        "whole_request_covered": whole_request_covered if candidates else None,
        "eligibility": eligibility or ("accepted" if intervened else "rejected"),
        "eligibility_reason": eligibility_reason,
        "dispatch": dispatch,
        "intervened": intervened,
        "shadow_mode": shadow_mode,
        "config_version": config_version,
        "provenance": normalize_provenance(provenance, provenance_detail, provenance_source),
        "latency_ms": round(latency_ms, 2),
    })

def emit_intervention(intervention_id: str, episode_id: str,
                      capability_id: str, capability_version: str,
                      retrieval_score: float, score_margin: float,
                      integration_mode: str, active_plugins: list[str] | None = None,
                      injection_position: int = 0, session_id: str = "",
                      turn_id: str = "", retrieval_event_id: str = ""):
    """Intervention created."""
    return emit("intervention_event", {
        "intervention_id": intervention_id,
        "session_id": session_id,
        "episode_id": episode_id,
        "turn_id": turn_id,
        "retrieval_event_id": retrieval_event_id,
        "capability_id": capability_id,
        "capability_version": capability_version,
        "retrieval_score": round(retrieval_score, 4),
        "score_margin": round(score_margin, 4),
        "integration_mode": integration_mode,
        "active_plugins": active_plugins or [],
        "injection_position": injection_position,
    })

def emit_state_transition(intervention_id: str, from_state: str,
                          to_state: str, reason: str = ""):
    """Protocol state machine transition."""
    return emit("protocol_state_transition", {
        "intervention_id": intervention_id,
        "from_state": from_state,
        "to_state": to_state,
        "reason": reason,
    })

def emit_invocation(intervention_id: str, capability_id: str,
                    capability_version: str, contract_hash: str = "",
                    input_validation: str = "passed",
                    invocation_status: str = "succeeded",
                    failure_code: str | None = None,
                    partial_effect_state: str = "none",
                    fallback_authorization_id: str | None = None,
                    latency_ms: float = 0.0, invocation_id: str = "",
                    validated_inputs: dict | None = None,
                    preview_target_peer_id: str = "",
                    dispatcher_target_peer_id: str = "",
                    result_target_peer_id: str = ""):
    """invoke_capability result."""
    return emit("capability_invocation_event", {
        "intervention_id": intervention_id,
        "invocation_id": invocation_id or _uuid(),
        "capability_id": capability_id,
        "capability_version": capability_version,
        "contract_hash": contract_hash,
        "input_validation": input_validation,
        "invocation_status": invocation_status,
        "failure_code": failure_code,
        "partial_effect_state": partial_effect_state,
        "fallback_authorization_id": fallback_authorization_id,
        "latency_ms": round(latency_ms, 2),
        "validated_inputs": validated_inputs or {},
        "preview_target_peer_id": preview_target_peer_id,
        "dispatcher_target_peer_id": dispatcher_target_peer_id,
        "result_target_peer_id": result_target_peer_id,
    })

def emit_fallback_authorization(intervention_id: str, token_id: str,
                                invocation_id: str, failure_code: str,
                                ttl_seconds: int,
                                action: str = "issued"):
    """Fallback token lifecycle: issued, consumed, expired, cancelled."""
    return emit("fallback_authorization_event", {
        "intervention_id": intervention_id,
        "token_id": token_id,
        "invocation_id": invocation_id,
        "failure_code": failure_code,
        "ttl_seconds": ttl_seconds,
        "action": action,
    })

def emit_failure_escalation(intervention_id: str, invocation_id: str,
                            effect_class: str, failure_code: str,
                            tool_call_id: str = ""):
    """Post-failure escalation for mutation/unknown effects."""
    return emit("post_failure_escalation_event", {
        "intervention_id": intervention_id,
        "invocation_id": invocation_id,
        "effect_class": effect_class,
        "failure_code": failure_code,
        "tool_call_id": tool_call_id,
    })

def emit_bypass(intervention_id: str, capability_id: str,
                capability_version: str, reason_code: str,
                feature_id: str = "", detail: str = "",
                prior_invocation_id: str = "",
                failure_code: str = "",
                fallback_authorization_id: str = ""):
    """Bypass record submitted by agent."""
    return emit("bypass_event", {
        "intervention_id": intervention_id,
        "capability_id": capability_id,
        "capability_version": capability_version,
        "reason_code": reason_code,
        "feature_id": feature_id,
        "detail": redact_preview(detail, 500),
        "prior_invocation_id": prior_invocation_id,
        "failure_code": failure_code,
        "fallback_authorization_id": fallback_authorization_id,
    })

def emit_execute_code_start(code_preview: str = "", code_hash: str = "",
                            session_id: str = "", episode_id: str = "",
                            turn_id: str = "", task_id: str = "",
                            tool_call_id: str = "", retrieval_event_id: str = ""):
    """execute_code attempt started."""
    return emit("execute_code_started_event", {
        "code_preview": redact_preview(code_preview, 200),
        "code_hash": code_hash,
        "session_id": session_id,
        "episode_id": episode_id or session_id,
        "turn_id": turn_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "retrieval_event_id": retrieval_event_id,
    })

def emit_execute_code_complete(code_hash: str = "", outcome: str = "success",
                               duration_ms: float = 0.0,
                               error: str | None = None,
                               block_origin: str = "", session_id: str = "",
                               episode_id: str = "", turn_id: str = "",
                               task_id: str = "", tool_call_id: str = "",
                               retrieval_event_id: str = ""):
    """execute_code completed."""
    return emit("execute_code_completed_event", {
        "code_hash": code_hash,
        "session_id": session_id,
        "episode_id": episode_id or session_id,
        "turn_id": turn_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "retrieval_event_id": retrieval_event_id,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
        "error_preview": redact_preview(error, 200) if error else None,
        "block_origin": block_origin,
    })

def emit_surface_execution_start(execution_surface: str = "hmp_plugin",
                                 surface_preview: str = "",
                                 session_id: str = "", episode_id: str = "",
                                 turn_id: str = "", task_id: str = "",
                                 tool_call_id: str = "", retrieval_event_id: str = "",
                                 requester_peer_id: str = "", processing_peer_id: str = "",
                                 trace_id: str = "", traffic_type: str = "",
                                 producer_surface: str = ""):
    """v2.5.0: generic surface (HMP ingress, gateway, etc.) started processing.

    NOT execute_code — reserved exclusively for real execute_code calls.
    Replaces the v2.4.16 misuse of execute_code_started_event for HMP
    message processing that never ran execute_code.
    """
    return emit("surface_execution_started_event", {
        "execution_surface": execution_surface,
        "surface_preview": redact_preview(surface_preview, 200),
        "session_id": session_id,
        "episode_id": episode_id or session_id,
        "turn_id": turn_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "retrieval_event_id": retrieval_event_id,
        "requester_peer_id": requester_peer_id,
        "processing_peer_id": processing_peer_id,
        "trace_id": trace_id,
        "traffic_type": traffic_type,
        "producer_surface": producer_surface,
    })

def emit_surface_execution_complete(execution_surface: str = "hmp_plugin",
                                    outcome: str = "success",
                                    duration_ms: float = 0.0,
                                    error: str | None = None,
                                    session_id: str = "", episode_id: str = "",
                                    turn_id: str = "", task_id: str = "",
                                    tool_call_id: str = "", retrieval_event_id: str = "",
                                    requester_peer_id: str = "", processing_peer_id: str = "",
                                    trace_id: str = "", traffic_type: str = "",
                                    producer_surface: str = ""):
    """v2.5.0: generic surface finished processing (see emit_surface_execution_start)."""
    return emit("surface_execution_completed_event", {
        "execution_surface": execution_surface,
        "session_id": session_id,
        "episode_id": episode_id or session_id,
        "turn_id": turn_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "retrieval_event_id": retrieval_event_id,
        "requester_peer_id": requester_peer_id,
        "processing_peer_id": processing_peer_id,
        "trace_id": trace_id,
        "traffic_type": traffic_type,
        "producer_surface": producer_surface,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
        "error_preview": redact_preview(error, 200) if error else None,
    })

def emit_alternate_execution(tool_name: str, args_preview: str = "",
                             task_id: str = ""):
    """Monitored alternate execution surface used."""
    return emit("alternate_execution_event", {
        "tool_name": tool_name,
        "args_preview": redact_preview(args_preview, 200),
        "task_id": task_id,
    })

def emit_observation(capability_id: str, capability_version: str,
                     syntax_hash: str = "", effect_class: str = "unknown",
                     observation_coverage: dict | None = None):
    """Post-execution observation."""
    return emit("observation_event", {
        "capability_id": capability_id,
        "capability_version": capability_version,
        "syntax_hash": syntax_hash,
        "effect_class": effect_class,
        "observation_coverage": observation_coverage or {},
    })

def emit_outcome(episode_id: str, intervention_id: str,
                 final_state: str, outcome: str,
                 total_latency_ms: float = 0.0,
                 registry_snapshot: str = ""):
    """Episode outcome summary."""
    return emit("outcome_event", {
        "episode_id": episode_id,
        "intervention_id": intervention_id,
        "final_state": final_state,
        "outcome": outcome,
        "total_latency_ms": round(total_latency_ms, 2),
        "registry_snapshot": registry_snapshot,
    })

def emit_review(episode_id: str, reviewer: str, verdict: str,
                bypass_justified: bool | None = None,
                notes: str = ""):
    """Human review record."""
    return emit("review_event", {
        "episode_id": episode_id,
        "reviewer": reviewer,
        "verdict": verdict,
        "bypass_justified": bypass_justified,
        "notes": notes[:500],
    })

def emit_validation(episode_id: str, capability_id: str,
                    capability_version: str, validation_mode: str,
                    result: str, equivalence_score: float | None = None):
    """Validation result."""
    return emit("validation_event", {
        "episode_id": episode_id,
        "capability_id": capability_id,
        "capability_version": capability_version,
        "validation_mode": validation_mode,
        "result": result,
        "equivalence_score": round(equivalence_score, 4) if equivalence_score else None,
    })

def emit_trust_transition(capability_id: str, capability_version: str,
                          from_state: str, to_state: str, reason: str = ""):
    """Capability version trust state change."""
    return emit("trust_transition_event", {
        "capability_id": capability_id,
        "capability_version": capability_version,
        "from_state": from_state,
        "to_state": to_state,
        "reason": reason,
    })

# ── Stats ──

def get_stats() -> dict:
    """Quick stats on the event log."""
    if not EVENT_LOG.exists():
        return {"total_events": 0, "file": str(EVENT_LOG)}

    try:
        with open(EVENT_LOG) as f:
            lines = [l.strip() for l in f if l.strip()]
        return {
            "total_events": len(lines),
            "file": str(EVENT_LOG),
            "size_bytes": EVENT_LOG.stat().st_size,
        }
    except OSError:
        return {"total_events": -1, "error": "cannot_read"}

def get_events_by_type(event_type: str, limit: int = 100) -> list[dict]:
    """Get recent events of a specific type."""
    if not EVENT_LOG.exists():
        return []
    try:
        with open(EVENT_LOG) as f:
            lines = [l.strip() for l in f if l.strip()]
        results = []
        for line in reversed(lines):
            try:
                ev = json.loads(line)
                if ev.get("event_type") == event_type:
                    results.append(ev)
                    if len(results) >= limit:
                        break
            except json.JSONDecodeError:
                pass
        return results
    except OSError:
        return []

def get_all_events(limit: int = 50) -> list[dict]:
    """Get most recent events."""
    if not EVENT_LOG.exists():
        return []
    try:
        with open(EVENT_LOG) as f:
            lines = [l.strip() for l in f if l.strip()]
        results = []
        for line in reversed(lines):
            try:
                results.append(json.loads(line))
                if len(results) >= limit:
                    break
            except json.JSONDecodeError:
                pass
        return results
    except OSError:
        return []