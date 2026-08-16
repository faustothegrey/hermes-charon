from __future__ import annotations
"""Reviewer-facing queue builder for capability-reuse v2.4.10."""
import csv
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from execution_plan import build_execution_plan, redact_execution_plan
except Exception:  # import when loaded from package-ish paths
    import importlib.util
    _p = Path(__file__).resolve().parent / "execution_plan.py"
    _spec = importlib.util.spec_from_file_location("execution_plan", str(_p))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    build_execution_plan = _mod.build_execution_plan
    redact_execution_plan = _mod.redact_execution_plan

REVIEW_SCHEMA_VERSION = "1.0"
ORGANIC_TRAFFIC_TYPES = {"organic_user", "organic_peer"}
EXCLUDED_TRAFFIC_TYPES = {"acceptance_test", "calibration_probe", "operator_seeded", "legacy_unclassified", "unknown"}
ACTOR_TYPES = {"human", "agent", "scheduler", "service", "unknown"}
REQUEST_CHANNELS = {"telegram", "hmp", "cron", "local", "api", "gateway", "unknown"}
LABELS = {"ACCEPT", "REJECT", "UNSURE"}
EXPECTED_PLUGIN_VERSION = "2.6.0"
EXPECTED_COHORT_LABEL = os.environ.get("CAPABILITY_REUSE_EXPECTED_COHORT_LABEL", "v2.5.0_live")

REASON_CODES = {
    "exact_match", "partial_coverage", "wrong_capability", "wrong_target", "effect_mismatch",
    "informational_only", "code_generation_request", "composite_request", "requester_unclear",
    "preview_incorrect", "insufficient_context", "other",
}

