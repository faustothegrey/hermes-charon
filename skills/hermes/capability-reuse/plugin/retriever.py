from __future__ import annotations
"""
retriever.py — Capability Reuse Plugin: Pre-execution Retrieval Pipeline
=======================================================================
Builds the retrieval query from hook-visible inputs, searches the registry,
applies hard filters, scores candidates, and decides whether to intervene.

Pipeline (§4.1.2):
  request + focused context
    → redact secrets
    → construct retrieval text
    → semantic retrieval (text matching, Phase 0/1A)
    → apply hard filters (compatibility.check_all)
    → compatibility rerank
    → check confidence, margin, availability, trust
    → inject best match when all conditions pass
"""
import re, time, difflib, logging, uuid
from typing import Optional, Any
from dataclasses import dataclass, field

from . import registry as reg
from . import compatibility as comp
from . import event_store as events

logger = logging.getLogger("capability-reuse.retriever")

# ── Configuration ──
DEFAULT_INTERVENTION_THRESHOLD = 0.65  # minimum score to intervene (Phase 0 peer58/peer106 scope)
DEFAULT_MINIMUM_MARGIN = 0.05          # top - second >= margin (Phase 0 peer58/peer106 scope)
DEFAULT_RETRIEVAL_THRESHOLD = 0.30     # minimum score to log (shadow)

# ── Data classes ──

@dataclass
class RetrievalResult:
    """Result of a retrieval attempt."""
    intervention_id: str = ""
    capability_id: str = ""
    capability_version: str = ""
    retrieval_score: float = 0.0
    score_margin: float = 0.0
    contract_version: str = ""
    prompt_template_version: str = "reuse-intervention-v1"
    inputs_description: str = ""
    output_description: str = ""
    episode_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    task_id: str = ""
    tool_call_id: str = ""
    retrieval_event_id: str = ""
    intervened: bool = False
    candidates: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0

# ── Text matching (Phase 0/1A — no embeddings yet) ──

def _tokenize(text: str) -> set[str]:
    """Simple tokenization: lowercase, split on non-alphanumeric."""
    return set(re.sub(r'[^a-z0-9\s]', ' ', text.lower()).split())