_REDACT_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)[^\s,;&]+"), r"\1\2[REDACTED]"),
    (re.compile(r"https?://([^:/\s]+):([^@/\s]+)@"), "https://[REDACTED]@"),
    (re.compile(r"([?&](?:token|key|password|secret|api_key)=)[^&#\s]+", re.I), r"\1[REDACTED]"),
    (re.compile(r'/(?:home|root)/[^\s,;:\'\"]+'), "[PATH]"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_text(value: Any, max_len: int = 500) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text[:max_len]


def neutralize_csv(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.lstrip(" 	\r\n")
        if stripped[:1] in ("=", "+", "-", "@"):
            return "'" + value
    return value


def pseudonymize_identity(value: Any, prefix: str = "id") -> str:
    text = str(value or "")
    if not text or text == "unknown":
        return "unknown"
    if ":sha256:" in text or text.startswith("hmp:") or text.startswith("peer"):
        return text
    salt = os.environ.get("CAPABILITY_REUSE_REVIEW_SALT", "capability-reuse-review-v1")
    return "%s:sha256:%s" % (prefix, hashlib.sha256((salt + "|" + text).encode("utf-8")).hexdigest()[:16])


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("data") if isinstance(event.get("data"), dict) else event


def split_capability(cap: str) -> tuple[str, str]:
    text = str(cap or "")
    if "@" in text:
        a, b = text.rsplit("@", 1)
        return a, b
    return text, ""


def candidate_name(candidate: dict[str, Any]) -> str:
    if not isinstance(candidate, dict):
        return ""
    if candidate.get("capability"):
        return str(candidate.get("capability"))
    cid = candidate.get("capability_id") or candidate.get("id") or ""
    ver = candidate.get("capability_version") or candidate.get("version") or ""
    return "%s@%s" % (cid, ver) if cid and ver else str(cid)


def normalize_requester(value: dict[str, Any] | None, processing_peer_id: str = "") -> dict[str, Any]:
    src = value if isinstance(value, dict) else {}
    actor_type = src.get("actor_type") if src.get("actor_type") in ACTOR_TYPES else "unknown"
    channel = src.get("request_channel") if src.get("request_channel") in REQUEST_CHANNELS else "unknown"
    requester_peer = str(src.get("requester_peer_id") or "")
    actor_id = str(src.get("actor_id") or "")
    processing = str(src.get("processing_peer_id") or processing_peer_id or src.get("peer_id") or "")
    if channel == "hmp" and requester_peer:
        requester_type = "hmp_peer"
        if not actor_id:
            actor_id = "hmp:%s" % requester_peer
        if actor_type == "unknown":
            actor_type = "agent"
    elif channel == "telegram":
        requester_type = "telegram"
        actor_id = pseudonymize_identity(actor_id, "telegram")
        if actor_type == "unknown":
            actor_type = "human"
    elif channel == "cron":
        requester_type = "cron"
        if actor_type == "unknown":
            actor_type = "scheduler"
    elif channel in {"api", "gateway", "local"}:
        requester_type = channel
    else:
        requester_type = "unknown"
    return {
        "actor_type": actor_type,
        "requester_type": requester_type,
        "requester_id": actor_id or "unknown",
        "requester_peer_id": requester_peer,
        "request_channel": channel,
        "processing_peer_id": processing,
    }


def stable_review_id(retrieval_event_id: str, capability_id: str, capability_version: str, candidate_rank: int) -> str:
    raw = "%s|%s|%s|%s" % (retrieval_event_id, capability_id, capability_version, candidate_rank)
    return "review_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _validated_inputs(d: dict[str, Any]) -> dict[str, Any]:
    vi = d.get("validated_inputs") if isinstance(d.get("validated_inputs"), dict) else None
    if vi is not None:
        return dict(vi)
    # Compatibility fallback for legacy generated rows: infer only peer labels, never addresses.
    text = str(d.get("user_message_preview") or "")
    m = re.search(r"\b(peer\d+|trixie)\b", text, re.I)
    return {"peer_list": [m.group(1).lower()]} if m else {}


def formal_holdout_validation(event: dict[str, Any], data: dict[str, Any], requester: dict[str, Any]) -> tuple[bool, list[str]]:
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    reasons: list[str] = []
    # v2.5.0: schema 1.3 required.
    if event.get("schema_version") != "1.3": reasons.append("schema_version_not_1_3")
    if data.get("plugin_version") != EXPECTED_PLUGIN_VERSION: reasons.append("plugin_version_not_%s" % EXPECTED_PLUGIN_VERSION.replace(".", "_"))
    if not data.get("deployment_id"): reasons.append("missing_deployment_id")
    if not data.get("plugin_artifact_hash") or str(data.get("plugin_artifact_hash", "")).startswith("placeholder"):
        reasons.append("missing_or_placeholder_artifact_hash")
    if data.get("cohort_label") != EXPECTED_COHORT_LABEL: reasons.append("wrong_cohort_label")
    if provenance.get("stream") != "organic_live": reasons.append("not_organic_live_provenance")
    if provenance.get("valid") is not True:
        reasons.append(provenance.get("reason") or "invalid_provenance")
    # P0-1 (reviewer 2026-08-16): provenance from the process environment
    # must NEVER be eligible for the formal holdout — a global
    # CAPABILITY_REUSE_PROVENANCE=organic_live would otherwise silently
    # contaminate the cohort. Only request-scoped/trusted sources count.
    _psrc = str(provenance.get("source") or "").strip()
    if _psrc in ("process_env", "missing", ""):
        reasons.append("provenance_source_not_request_scoped")
    elif _psrc.startswith("hook_context") or _psrc == "request":
        pass  # request-scoped/trusted
    else:
        reasons.append("provenance_source_not_request_scoped")
    # v2.5.0: traffic taxonomy — registry_sync/test/acceptance/calibration
    # must automatically evaluate to false.
    if data.get("traffic_type") not in ORGANIC_TRAFFIC_TYPES: reasons.append("non_organic_traffic_type")
    if data.get("traffic_type") in {"registry_sync", "test", "acceptance", "calibration", "cron", "retry"}:
        reasons.append("excluded_traffic_class")
    if requester.get("requester_type") == "unknown": reasons.append("unknown_requester")
    if not (requester.get("processing_peer_id") or data.get("peer_id")): reasons.append("missing_processing_peer_id")
    if not data.get("requester_peer_id"): reasons.append("missing_requester_peer_id")
    # v2.5.0: complete trace envelope required.
    if not data.get("trace_id"): reasons.append("missing_trace_id")
    # v2.5.0 spec 2: canonical producer identity is producer.surface
    # (the flat producer_surface key is a legacy secondary field). Read the
    # canonical object first; fall back to the legacy key only if absent.
    _producer = data.get("producer")
    _surface = _producer.get("surface") if isinstance(_producer, dict) else None
    if _surface in (None, "", "unknown"):
        _surface = data.get("producer_surface")
    if _surface in (None, "", "unknown"):
        reasons.append("missing_producer_surface")
    # P0-11 / P0-2 (reviewer 2026-08-16): a clean-cohort envelope must carry
    # BOTH timestamps; a missing event or deployment timestamp is a rejection
    # reason, and only then is the ordering check applied.
    _ev_ts = event.get("timestamp") or data.get("timestamp") or ""
    _dep_ts = data.get("deployment_timestamp") or ""
    if not _ev_ts:
        reasons.append("missing_event_timestamp")
    if not _dep_ts:
        reasons.append("missing_deployment_timestamp")
    if _ev_ts and _dep_ts:
        try:
            from datetime import datetime
            _fmt = "%Y-%m-%dT%H:%M:%S%z"
            _ev_dt = datetime.strptime(_ev_ts, _fmt)
            _dep_dt = datetime.strptime(_dep_ts, _fmt)
            if _ev_dt < _dep_dt:
                reasons.append("event_before_deployment")
        except (ValueError, TypeError):
            reasons.append("invalid_timestamp")
    return (len(reasons) == 0), reasons


def _candidate_score_margin(candidates: list[dict[str, Any]], candidate_rank: int) -> Any:
    if not candidates or candidate_rank < 1 or candidate_rank > len(candidates):
        return ""
    cur = candidates[candidate_rank - 1].get("score")
    nxt = candidates[candidate_rank].get("score") if candidate_rank < len(candidates) else 0
    try:
        return round(float(cur) - float(nxt), 4)
    except Exception:
        return ""


def build_review_record(event: dict[str, Any], candidate_rank: int = 1, latest_label: dict[str, Any] | None = None) -> dict[str, Any]:
    d = payload(event)
    candidates = d.get("candidates") if isinstance(d.get("candidates"), list) else []
    if not candidates and d.get("top_capability"):
        candidates = [{"capability": d.get("top_capability"), "score": d.get("top_score"), "effect_class": d.get("capability_effect") or d.get("effect_class")}]
    if candidate_rank < 1 or candidate_rank > len(candidates):
        raise ValueError("candidate_rank out of range")
    cand = candidates[candidate_rank - 1]
    cap = candidate_name(cand)
    cap_id, cap_ver = split_capability(cap)
    retrieval_event_id = str(event.get("event_id") or d.get("retrieval_event_id") or d.get("event_id") or "")
    review_id = stable_review_id(retrieval_event_id, cap_id, cap_ver, candidate_rank)
    provenance = d.get("provenance") if isinstance(d.get("provenance"), dict) else {}
    processing_peer = str(d.get("processing_peer_id") or d.get("peer_id") or "")
    requester = normalize_requester(d.get("requester"), processing_peer)
    redacted = redact_text(d.get("redacted_text") or d.get("user_message_preview") or "")
    raw_ref = "event:%s" % retrieval_event_id
    inputs = _validated_inputs(d)
    plan = redact_execution_plan(build_execution_plan(cap_id, cap_ver, inputs))
    if plan.get("preview_status") in {"unsupported", "invalid_input"} and d.get("eligibility_result") == "eligible_shadow_only":
        eligibility = "ineligible_environment_constraint"
    elif cand.get("eligible_for_intervention") is False:
        eligibility = "ineligible_candidate_filter"
    else:
        eligibility = d.get("eligibility_result") or ("eligible_shadow_only" if plan.get("preview_status") == "exact" else "ineligible_environment_constraint")
    rejection_reasons = d.get("filter_rejection_reasons") or d.get("rejection_reasons") or cand.get("ineligibility_reasons") or []
    score_margin = d.get("score_margin")
    if score_margin in (None, ""):
        score_margin = _candidate_score_margin(candidates, candidate_rank)
    formal_ok, formal_reasons = formal_holdout_validation(event, d, requester)
    second = candidates[1] if len(candidates) > 1 else {}
    human = {"label": "", "reason_code": "", "notes": "", "reviewer": "", "reviewed_at": ""}
    if latest_label:
        human.update({k: latest_label.get(k, human.get(k, "")) for k in human})
    return {
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "review_id": review_id,
        "timestamp": d.get("timestamp") or event.get("timestamp") or "",
        "event_schema_version": event.get("schema_version") or d.get("schema_version") or "",
        "cohort": {
            "deployment_id": d.get("deployment_id") or "",
            "deployment_timestamp": d.get("deployment_timestamp") or "",
            "plugin_version": d.get("plugin_version") or "",
            "plugin_artifact_hash": d.get("plugin_artifact_hash") or "",
            "cohort_label": d.get("cohort_label") or "",
        },
        "requester": requester,
        "request": {
            "redacted_text": redacted,
            "raw_request_ref": raw_ref,
            "redaction_status": "applied",
            "traffic_type": d.get("traffic_type") or provenance.get("stream") or "unknown",
            "provenance_source": provenance.get("source") or d.get("provenance_source") or "unknown",
            "session_id": d.get("session_id") or "",
            "turn_id": d.get("turn_id") or "",
            "task_id": d.get("task_id") or "",
        },
        "retrieval": {
            "candidate_capability": cap,
            "candidate_rank": candidate_rank,
            "candidate_score": cand.get("score") if cand.get("score") is not None else d.get("top_score"),
            "second_capability": candidate_name(second) if second else "",
            "second_score": second.get("score", "") if isinstance(second, dict) else "",
            "score_margin": score_margin,
            "eligibility_result": eligibility,
            "rejection_reasons": sorted(set(rejection_reasons)) if isinstance(rejection_reasons, list) else [str(rejection_reasons)],
        },
        "intended_execution": plan,
        "formal_holdout_eligible": formal_ok,
        "formal_holdout_rejection_reasons": formal_reasons,
        # v2.5.0: review row linked to the same trace — trivial joins.
        "trace_id": d.get("trace_id") or d.get("session_id") or "",
        "retrieval_event_id_ref": retrieval_event_id,
        "human_review": human,
    }


def append_human_label(path: Path | str, review_id: str, label: str, reason_code: str, notes: str, reviewer: str, supersedes_label_id: str | None = None, now: str | None = None) -> dict[str, Any]:
    if label not in LABELS:
        raise ValueError("invalid label")
    if reason_code not in REASON_CODES:
        raise ValueError("invalid reason_code")
    allowed_by_label = {
        "ACCEPT": {"exact_match"},
        "REJECT": REASON_CODES - {"exact_match", "insufficient_context", "requester_unclear"},
        "UNSURE": {"insufficient_context", "requester_unclear", "other"},
    }
    if reason_code not in allowed_by_label[label]:
        raise ValueError("label/reason_code mismatch")
    row = {
        "label_id": "label_" + uuid.uuid4().hex[:16],
        "review_id": review_id,
        "label": label,
        "reason_code": reason_code,
        "notes": redact_text(notes, 500),
        "reviewer": pseudonymize_identity(reviewer, "reviewer"),
        "reviewed_at": now or utc_now(),
        "supersedes_label_id": supersedes_label_id,
    }
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_latest_labels(path: Path | str) -> dict[str, dict[str, Any]]:
    p = Path(path); latest = {}
    if not p.exists():
        return latest
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("review_id"):
            latest[row["review_id"]] = row
    return latest


def filter_organic_review_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in records:
        tt = ((r.get("request") or {}).get("traffic_type") or "unknown")
        if tt in ORGANIC_TRAFFIC_TYPES and r.get("formal_holdout_eligible") is True:
            out.append(r)
    return out

CSV_FIELDS = [
    "review_schema_version", "review_id", "timestamp", "event_schema_version",
    "actor_type", "requester_type", "requester_id", "requester_peer_id", "request_channel", "processing_peer_id",
    "redacted_text", "raw_request_ref", "redaction_status", "traffic_type", "provenance_source", "session_id", "turn_id", "task_id",
    "candidate_capability", "candidate_rank", "candidate_score", "second_capability", "second_score", "score_margin", "eligibility_result", "rejection_reasons",
    "preview_schema_version", "preview_status", "effect_class", "target_peer_id", "target_resolution_source", "executor_kind", "method", "endpoint", "timeout_seconds", "command_preview", "mutation_possible", "auth_mode", "credentials_exposed_in_preview",
    "formal_holdout_eligible", "label", "reason_code", "notes", "reviewer", "reviewed_at",
]


def flatten_record(r: dict[str, Any]) -> dict[str, Any]:
    reqr = r.get("requester") or {}; req = r.get("request") or {}; ret = r.get("retrieval") or {}; exe = r.get("intended_execution") or {}; hr = r.get("human_review") or {}
    row = {
        "review_schema_version": r.get("review_schema_version", ""), "review_id": r.get("review_id", ""), "timestamp": r.get("timestamp", ""), "event_schema_version": r.get("event_schema_version", ""),
        "actor_type": reqr.get("actor_type", ""), "requester_type": reqr.get("requester_type", ""), "requester_id": reqr.get("requester_id", ""), "requester_peer_id": reqr.get("requester_peer_id", ""), "request_channel": reqr.get("request_channel", ""), "processing_peer_id": reqr.get("processing_peer_id", ""),
        "redacted_text": req.get("redacted_text", ""), "raw_request_ref": req.get("raw_request_ref", ""), "redaction_status": req.get("redaction_status", ""), "traffic_type": req.get("traffic_type", ""), "provenance_source": req.get("provenance_source", ""), "session_id": req.get("session_id", ""), "turn_id": req.get("turn_id", ""), "task_id": req.get("task_id", ""),
        "candidate_capability": ret.get("candidate_capability", ""), "candidate_rank": ret.get("candidate_rank", ""), "candidate_score": ret.get("candidate_score", ""), "second_capability": ret.get("second_capability", ""), "second_score": ret.get("second_score", ""), "score_margin": ret.get("score_margin", ""), "eligibility_result": ret.get("eligibility_result", ""), "rejection_reasons": json.dumps(ret.get("rejection_reasons", []), ensure_ascii=False),
        "preview_schema_version": exe.get("preview_schema_version", ""), "preview_status": exe.get("preview_status", ""), "effect_class": exe.get("effect_class", ""), "target_peer_id": exe.get("target_peer_id", ""), "target_resolution_source": exe.get("target_resolution_source", ""), "executor_kind": exe.get("executor_kind", ""), "method": exe.get("method", ""), "endpoint": exe.get("endpoint", ""), "timeout_seconds": exe.get("timeout_seconds", ""), "command_preview": exe.get("command_preview", ""), "mutation_possible": exe.get("mutation_possible", ""), "auth_mode": exe.get("auth_mode", ""), "credentials_exposed_in_preview": exe.get("credentials_exposed_in_preview", ""),
        "formal_holdout_eligible": r.get("formal_holdout_eligible", ""), "label": hr.get("label", ""), "reason_code": hr.get("reason_code", ""), "notes": hr.get("notes", ""), "reviewer": hr.get("reviewer", ""), "reviewed_at": hr.get("reviewed_at", ""),
    }
    return {k: neutralize_csv(v) for k, v in row.items()}


def write_jsonl(path: Path | str, records: list[dict[str, Any]]) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_review_csv(path: Path | str, records: list[dict[str, Any]]) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in records:
            w.writerow(flatten_record(r))


def write_markdown_sample(path: Path | str, records: list[dict[str, Any]], limit: int = 10) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Capability-Reuse Human Review Queue Sample", "", "Generated from review_schema_version 1.0 records.", ""]
    for i, r in enumerate(records[:limit], 1):
        reqr = r["requester"]; req = r["request"]; ret = r["retrieval"]; exe = r["intended_execution"]
        lines += [
            "## Candidate %d" % i, "",
            "Requester:",
            "- Actor type: %s" % reqr.get("actor_type", ""),
            "- Requester type: %s" % reqr.get("requester_type", ""),
            "- Requester ID: %s" % reqr.get("requester_id", ""),
            "- Requester peer: %s" % (reqr.get("requester_peer_id") or ""),
            "- Request channel: %s" % reqr.get("request_channel", ""),
            "- Processing peer: %s" % reqr.get("processing_peer_id", ""), "",
            "Request:",
            "> %s" % req.get("redacted_text", ""), "",
            "Candidate capability:",
            "- %s" % ret.get("candidate_capability", ""),
            "- Rank: %s" % ret.get("candidate_rank", ""),
            "- Score: %s" % ret.get("candidate_score", ""),
            "- Eligibility: %s" % ret.get("eligibility_result", ""), "",
            "Would execute:",
            "- Preview status: %s" % exe.get("preview_status", ""),
            "- %s" % exe.get("command_preview", ""),
            "- Target peer: %s" % (exe.get("target_peer_id") or ""),
            "- Effect: %s" % exe.get("effect_class", ""),
            "- Auth mode: %s" % exe.get("auth_mode", ""),
            "- Credentials exposed in preview: %s" % exe.get("credentials_exposed_in_preview", ""), "",
            "Human label:",
            "- ACCEPT / REJECT / UNSURE", "",
            "Reason code:",
            "- exact_match / partial_coverage / wrong_capability / wrong_target / effect_mismatch / informational_only / code_generation_request / composite_request / requester_unclear / preview_incorrect / insufficient_context / other", "",
        ]
    p.write_text("\n".join(lines), encoding="utf-8")