def _text_similarity(query: str, candidate_texts: list[str]) -> float:
    """
    Simple text similarity score (0.0-1.0).
    Phase 0: token overlap + bigram overlap.
    Phase 1A: replace with embedding similarity.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    
    all_tokens = set()
    for ct in candidate_texts:
        all_tokens |= _tokenize(ct)
    
    if not all_tokens:
        return 0.0
    
    overlap = query_tokens & all_tokens
    # Jaccard-like: intersection / union
    union = query_tokens | all_tokens
    jaccard = len(overlap) / len(union) if union else 0
    
    # Bigram overlap bonus
    query_bigrams = {query[i:i+2] for i in range(len(query)-1)}
    candidate_bigrams = set()
    for ct in candidate_texts:
        for i in range(len(ct)-1):
            candidate_bigrams.add(ct[i:i+2].lower())
    bigram_overlap = query_bigrams & candidate_bigrams
    bigram_union = query_bigrams | candidate_bigrams
    bigram_score = len(bigram_overlap) / len(bigram_union) if bigram_union else 0
    
    return (jaccard * 0.6 + bigram_score * 0.4)

def _keyword_match(query: str, keywords: list[str]) -> float:
    """
    Bonus score from keyword overlap.
    Returns fraction of keywords found in query (0.0-1.0).
    """
    if not keywords:
        return 0.0
    ql = query.lower()
    found = sum(1 for kw in keywords if kw.lower() in ql)
    return found / len(keywords)

# ── Focused context construction (§4.1.1) ──

def build_query(session_id: str = "",
                user_message: str = "",
                hook_context: dict | None = None) -> str:
    """
    Build a retrieval query from hook-visible inputs only.
    No planner state, no tool state — only what pre_llm_call delivers.
    
    Inputs:
      - user_message: the current user request
      - hook_context: kwargs from the hook (may contain conversation_history)
    
    Returns a single query string for retrieval.
    """
    parts = [user_message] if user_message else []
    
    # Extract targets, outputs, constraints from conversation history
    if hook_context:
        history = hook_context.get("conversation_history", [])
        if isinstance(history, list):
            # Scan last 5 messages for explicit targets and constraints
            for msg in history[-5:]:
                content = ""
                if isinstance(msg, dict):
                    content = msg.get("content", "") or msg.get("text", "")
                elif isinstance(msg, str):
                    content = msg
                
                if not content:
                    continue
                
                # Deterministic extraction: look for patterns
                for pattern in [
                    r'(?:peer|host|target)[s:]?\s+([a-zA-Z0-9_.\s,-]+)',
                    r'(?:output|result)[s:]?\s+([a-zA-Z0-9_.\s,-]+)',
                    r'(?:format|schema)[s:]?\s+([a-zA-Z0-9_.\s,-]+)',
                ]:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        parts.append(match.group(0))
    
    return " ".join(parts) if parts else user_message

# ── Scoring ──

def score_capability(query: str, capability: dict) -> float:
    """
    Score a single capability against a query.
    Combines text similarity with keyword matching.
    """
    meta = capability.get("retrieval_metadata", {})
    
    # Build candidate text from metadata
    texts = [
        meta.get("name", ""),
        meta.get("description", ""),
    ] + meta.get("examples", []) + meta.get("supports_text", [])
    
    sim = _text_similarity(query, texts)
    
    # Keyword bonus (weight lower than semantic similarity)
    kw_score = _keyword_match(query, meta.get("supports_text", []))
    
    # Weighted score
    score = sim * 0.7 + kw_score * 0.3

    # Phase 1B canary guardrail: short operational prompts like
    # "check HMP health for peer128" are semantically exact but too terse for
    # broad Jaccard over long capability metadata. Apply a deterministic boost
    # only to the read-only HMP healthcheck contract and only for explicit HMP
    # health/status/check/ping intent.
    cap_id = meta.get("capability_id", "")
    ql = (query or "").lower()
    if cap_id == "hmp-healthcheck" and any(t in ql for t in ["health", "healthy", "status", "check", "ping", "healthcheck"]):
        has_hmp_context = "hmp" in ql or bool(_extract_peer_targets(query))
        if has_hmp_context:
            score += 0.55
        # "show peer128 HMP gateway health" is a common operator phrasing;
        # the extra gateway token otherwise dilutes the small-query score just
        # below the active canary threshold despite exact read-only intent.
        if has_hmp_context and "gateway" in ql and "health" in ql:
            score += 0.05
        # Operator shorthand "healthcheck peerX via HMP" lacks a separator
        # between health/check and can land a few thousandths below the active
        # threshold in the token-overlap scorer despite exact read-only intent.
        if has_hmp_context and "healthcheck" in ql:
            score += 0.03
    return min(score, 1.0)


def _extract_request_effect(query: str) -> str:
    q = (query or "").lower()
    # Non-operational/informational intents must not trigger active execution,
    # even when they mention an otherwise supported read-only operation.
    non_operational_patterns = [
        r"\bdo\s+not\s+(?:check|ping|run|invoke)\b",
        r"\bdon't\s+(?:check|ping|run|invoke)\b",
        r"\bwhat\s+is\b",
        r"\bexplain\b",
        r"\bdescribe\b",
        r"\bdocument(?:ation)?\b",
        r"\bgenerate\s+(?:python\s+)?code\b",
        r"\bwrite\s+(?:python\s+)?code\b",
        r"\bcompare\b",
        # Italian non-operational / informational
        r"\bspiega\b", r"\bdescrivi\b", r"\bcos'[èe]\b", r"\bche\s+cos'[èe]\b",
        r"\bcome\s+funziona\b", r"\bdimmi\s+come\b", r"\bcosa\s+[èe]\b",
    ]
    if any(re.search(p, q) for p in non_operational_patterns):
        return "non_operational"

    mutating_terms = [
        "send", "post", "write", "create", "delete", "remove", "email", "message",
        "deploy", "scp", "upload", "restart", "stop", "start", "enable", "disable",
        "modify", "update", "replace", "configure", "reboot", "shutdown", "kill",
        "terminate", "pause", "resume", "reset", "power cycle", "power-cycle",
        "patch", "upgrade",
        # Italian operator terms (peer network is Italian-speaking)
        "riavvia", "riavvialo", "riavviali", "ferma", "fermalo", "arresta",
        "disattiva", "attiva", "aggiorna", "riconfigura", "ricarica", "riavvio",
        "spegnilo", "accendilo", "termina", "uccidi", "sospendi", "riprendi",
        "cambia", "modifica", "sostituisci", "installa", "rimuovi", "elimina",
        "invia", "scrivi", "crea", "cancella",
    ]
    composite_mutating_patterns = [
        r"\band\s+(?:then\s+)?(?:restart|stop|start|enable|disable|modify|update|replace|configure|reboot|shutdown|kill|terminate|pause|resume|reset|power\s+cycle|patch|upgrade)\b",
        r"\bthen\s+(?:restart|stop|start|enable|disable|modify|update|replace|configure|reboot|shutdown|kill|terminate|pause|resume|reset|power\s+cycle|patch|upgrade)\b",
        r"\b(?:and\s+)?then\s+(?:do|perform|run|execute|continue|proceed)\b",
        r"\band\s+then\s+[^.?!]*(?:action|maintenance|step|operation|task)\b",
        r"\bif\s+(?:unhealthy|down|offline|failing|failed|not\s+ok)\b",
        r"\bif\s+[^.?!]{0,80}\b(?:fix|repair|recover|remediate|investigate|diagnose|escalate|open\s+ticket|notify|alert)\b",
        r"\b(?:check|inspect|ping|healthcheck)\b[^.?!]{0,120}\b(?:and|then)\b[^.?!]{0,120}\b(?:fix|repair|recover|remediate|investigate|diagnose|escalate|open\s+ticket|notify|alert)\b",
        # Italian composite patterns: "e se giu riavvialo", "se non healthy riavvia"
        r"\b(?:e\s+)?se\s+(?:non\s+)?(?:healthy|ok|su|attivo|attiva|funzionante|giu|giù|down|offline)\b[^.?!]{0,60}\b(?:riavvia|riavvialo|ferma|fermalo|arresta|disattiva|spegni|accendi|termina|uccidi|sospendi|riprendi|aggiorna|riconfigura)\b",
        r"\b(?:controlla|check|verifica|ping)\b[^.?!]{0,80}\b(?:e|then|poi)\b[^.?!]{0,80}\b(?:riavvia|riavvialo|ferma|fermalo|arresta|disattiva|spegni|accendi|termina|sospendi|riprendi|aggiorna|riconfigura)\b",
    ]
    read_terms = ["check", "read", "list", "inspect", "health", "status", "ping",
                  "mostra", "stato", "verifica", "controlla", "salute", "elenco", "lista"]
    if any(t in q for t in mutating_terms) or any(re.search(p, q) for p in composite_mutating_patterns):
        return "mutating"
    if any(t in q for t in read_terms):
        return "read_only"
    return ""


def _extract_peer_targets(query: str) -> set[str]:
    """Return explicitly mentioned peer labels such as peer128/peer999."""
    return {m.group(0).lower() for m in re.finditer(r"\bpeer\d+\b", query or "", re.IGNORECASE)}


def _supported_hmp_health_targets() -> set[str]:
    # Keep this local to avoid importing the dispatcher in shadow collection paths.
    return {"peer58", "peer70", "peer84", "peer105", "peer106", "peer128", "peer136", "peer138"}


def _extract_requester(hook_context: dict | None) -> dict:
    ctx = hook_context or {}
    req = ctx.get("requester") if isinstance(ctx.get("requester"), dict) else {}
    platform = str(ctx.get("platform") or "").lower()
    channel = req.get("request_channel") or ctx.get("request_channel") or ctx.get("channel") or ctx.get("source") or platform or "unknown"
    if isinstance(channel, str):
        channel = channel.lower()
    sender = ctx.get("sender_id") or ctx.get("user_id") or ""
    requester_peer = req.get("requester_peer_id") or ctx.get("requester_peer_id") or ctx.get("source_peer_id") or ctx.get("hmp_requester_peer_id") or (sender if channel == "hmp" else "")
    actor_type = req.get("actor_type") or ctx.get("actor_type") or "unknown"
    actor_id = req.get("actor_id") or ctx.get("actor_id") or sender or "unknown"
    if channel == "hmp" or requester_peer:
        channel = "hmp"
        if actor_type == "unknown": actor_type = "agent"
        if actor_id == "unknown" and requester_peer: actor_id = "hmp:%s" % requester_peer
    elif channel == "telegram":
        if actor_type == "unknown": actor_type = "human"
    return {
        "actor_type": actor_type,
        "actor_id": str(actor_id),
        "request_channel": channel if channel in {"telegram", "hmp", "cron", "local", "api", "gateway"} else "unknown",
        "requester_peer_id": str(requester_peer or ""),
        "processing_peer_id": str(req.get("processing_peer_id") or ctx.get("processing_peer_id") or ctx.get("peer_id") or ""),
    }


def _extract_traffic_type(hook_context: dict | None) -> str:
    ctx = hook_context or {}
    explicit = ctx.get("traffic_type") or ctx.get("capability_reuse_traffic_type")
    if explicit:
        return str(explicit)
    platform = str(ctx.get("platform") or "").lower()
    channel = str(ctx.get("request_channel") or platform or "").lower()
    if ctx.get("is_test") or ctx.get("acceptance_test"):
        return "acceptance_test"
    if ctx.get("is_cron") or ctx.get("schedule_id") or channel == "cron":
        return "cron"
    if channel == "hmp" or ctx.get("source_peer_id") or ctx.get("requester_peer_id"):
        return "organic_peer"
    if channel == "telegram" or ctx.get("user_id") or ctx.get("sender_id") or ctx.get("parent_task_id"):
        return "organic_user"
    return "unknown"


def _extract_validated_inputs(user_message: str, top_capability: dict) -> dict:
    meta = top_capability.get("retrieval_metadata", {}) if isinstance(top_capability, dict) else {}
    if meta.get("capability_id") != "hmp-healthcheck":
        return {}
    seen = set(); peers = []
    for m in re.finditer(r"\bpeer\d+\b", user_message or "", re.IGNORECASE):
        peer = m.group(0).lower()
        if peer not in seen:
            seen.add(peer); peers.append(peer)
    out = {"peer_list": peers} if peers else {}
    m = re.search(r"timeout(?:_seconds)?\s*[:=]?\s*(\d+)", user_message or "", re.I)
    if m:
        out["timeout_seconds"] = int(m.group(1))
    elif peers:
        out["timeout_seconds"] = 5
    return out


def _request_provenance(hook_context: dict | None) -> tuple[str | None, str, str]:
    """Extract request-scoped provenance from hook kwargs.

    The process environment fallback lives in event_store.normalize_provenance;
    this helper keeps formal request provenance scoped to the current hook call.
    """
    if not hook_context:
        return None, "", ""
    prov = hook_context.get("capability_reuse_provenance")
    source = "hook_context.capability_reuse_provenance"
    detail = hook_context.get("capability_reuse_provenance_detail", "")
    if prov is None and isinstance(hook_context.get("provenance"), dict):
        pdata = hook_context.get("provenance")
        prov = pdata.get("stream") or pdata.get("type") or pdata.get("name")
        detail = detail or pdata.get("detail", "")
        source = "hook_context.provenance"
    elif prov is None and hook_context.get("provenance") is not None:
        prov = hook_context.get("provenance")
        source = "hook_context.provenance"
    if prov is None:
        platform = str(hook_context.get("platform") or "").lower()
        if platform in {"hmp", "telegram", "api", "gateway", "local"}:
            prov = "organic_live"
            detail = detail or "platform_hook_context"
            source = "hook_context.platform"
    return prov, detail, source

def _coverage_reason(request_effect: str, capability_effect: str, query: str) -> tuple[bool, str]:
    """Fail closed for partial/composite requests."""
    if request_effect == "mutating" and capability_effect == "read_only":
        q=(query or "").lower()
        if any(t in q for t in ["restart", "if unhealthy", "fix", "recover", "remediate"]):
            return False, "partial_coverage"
        return False, "effect_mismatch"
    return True, ""


def _collect_filter_rejections(candidates: list[dict]) -> list[str]:
    """v2.4.18: collect per-candidate filter/eligibility rejection reasons.

    Returns a flat list of structured reasons so consumers can see WHY
    each candidate was filtered without guessing from booleans.
    """
    reasons: list[str] = []
    for c in candidates or []:
        cap_name = str(c.get("capability") or c.get("name") or "?")
        inelig = c.get("ineligibility_reasons") or c.get("filter_rejection_reasons")
        if isinstance(inelig, list) and inelig:
            for r in inelig:
                reasons.append(f"{cap_name}: {r}")
        elif c.get("eligible_for_intervention") is False:
            reasons.append(f"{cap_name}: ineligible_candidate_filter")
    return reasons

# ── Main retrieval ──

def retrieve(session_id: str = "",
             user_message: str = "",
             hook_context: dict | None = None,
             available_permissions: list[str] | None = None,
             available_capabilities: list[str] | None = None,
             intervention_threshold: float = DEFAULT_INTERVENTION_THRESHOLD,
             minimum_margin: float = DEFAULT_MINIMUM_MARGIN,
             retrieval_threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
             shadow_mode: bool = True
             ) -> Optional[RetrievalResult]:
    """
    Full retrieval pipeline (§4.1.2).
    
    Returns:
      - RetrievalResult with intervened=True if a high-confidence match is found
      - RetrievalResult with intervened=False if below threshold (shadow log)
      - None if below retrieval_threshold (silent)
    """
    start = time.monotonic()
    
    # 1. Build query from hook-visible inputs
    if shadow_mode:
        retrieval_threshold = min(retrieval_threshold, 0.05)
    query = build_query(session_id, user_message, hook_context)
    if not query:
        return None
    
    # 2. Get all capabilities from registry
    all_caps = reg.list_capabilities()
    if not all_caps:
        return None
    
    # 3. Score all capabilities
    scored = []
    for cap in all_caps:
        score = score_capability(query, cap)
        if score >= retrieval_threshold:
            scored.append((score, cap))
    
    if not scored:
        return None
    
    # 4. Sort by score descending
    scored.sort(key=lambda x: -x[0])
    
    # 5. Apply hard filters but keep all semantic candidates for shadow labeling
    candidate_records = []
    filtered = []
    request_effect = _extract_request_effect(query)
    for score, cap in scored:
        result = comp.check_all(
            capability=cap,
            request_effect=request_effect,
            available_permissions=available_permissions or [],
            available_capabilities=available_capabilities or [],
        )
        meta = cap.get("retrieval_metadata", {})
        inv = cap.get("invocation_contract", {})
        reasons = [] if result.compatible else [result.reason]
        unsupported_targets = []
        if meta.get("capability_id", "") == "hmp-healthcheck":
            targets = _extract_peer_targets(query)
            unsupported_targets = sorted(targets - _supported_hmp_health_targets())
            if unsupported_targets:
                result = comp.incompatible("unsupported_target")
                reasons.append("unsupported_target")
        if inv.get("trust_state") != "trusted":
            reasons.append(f"trust_state_{inv.get('trust_state', 'missing')}")
        if inv.get("required_permissions") and not available_permissions:
            reasons.append("permissions_unknown")
        if inv.get("availability_constraints") and not available_capabilities:
            reasons.append("availability_unknown")
        cap_effect = inv.get("effect_class", "unknown")
        whole_request_covered, coverage_reason = _coverage_reason(request_effect, cap_effect, query)
        if not whole_request_covered and coverage_reason not in reasons:
            reasons.append(coverage_reason)
            result = comp.incompatible(coverage_reason)
        record = {
            "capability_id": meta.get("capability_id", ""),
            "capability_version": meta.get("version", ""),
            "score": round(score, 4),
            "semantic_candidate": True,
            "eligible_for_intervention": result.compatible,
            "ineligibility_reasons": sorted(set([r for r in reasons if r])),
            "effect_class": cap_effect,
            "request_effect": request_effect or "unknown",
            "capability_effect": cap_effect,
            "whole_request_covered": whole_request_covered,
            "eligibility": "accepted" if result.compatible else "rejected",
            "eligibility_reason": coverage_reason or (result.reason if not result.compatible else ""),
            "dispatch": "pending" if result.compatible else "none",
            "trust_state": inv.get("trust_state", ""),
        }
        candidate_records.append(record)
        if result.compatible:
            filtered.append((score, cap))

    ranked = filtered if filtered else scored
    top_score, top_cap = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = top_score - second_score
    
    # 7. Check intervention conditions
    meta = top_cap.get("retrieval_metadata", {})
    inv = top_cap.get("invocation_contract", {})
    top_capability_effect = inv.get("effect_class", "unknown")
    top_whole_request_covered, top_eligibility_reason = _coverage_reason(request_effect, top_capability_effect, query)
    
    should_intervene = (
        not shadow_mode
        and bool(filtered)
        and top_score >= intervention_threshold
        and margin >= minimum_margin
        and inv.get("trust_state") == "trusted"
        and top_whole_request_covered
    )
    
    latency = (time.monotonic() - start) * 1000
    
    # 8. Emit retrieval event with full candidate evidence for retrospective labeling
    candidates_info = candidate_records[:10]
    episode_id = hook_context.get("episode_id") or hook_context.get("session_id") or session_id if hook_context else session_id
    turn_id = hook_context.get("turn_id", "") if hook_context else ""
    task_id = hook_context.get("task_id", "") if hook_context else ""
    tool_call_id = hook_context.get("tool_call_id", "") if hook_context else ""
    provenance_stream, provenance_detail, provenance_source = _request_provenance(hook_context)
    retrieval_event_id = events.emit_retrieval(
        session_id=session_id,
        episode_id=episode_id,
        turn_id=turn_id,
        task_id=task_id,
        tool_call_id=tool_call_id,
        user_message_preview=user_message,
        candidates=candidates_info,
        top_score=top_score,
        intervened=should_intervene,
        latency_ms=latency,
        shadow_mode=shadow_mode,
        provenance=provenance_stream,
        provenance_detail=provenance_detail,
        provenance_source=provenance_source,
        requester=_extract_requester(hook_context),
        validated_inputs=_extract_validated_inputs(user_message, top_cap),
        traffic_type=_extract_traffic_type(hook_context),
        second_score=second_score,
        score_margin=margin,
        intervention_threshold=intervention_threshold,
        minimum_margin=minimum_margin,
        request_effect=request_effect,
        capability_effect=top_capability_effect,
        whole_request_covered=top_whole_request_covered,
        eligibility="accepted" if should_intervene else "rejected",
        eligibility_reason="" if should_intervene else (top_eligibility_reason or "below_threshold_or_margin"),
        dispatch="pending" if should_intervene else "none",
        # v2.4.18: explicit retrieval semantics + proof the real retriever ran.
        retriever_executed=True,
        retriever_version="2.4.18",
        registry_version=reg.get_registry_version(),
        retrieval_threshold=retrieval_threshold,
        candidate_count=len(candidates_info),
        filter_rejection_reasons=_collect_filter_rejections(candidates_info) if candidates_info else [],
        # v2.4.18: explicit stage semantics — never default booleans that
        # imply a successful evaluation when no candidate was evaluated.
        retrieval_stages={
            "retrieval": {"executed": True, "candidate_count": len(candidates_info)},
            "coverage": {
                "evaluated": bool(candidates_info),
                "whole_request_covered": top_whole_request_covered if candidates_info else None,
            },
            "eligibility": {
                "evaluated": bool(candidates_info),
                "eligible": should_intervene if candidates_info else None,
            },
        },
    )
    
    if not should_intervene:
        # Shadow mode: log but don't intervene
        return RetrievalResult(
            retrieval_score=round(top_score, 4),
            score_margin=round(margin, 4),
            session_id=session_id,
            episode_id=episode_id,
            turn_id=turn_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            retrieval_event_id=retrieval_event_id or "",
            candidates=candidates_info,
            intervened=False,
            latency_ms=round(latency, 2),
        )
    
    # 9. Create result
    cap_id = meta.get("capability_id", "")
    cap_ver = meta.get("version", "")
    examples = meta.get("examples", [])
    supports = meta.get("supports_text", [])
    
    inputs_desc = ", ".join(supports[:3]) if supports else examples[0] if examples else "see schema"
    output_desc = ", ".join(inv.get("declared_effects", [])) if inv.get("declared_effects") else "structured result"
    
    episode_id = (hook_context.get("episode_id") or hook_context.get("session_id") or session_id) if hook_context else session_id
    
    return RetrievalResult(
        intervention_id=f"int_{uuid.uuid4().hex}",
        capability_id=cap_id,
        capability_version=cap_ver,
        retrieval_score=round(top_score, 4),
        score_margin=round(margin, 4),
        contract_version=cap_ver,
        inputs_description=inputs_desc,
        output_description=output_desc,
        session_id=session_id,
        episode_id=episode_id,
        turn_id=turn_id,
        task_id=task_id,
        tool_call_id=tool_call_id,
        retrieval_event_id=retrieval_event_id or "",
        intervened=True,
        candidates=candidates_info,
        latency_ms=round(latency, 2),
    )

# ── Utility ──

def search_capabilities(query: str, limit: int = 5) -> list[dict]:
    """
    Quick text search over all registered capabilities.
    Returns top-N capability entries with scores.
    """
    all_caps = reg.list_capabilities()
    scored = [(score_capability(query, cap), cap) for cap in all_caps]
    scored.sort(key=lambda x: -x[0])
    return [{"capability": c["retrieval_metadata"]["capability_id"],
             "version": c["retrieval_metadata"]["version"],
             "score": round(s, 4)}
            for s, c in scored[:limit] if s > 0]

def get_retriever_stats() -> dict:
    """Return retriever configuration."""
    return {
        "intervention_threshold": DEFAULT_INTERVENTION_THRESHOLD,
        "minimum_margin": DEFAULT_MINIMUM_MARGIN,
        "retrieval_threshold": DEFAULT_RETRIEVAL_THRESHOLD,
        "method": "text_similarity",
        "embedding_method": "none (Phase 0)",
    }