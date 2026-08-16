from __future__ import annotations
"""
protocol.py — Capability Reuse Plugin: Atomic State Machine (§3.7)
==================================================================
State machine for intervention claiming, fallback tokens, and
execution decision protocol.

Transitions:
  open
    ├── claimed_by_capability(invocation_id)
    │     ├── resolved_success
    │     ├── fallback_authorized(token_id)          # clean read-only failure
    │     │     ├── fallback_consumed(ec_tool_call_id)
    │     │     ├── fallback_expired
    │     │     └── fallback_cancelled
    │     ├── failed_unclean_read_only(invocation_id) # no token
    │     │     ├── unclean_fallback_recorded(ec_tool_call_id)
    │     │     └── unclean_fallback_expired
    │     └── failed_requires_safety(invocation_id)
    │           └── post_failure_escalation_observed(ec_tool_call_id)
    │
    ├── claimed_by_bypass(execute_code_tool_call_id)
    │     └── resolved_bypass
    │
    ├── expired
    └── cancelled

Only ONE initial transition out of 'open' may succeed (atomic compare-and-set).
"""
import copy, hashlib, importlib, json, os, time, uuid, threading
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

VERSION = "2.6.0"

# ── Constants ──
DEFAULT_FALLBACK_TTL_SECONDS = 300  # 5 minutes
DEFAULT_UNCLEAN_TTL_SECONDS = 600   # 10 minutes
DEFAULT_TOMBSTONE_TTL_SECONDS = 300 # turn decision tombstones; cleared at next pre_llm turn too
DEFAULT_BLOCKED_CALL_TTL_SECONDS = 300
DEFAULT_RETRIEVAL_ENVELOPE_TTL_SECONDS = 300

# ── Verdict (for pre_tool_call hook) ──

@dataclass
class Verdict:
    """pre_tool_call return value. allowed=True → pass through."""
    allowed: bool
    message: str = ""

# ── State definitions ──

INTERVENTION_INITIAL = "open"
INTERVENTION_TERMINAL = {
    "resolved_success", "resolved_bypass",
    "fallback_consumed", "fallback_expired", "fallback_cancelled",
    "unclean_fallback_recorded", "unclean_fallback_expired",
    "post_failure_escalation_observed",
    "expired", "cancelled",
}

ALLOWED_TRANSITIONS = {
    "open": {"claimed_by_capability", "claimed_by_bypass", "expired", "cancelled"},
    "claimed_by_capability": {
        "resolved_success", "fallback_authorized",
        "failed_unclean_read_only", "failed_requires_safety",
    },
    "fallback_authorized": {"fallback_consumed", "fallback_expired", "fallback_cancelled"},
    "failed_unclean_read_only": {"unclean_fallback_recorded", "unclean_fallback_expired"},
    "failed_requires_safety": {"post_failure_escalation_observed"},
    "claimed_by_bypass": {"resolved_bypass"},
}

# ── Intervention Store (thread-safe, in-memory for single-process canary) ──

class InterventionStore:
    """
    Thread-safe intervention store with atomic compare-and-set.
    For single-process canary (in-memory dict).
    Multi-process deployments require a shared transactional store (TODO).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._interventions: dict[str, dict] = {}       # intervention_id → state
        self._tokens: dict[str, dict] = {}              # token_id → state
        self._unclean: dict[str, dict] = {}             # invocation_id → recorded
        self._turn_decisions: dict[tuple[str, str, str], dict] = {}  # turn-scope exactly-once tombstones
        self._blocked_calls: dict[str, dict] = {}         # tool_call_id → protocol block metadata

    # ── Intervention claiming ──

    def create_intervention(self, intervention_id: str, episode_id: str,
                            capability_id: str, capability_version: str,
                            retrieval_score: float = 0.0, score_margin: float = 0.0,
                            contract_version: str = "", prompt_template_version: str = "",
                            session_id: str = "", turn_id: str = "",
                            retrieval_event_id: str = "") -> dict:
        """Create a new intervention in 'open' state. No-op if already exists."""
        with self._lock:
            if intervention_id not in self._interventions:
                self._interventions[intervention_id] = {
                    "state": INTERVENTION_INITIAL,
                    "session_id": session_id,
                    "episode_id": episode_id,
                    "turn_id": turn_id,
                    "retrieval_event_id": retrieval_event_id,
                    "capability_id": capability_id,
                    "capability_version": capability_version,
                    "retrieval_score": retrieval_score,
                    "score_margin": score_margin,
                    "contract_version": contract_version,
                    "prompt_template_version": prompt_template_version,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            return self._interventions[intervention_id]

    def _turn_key_for_inv(self, inv: dict) -> tuple[str, str, str]:
        return (inv.get("session_id", ""), inv.get("episode_id", "") or inv.get("session_id", ""), inv.get("turn_id", ""))

    def mark_turn_decision_consumed(self, intervention_id: str, tool_call_id: str = "", reason: str = "") -> None:
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return
            key = self._turn_key_for_inv(inv)
            if key != ("", "", ""):
                self._turn_decisions[key] = {
                    "intervention_id": intervention_id,
                    "state": inv.get("state", ""),
                    "tool_call_id": tool_call_id,
                    "reason": reason,
                    "consumed_at": _now(),
                }

    def latest_turn_decision(self, session_id: str = "", episode_id: str = "", turn_id: str = "") -> Optional[dict]:
        scope_episode = episode_id or session_id or ""
        keys = [
            (session_id or "", scope_episode, turn_id or ""),
            (session_id or "", scope_episode, ""),
            (session_id or "", session_id or "", turn_id or ""),
            (session_id or "", session_id or "", ""),
            ("", scope_episode, turn_id or ""),
            ("", scope_episode, ""),
        ]
        with self._lock:
            for key in keys:
                if key in self._turn_decisions:
                    return copy.deepcopy(self._turn_decisions[key])
        return None

    def clear_turn_decisions_for_scope(self, session_id: str = "", episode_id: str = "", turn_id: str = "") -> int:
        """Clear previous-turn tombstones at the start/end of a visible turn scope."""
        scope_episode = episode_id or session_id or ""
        keys = {
            (session_id or "", scope_episode, turn_id or ""),
            (session_id or "", scope_episode, ""),
            (session_id or "", session_id or "", turn_id or ""),
            (session_id or "", session_id or "", ""),
            ("", scope_episode, turn_id or ""),
            ("", scope_episode, ""),
        }
        removed = 0
        with self._lock:
            for key in keys:
                if key in self._turn_decisions:
                    del self._turn_decisions[key]
                    removed += 1
        return removed

    def remember_blocked_call(self, tool_call_id: str, origin: str, reason: str, intervention_id: str = "") -> None:
        if not tool_call_id:
            return
        with self._lock:
            self._blocked_calls[tool_call_id] = {"origin": origin, "reason": reason, "intervention_id": intervention_id, "recorded_at": _now()}

    def pop_blocked_call(self, tool_call_id: str) -> Optional[dict]:
        if not tool_call_id:
            return None
        with self._lock:
            data = self._blocked_calls.pop(tool_call_id, None)
            return copy.deepcopy(data) if data is not None else None

    def claim_intervention(self, intervention_id: str, claim_type: str,
                           caller_id: str) -> bool:
        """
        Atomic compare-and-set: claim an open intervention.
        claim_type: 'capability' or 'bypass'
        caller_id: invocation_id or tool_call_id
        Returns True if claim succeeded, False if already claimed.
        """
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return False
            if inv["state"] != INTERVENTION_INITIAL:
                return False  # already claimed

            now = _now()
            if claim_type == "capability":
                inv["state"] = "claimed_by_capability"
                inv["invocation_id"] = caller_id
            elif claim_type == "bypass":
                inv["state"] = "claimed_by_bypass"
                inv["tool_call_id"] = caller_id
            else:
                return False

            inv["claimed_at"] = now
            inv["updated_at"] = now
            return True

    def get_intervention(self, intervention_id: str) -> Optional[dict]:
        with self._lock:
            inv = self._interventions.get(intervention_id)
            return copy.deepcopy(inv) if inv is not None else None

    def transition(self, intervention_id: str, target_state: str,
                   **extra) -> bool:
        """
        Transition an intervention to target_state.
        Returns True if transition was valid, False otherwise.
        """
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return False
            current_state = inv["state"]
            if current_state in INTERVENTION_TERMINAL:
                return False  # terminal state, no more transitions
            if target_state not in ALLOWED_TRANSITIONS.get(current_state, set()):
                return False

            now = _now()
            inv["state"] = target_state
            inv["updated_at"] = now
            for k, v in extra.items():
                inv[k] = v
            if target_state in INTERVENTION_TERMINAL:
                key = self._turn_key_for_inv(inv)
                if key != ("", "", ""):
                    self._turn_decisions[key] = {
                        "intervention_id": intervention_id,
                        "state": target_state,
                        "tool_call_id": extra.get("tool_call_id") or extra.get("execute_code_tool_call_id", ""),
                        "reason": extra.get("reason", "transition"),
                        "consumed_at": now,
                    }
            return True

    # ── Fallback token management ──

    def issue_fallback_token(self, intervention_id: str, invocation_id: str,
                             failure_code: str, ttl: int = DEFAULT_FALLBACK_TTL_SECONDS) -> Optional[str]:
        """
        Issue a single-use fallback token for a clean read-only failure.
        Returns token_id, or None if issuance is not allowed by state.
        """
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return None
            if inv["state"] != "claimed_by_capability":
                return None
            if inv.get("invocation_id") and inv.get("invocation_id") != invocation_id:
                return None
            if inv.get("fallback_authorization_id"):
                return None

            token_id = f"fbt_{uuid.uuid4().hex[:16]}"
            now = _now()
            expiry = now + ttl if isinstance(now, (int, float)) else time.time() + ttl

            self._tokens[token_id] = {
                "state": "issued",
                "intervention_id": intervention_id,
                "invocation_id": invocation_id,
                "failure_code": failure_code,
                "issued_at": now,
                "expires_at": expiry,
            }

            inv["state"] = "fallback_authorized"
            inv["fallback_authorization_id"] = token_id
            inv["fallback_failure_code"] = failure_code
            inv["updated_at"] = now
            return token_id

    def consume_fallback_token(self, token_id: str, tool_call_id: str,
                               intervention_id: str = "") -> bool:
        """
        Atomically consume a fallback token. Returns True if consumed.
        When intervention_id is supplied, the token must belong to that exact
        currently-blocking intervention.
        """
        with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                return False
            if intervention_id and token.get("intervention_id") != intervention_id:
                return False
            if token["state"] != "issued":
                return False

            # Check TTL
            now = time.time()
            if now > token["expires_at"]:
                token["state"] = "expired"
                # Update intervention
                inv = self._interventions.get(token["intervention_id"])
                if inv:
                    inv["state"] = "fallback_expired"
                    inv["updated_at"] = now
                return False

            token["state"] = "consumed"
            token["consumed_by"] = tool_call_id
            token["consumed_at"] = now

            # Update intervention
            inv = self._interventions.get(token["intervention_id"])
            if inv:
                inv["state"] = "fallback_consumed"
                inv["execute_code_tool_call_id"] = tool_call_id
                inv["updated_at"] = now
                key = self._turn_key_for_inv(inv)
                if key != ("", "", ""):
                    self._turn_decisions[key] = {"intervention_id": token["intervention_id"], "state": "fallback_consumed", "tool_call_id": tool_call_id, "reason": "harness_failure", "consumed_at": now}
            return True

    def expire_fallback_token(self, token_id: str) -> bool:
        """Explicitly expire a token (e.g. on session end)."""
        with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                return False
            if token["state"] != "issued":
                return False
            token["state"] = "expired"
            inv = self._interventions.get(token["intervention_id"])
            if inv:
                inv["state"] = "fallback_expired"
                inv["updated_at"] = time.time()
            return True

    # ── Unclean continuation (read-only only) ──

    def record_unclean_continuation(self, intervention_id: str,
                                    invocation_id: str, failure_code: str,
                                    tool_call_id: str) -> bool:
        """
        Record ONE unclean continuation for a read-only failure.
        Returns True if recorded, False if already recorded or invalid state.
        """
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return False
            if inv["state"] != "failed_unclean_read_only":
                return False

            # Check we haven't already recorded one
            if self._unclean.get(invocation_id):
                return False

            now = _now()
            self._unclean[invocation_id] = {
                "state": "recorded",
                "intervention_id": intervention_id,
                "invocation_id": invocation_id,
                "failure_code": failure_code,
                "tool_call_id": tool_call_id,
                "recorded_at": now,
            }

            inv["state"] = "unclean_fallback_recorded"
            inv["execute_code_tool_call_id"] = tool_call_id
            inv["unclean_failure_code"] = failure_code
            inv["updated_at"] = now
            key = self._turn_key_for_inv(inv)
            if key != ("", "", ""):
                self._turn_decisions[key] = {"intervention_id": intervention_id, "state": "unclean_fallback_recorded", "tool_call_id": tool_call_id, "reason": "harness_failure_unclean", "consumed_at": now}
            return True

    def check_unclean_continuation_allowed(self, intervention_id: str,
                                           invocation_id: str) -> bool:
        """
        Check if an unclean continuation is allowed for a given invocation.
        Returns True if: state is failed_unclean_read_only AND
        no continuation has been recorded yet for this invocation.
        """
        with self._lock:
            inv = self._interventions.get(intervention_id)
            if not inv:
                return False
            if inv["state"] != "failed_unclean_read_only":
                return False
            if self._unclean.get(invocation_id):
                return False
            return True

    # ── Garbage collection ──

    def cleanup_expired(self, max_age_seconds: int = 3600):
        """Remove expired terminal interventions and bounded auxiliary state."""
        now = time.time()
        tombstone_age = min(max_age_seconds, DEFAULT_TOMBSTONE_TTL_SECONDS)
        blocked_age = min(max_age_seconds, DEFAULT_BLOCKED_CALL_TTL_SECONDS)
        unclean_age = min(max_age_seconds, DEFAULT_UNCLEAN_TTL_SECONDS)
        with self._lock:
            to_remove = []
            for iid, inv in self._interventions.items():
                age = now - inv.get("created_at", 0)
                if inv["state"] in INTERVENTION_TERMINAL and age > max_age_seconds:
                    to_remove.append(iid)
            for iid in to_remove:
                del self._interventions[iid]

            expired_tokens = []
            for token_id, token in self._tokens.items():
                if token.get("state") != "issued" or now > token.get("expires_at", 0) or now - token.get("issued_at", now) > DEFAULT_FALLBACK_TTL_SECONDS:
                    expired_tokens.append(token_id)
            for token_id in expired_tokens:
                del self._tokens[token_id]

            stale_unclean = []
            for invocation_id, record in self._unclean.items():
                if now - record.get("recorded_at", now) > unclean_age:
                    stale_unclean.append(invocation_id)
            for invocation_id in stale_unclean:
                del self._unclean[invocation_id]

            stale_tombstones = []
            for key, tombstone in self._turn_decisions.items():
                if now - tombstone.get("consumed_at", now) > tombstone_age:
                    stale_tombstones.append(key)
            for key in stale_tombstones:
                del self._turn_decisions[key]

            stale_blocks = []
            for tool_call_id, record in self._blocked_calls.items():
                if now - record.get("recorded_at", now) > blocked_age:
                    stale_blocks.append(tool_call_id)
            for tool_call_id in stale_blocks:
                del self._blocked_calls[tool_call_id]

# ── Global store ──
_store = InterventionStore()

# ── Public API ──

def invoke_schema() -> dict:
    """Return Hermes tool schema for invoke_capability."""
    return {
        "name": "invoke_capability",
        "description": (
            "Invoke the exact capability version proposed by the "
            "capability-reuse controller."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "intervention_id", "capability_id",
                "capability_version", "inputs",
            ],
            "properties": {
                "intervention_id": {"type": "string", "minLength": 1},
                "capability_id": {"type": "string", "minLength": 1},
                "capability_version": {
                    "type": "string",
                    "pattern": r"^\d+\.\d+\.\d+$",
                },
                "inputs": {"type": "object"},
            },
        },
    }

def _mode() -> str:
    return os.environ.get("CAPABILITY_REUSE_MODE", "shadow").strip().lower() or "shadow"


def _active_allowlist() -> set[str]:
    raw = os.environ.get("CAPABILITY_REUSE_ACTIVE_CAPABILITIES", "hmp-healthcheck")
    return {x.strip() for x in raw.split(",") if x.strip()}

def _csv_env(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]

_latest_retrieval_by_scope: dict[tuple[str, str, str], dict] = {}

def _scope(session_id: str = "", episode_id: str = "", turn_id: str = "") -> tuple[str, str, str]:
    return (session_id or "", episode_id or session_id or "", turn_id or "")

def _remember_retrieval(result) -> None:
    if not result:
        return
    data = result.__dict__ if hasattr(result, "__dict__") else dict(result)
    envelope = {
        "retrieval_event_id": data.get("retrieval_event_id", ""),
        "session_id": data.get("session_id", ""),
        "episode_id": data.get("episode_id", ""),
        "turn_id": data.get("turn_id", ""),
        # v2.5.0: campi per la bubble observe (canale 🔍) — capability top,
        # score e latenza del retrieval, come da RetrievalResult.
        "capability_id": data.get("capability_id", ""),
        "capability_version": data.get("capability_version", ""),
        "retrieval_score": float(data.get("retrieval_score") or 0.0),
        "latency_ms": float(data.get("latency_ms") or 0.0),
        "intervened": bool(data.get("intervened", False)),
        # v2.5.0 fix (e2e): candidates conservati per la bubble observe anche
        # in shadow (capability top e score sono in candidates[0]).
        "candidates": list(data.get("candidates") or []),
        # consume-on-observe: settato SOLO quando l'hook ha davvero ritornato
        # action=observe per questo envelope (single-fire bubble, v2.5.0).
        "observe_shown": False,
        "remembered_at": _now(),
    }
    session_id = data.get("session_id", "")
    episode_id = data.get("episode_id", "")
    turn_id = data.get("turn_id", "")
    for key in {
        _scope(session_id, episode_id, turn_id),
        _scope(session_id, episode_id, ""),
        _scope(session_id, "", turn_id),
        _scope(session_id, "", ""),
        _scope(episode_id, "", turn_id),
        _scope(episode_id, "", ""),
    }:
        if key != _scope("", "", ""):
            _latest_retrieval_by_scope[key] = envelope

def _latest_retrieval_envelope(session_id: str = "", episode_id: str = "", turn_id: str = "") -> dict:
    keys = [
        _scope(session_id, episode_id, turn_id),
        _scope(session_id, episode_id, ""),
        _scope(session_id, "", turn_id),
        _scope(session_id, "", ""),
    ]
    for key in keys:
        if key in _latest_retrieval_by_scope:
            return dict(_latest_retrieval_by_scope[key])
    return {}


def consume_retrieval_observe(session_id: str = "", episode_id: str = "", turn_id: str = "") -> dict | None:
    """v2.5.0 — capability-reuse produce una bubble observe 🔍 (canale
    tool.considered) quando c'e' un retrieval ATTIVO nello STESSO turno.

    Vincoli del review gate:
      - same session + same turn: match FORTE su (session_id, turn_id),
        nessun fallback a scope piu' largo (niente bubble stale)
      - single observe per envelope: consume-on-observe — `observe_shown`
        viene settato SOLO qui, quando l'hook ritorna davvero action=observe
      - fail-open: se mancano capability_id/score valido o il feedback non e'
        costruibile -> ritorna None SENZA consumare l'envelope
      - observe non blocca/approva: ritorna solo feedback; la decisione
        block/approve del gate resta invariata
    """
    if not session_id or not turn_id:
        return None
    key = _scope(session_id, episode_id, turn_id)
    envelope = _latest_retrieval_by_scope.get(key)
    # v2.5.0 hardening (close-up review peer70): se la key esatta non matcha
    # (es. episode_id mancante nei kwargs del pre_tool_call mentre l'envelope
    # è stato memorizzato con episode reale), fallback alla key con episode
    # vuoto — resta comunque match FORTE su session+turn (zero bubble stale).
    if envelope is None and episode_id:
        envelope = _latest_retrieval_by_scope.get(_scope(session_id, "", turn_id))
    if not envelope:
        return None
    if envelope.get("observe_shown"):
        return None
    # v2.5.0 fix (e2e): in SHADOW mode il result ha capability_id vuoto ma i
    # candidates sono popolati (candidates[0] = capability top con score).
    # La bubble observe è un feedback diagnostico — deve funzionare in shadow
    # E in active. Precedenza: capability_id/retrieval_score del result
    # (active), fallback a candidates[0] (shadow).
    capability = envelope.get("capability_id", "")
    score = envelope.get("retrieval_score", 0.0)
    if (not capability or not isinstance(score, (int, float)) or score <= 0.0):
        candidates = envelope.get("candidates") or []
        if candidates:
            top = candidates[0]
            capability = top.get("capability_id", "")
            try:
                score = float(top.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
    if not capability or not isinstance(score, (int, float)) or score <= 0.0:
        # fail-open: feedback non costruibile -> nessun observe, envelope
        # NON consumato (un futuro retrieval valido sullo stesso scope puo'
        # ancora emettere la bubble)
        return None
    envelope["observe_shown"] = True
    return {
        "kind": "retrieval",
        "text": f"{capability} · score {score:.2f}",
        "duration_ms": float(envelope.get("latency_ms") or 0.0),
    }


def _cleanup_latest_retrievals(max_age_seconds: int = DEFAULT_RETRIEVAL_ENVELOPE_TTL_SECONDS) -> int:
    now = _now()
    stale = [
        key for key, envelope in _latest_retrieval_by_scope.items()
        if now - envelope.get("remembered_at", now) > max_age_seconds
    ]
    for key in stale:
        del _latest_retrieval_by_scope[key]
    return len(stale)


def cleanup_expired(max_age_seconds: int = 3600) -> None:
    """Hook-callable maintenance for interventions, tombstones, blocks, and retrieval envelopes."""
    _store.cleanup_expired(max_age_seconds=max_age_seconds)
    _cleanup_latest_retrievals(min(max_age_seconds, DEFAULT_RETRIEVAL_ENVELOPE_TTL_SECONDS))


def _maintenance_cleanup() -> None:
    try:
        cleanup_expired()
    except Exception:
        pass

def _latest_open_intervention(session_id: str = "", episode_id: str = "", turn_id: str = "") -> Optional[dict]:
    # Single-process Phase 1B canary: most recent non-terminal intervention scoped by the hook-visible envelope.
    with _store._lock:
        items = list(_store._interventions.items())
    for intervention_id, inv in reversed(items):
        if inv.get("state") in INTERVENTION_TERMINAL:
            continue
        if episode_id and inv.get("episode_id") not in ("", episode_id):
            continue
        if session_id and inv.get("session_id") and inv.get("session_id") != session_id and inv.get("episode_id") != session_id and inv.get("episode_id") != episode_id:
            continue
        if turn_id and inv.get("turn_id") and inv.get("turn_id") != turn_id:
            continue
        snap = copy.deepcopy(inv)
        snap["intervention_id"] = intervention_id
        return snap
    return None

def _normalise_tool_result(result):
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return {"raw": result}
    return result if isinstance(result, dict) else {"raw": result}

def _import_sibling(name: str):
    """Import a sibling module whether protocol is loaded as a package or top-level file."""
    if __package__:
        return importlib.import_module(__package__ + "." + name)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, name + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

def retrieve(session_id="", user_message="", hook_context=None) -> Optional[dict]:
    """Pre-LLM hook entry. Shadow mode observes retrieval but never injects."""
    _maintenance_cleanup()
    hook_context = hook_context or {}
    _store.clear_turn_decisions_for_scope(
        session_id=session_id or hook_context.get("session_id", ""),
        episode_id=hook_context.get("episode_id", ""),
        turn_id=hook_context.get("turn_id", ""),
    )
    retriever = _import_sibling("retriever")
    active = _mode() == "active"
    available_permissions = hook_context.get("available_permissions")
    available_capabilities = hook_context.get("available_capabilities")
    if active:
        # Active mode must not invent permissions/availability. They must come
        # from hook data or an explicit trusted runtime configuration source.
        if available_permissions is None:
            available_permissions = _csv_env("CAPABILITY_REUSE_PERMISSIONS")
        if available_capabilities is None:
            available_capabilities = _csv_env("CAPABILITY_REUSE_AVAILABLE_CAPABILITIES")
    threshold = float(os.environ.get("CAPABILITY_REUSE_INTERVENTION_THRESHOLD", os.environ.get("CAPABILITY_REUSE_THRESHOLD", getattr(retriever, "DEFAULT_INTERVENTION_THRESHOLD", 0.75))))
    margin = float(os.environ.get("CAPABILITY_REUSE_MINIMUM_MARGIN", os.environ.get("CAPABILITY_REUSE_MIN_MARGIN", getattr(retriever, "DEFAULT_MINIMUM_MARGIN", 0.15))))
    result = retriever.retrieve(
        session_id=session_id,
        user_message=user_message,
        hook_context=hook_context,
        available_permissions=available_permissions,
        available_capabilities=available_capabilities,
        intervention_threshold=threshold,
        minimum_margin=margin,
        shadow_mode=not active,
    )
    _remember_retrieval(result)
    if not active:
        return None
    if result is None or not getattr(result, "intervened", False):
        return None
    decision = result.__dict__ if hasattr(result, "__dict__") else dict(result)
    if decision.get("capability_id") not in _active_allowlist():
        return None
    return decision

def persist_intervention(decision: dict):
    """Store a retrieval decision as an intervention."""
    if not decision:
        return
    events = _import_sibling("event_store")
    intervention_id = decision.get("intervention_id", f"int_{uuid.uuid4().hex[:16]}")
    _store.create_intervention(
        intervention_id=intervention_id,
        episode_id=decision.get("episode_id", ""),
        capability_id=decision.get("capability_id", ""),
        capability_version=decision.get("capability_version", ""),
        retrieval_score=decision.get("retrieval_score", 0.0),
        score_margin=decision.get("score_margin", 0.0),
        contract_version=decision.get("contract_version", ""),
        prompt_template_version=decision.get("prompt_template_version", ""),
        session_id=decision.get("session_id", ""),
        turn_id=decision.get("turn_id", ""),
        retrieval_event_id=decision.get("retrieval_event_id", ""),
    )
    events.emit_intervention(
        intervention_id=intervention_id,
        episode_id=decision.get("episode_id", ""),
        capability_id=decision.get("capability_id", ""),
        capability_version=decision.get("capability_version", ""),
        retrieval_score=decision.get("retrieval_score", 0.0),
        score_margin=decision.get("score_margin", 0.0),
        integration_mode=_mode(),
        injection_position=0,
        session_id=decision.get("session_id", ""),
        turn_id=decision.get("turn_id", ""),
        retrieval_event_id=decision.get("retrieval_event_id", ""),
    )
    events.emit_state_transition(intervention_id, "none", "open", reason="active_intervention_created")

def render_injection(decision: dict) -> str:
    """Render the prompt injection text for an intervention."""
    if not decision:
        return ""
    iid = decision.get("intervention_id", "")
    cap_id = decision.get("capability_id", "?")
    cap_ver = decision.get("capability_version", "?")
    inputs_desc = decision.get("inputs_description", "see contract")
    output_desc = decision.get("output_description", "structured result")

    return (
        f"A registered capability matches this operation:\n\n"
        f"  Intervention ID: {iid}\n"
        f"  Capability: {cap_id}@{cap_ver}\n"
        f"  Inputs: {inputs_desc}\n"
        f"  Output: {output_desc}\n\n"
        f"Call invoke_capability with exactly:\n"
        f"  intervention_id={iid}\n"
        f"  capability_id={cap_id}\n"
        f"  capability_version={cap_ver}\n"
        f"  inputs=<object matching the capability input schema>\n\n"
        f"If the capability is incompatible, execute_code is allowed only with a\n"
        f"structured capability_reuse_bypass containing intervention_id,\n"
        f"capability_id, capability_version, reason_code, and the fields required\n"
        f"for that reason. Allowed reason_code values: missing_feature,\n"
        f"taxonomy_gap, incompatible_input, incompatible_output,\n"
        f"environment_constraint, harness_failure, harness_failure_unclean."
    )


def _validate_bypass(bypass: dict, intervention: dict) -> tuple[bool, str]:
    if not isinstance(bypass, dict):
        return False, "missing_bypass"
    iid = intervention.get("intervention_id", "")
    cap_id = intervention.get("capability_id", "")
    cap_ver = intervention.get("capability_version", "")
    if bypass.get("intervention_id") != iid:
        return False, "intervention_id_mismatch"
    if bypass.get("capability_id") != cap_id or bypass.get("capability_version") != cap_ver:
        return False, "capability_mismatch"
    reason = bypass.get("reason_code", "")
    allowed = {
        "missing_feature", "taxonomy_gap", "incompatible_input",
        "incompatible_output", "environment_constraint",
        "harness_failure", "harness_failure_unclean",
        # Back-compat aliases accepted but normalized only in audit detail.
        "unsupported_feature", "schema_mismatch",
    }
    if reason not in allowed:
        return False, "invalid_reason_code"
    if reason in ("missing_feature", "taxonomy_gap", "unsupported_feature") and not (bypass.get("proposed_feature_slug") or bypass.get("feature_id")):
        return False, "missing_proposed_feature_slug"
    if reason in ("incompatible_input", "incompatible_output", "schema_mismatch") and not (bypass.get("schema_path") or bypass.get("field_path")):
        return False, "missing_schema_path"
    if reason == "environment_constraint" and not bypass.get("constraint_id"):
        return False, "missing_constraint_id"
    if reason == "harness_failure":
        if intervention.get("state") != "fallback_authorized":
            return False, "no_clean_failure"
        if bypass.get("prior_invocation_id") != intervention.get("invocation_id"):
            return False, "prior_invocation_mismatch"
        if bypass.get("failure_code") != intervention.get("fallback_failure_code"):
            return False, "failure_code_mismatch"
        if bypass.get("fallback_authorization_id") != intervention.get("fallback_authorization_id"):
            return False, "fallback_token_mismatch"
    if reason == "harness_failure_unclean":
        if intervention.get("state") != "failed_unclean_read_only":
            return False, "no_unclean_failure"
        if bypass.get("prior_invocation_id") != intervention.get("invocation_id"):
            return False, "prior_invocation_mismatch"
        if bypass.get("failure_code") != intervention.get("failure_code"):
            return False, "failure_code_mismatch"
    return True, ""


def authorize_execute_code(args=None, task_id="", hook_context=None) -> Verdict:
    """Deterministically block raw execute_code while an active intervention is open."""
    _maintenance_cleanup()
    events = _import_sibling("event_store")
    args = args or {}
    hook_context = hook_context or {}
    code = args.get("code", "") if isinstance(args, dict) else ""
    code_hash = _stable_hash(code)
    session_id = hook_context.get("session_id", "")
    episode_id = hook_context.get("episode_id", "")
    turn_id = hook_context.get("turn_id", "")
    tool_call_id = hook_context.get("tool_call_id", task_id or f"ec_{uuid.uuid4().hex[:8]}")
    retrieval = _latest_retrieval_envelope(session_id, episode_id, turn_id)
    events.emit_execute_code_start(
        code_preview=code,
        code_hash=code_hash,
        session_id=session_id,
        episode_id=episode_id,
        turn_id=turn_id,
        task_id=task_id,
        tool_call_id=tool_call_id,
        retrieval_event_id=retrieval.get("retrieval_event_id", ""),
    )
    if _mode() != "active":
        return Verdict(allowed=True)
    intervention = _latest_open_intervention(session_id=session_id, episode_id=episode_id, turn_id=turn_id)
    if not intervention:
        tombstone = _store.latest_turn_decision(session_id=session_id, episode_id=episode_id, turn_id=turn_id)
        if tombstone:
            iid = tombstone.get("intervention_id", "")
            _store.remember_blocked_call(tool_call_id, events.BLOCK_ORIGIN_PROTOCOL, "turn_decision_already_consumed", iid)
            return Verdict(False, f"capability-reuse intervention {iid} decision already consumed for this turn; second decision-capable execute_code is rejected")
        return Verdict(allowed=True)
    iid = intervention["intervention_id"]
    bypass = args.get("capability_reuse_bypass") if isinstance(args, dict) else None
    ok, reason = _validate_bypass(bypass, intervention)
    if ok:
        if intervention.get("state") == "failed_unclean_read_only":
            if _store.record_unclean_continuation(iid, intervention.get("invocation_id", ""), intervention.get("failure_code", ""), tool_call_id):
                events.emit_bypass(
                    intervention_id=iid,
                    capability_id=intervention.get("capability_id", ""),
                    capability_version=intervention.get("capability_version", ""),
                    reason_code=bypass.get("reason_code", ""),
                    feature_id=bypass.get("feature_id", ""),
                    detail=bypass.get("detail", ""),
                    prior_invocation_id=bypass.get("prior_invocation_id", ""),
                    failure_code=bypass.get("failure_code", ""),
                )
                events.emit_state_transition(iid, "failed_unclean_read_only", "unclean_fallback_recorded", reason="harness_failure_unclean_bypass")
                return Verdict(allowed=True)
        elif intervention.get("state") == "fallback_authorized" and bypass.get("reason_code") == "harness_failure":
            token = bypass.get("fallback_authorization_id", "")
            if _store.consume_fallback_token(token, tool_call_id, intervention_id=iid):
                events.emit_fallback_authorization(iid, token, intervention.get("invocation_id", ""), intervention.get("fallback_failure_code", ""), DEFAULT_FALLBACK_TTL_SECONDS, action="consumed")
                events.emit_bypass(
                    intervention_id=iid,
                    capability_id=intervention.get("capability_id", ""),
                    capability_version=intervention.get("capability_version", ""),
                    reason_code=bypass.get("reason_code", ""),
                    detail=bypass.get("detail", ""),
                    prior_invocation_id=bypass.get("prior_invocation_id", ""),
                    failure_code=bypass.get("failure_code", ""),
                    fallback_authorization_id=token,
                )
                events.emit_state_transition(iid, "fallback_authorized", "fallback_consumed", reason="harness_failure_bypass")
                return Verdict(allowed=True)
            reason = "fallback_token_not_consumable"
        elif _store.claim_intervention(iid, "bypass", tool_call_id):
            events.emit_bypass(
                intervention_id=iid,
                capability_id=intervention.get("capability_id", ""),
                capability_version=intervention.get("capability_version", ""),
                reason_code=bypass.get("reason_code", ""),
                feature_id=bypass.get("proposed_feature_slug", "") or bypass.get("feature_id", ""),
                detail=bypass.get("detail", ""),
            )
            _store.transition(iid, "resolved_bypass")
            events.emit_state_transition(iid, "claimed_by_bypass", "resolved_bypass", reason="validated_bypass")
            return Verdict(allowed=True)
    suffix = f"; bypass rejected: {reason}" if bypass else ""
    _store.remember_blocked_call(tool_call_id, events.BLOCK_ORIGIN_PROTOCOL, reason or "missing_or_invalid_bypass", iid)
    return Verdict(False, f"capability-reuse active intervention {iid} is open for {intervention.get('capability_id')}@{intervention.get('capability_version')}; use invoke_capability or provide a valid capability_reuse_bypass{suffix}")

def invoke_capability(params=None, hook_context=None) -> dict:
    """Handle invoke_capability tool call for the Phase 1B read-only canary set."""
    start = time.monotonic()
    if _mode() != "active":
        return {"success": False, "error": "shadow_mode_not_executable", "message": "capability-reuse is in shadow mode; no capability was dispatched"}
    if not isinstance(params, dict):
        return {"success": False, "error": "no_params"}
    comp = _import_sibling("compatibility")
    dispatcher = _import_sibling("dispatcher")
    events = _import_sibling("event_store")
    reg = _import_sibling("registry")
    iid = params.get("intervention_id", "")
    cap_id = params.get("capability_id", "")
    cap_ver = params.get("capability_version", "")
    inputs = params.get("inputs", {})
    invocation_id = f"inv_{uuid.uuid4().hex[:16]}"
    plan = {}
    preview_target_peer_id = ""
    dispatcher_target_peer_id = ""
    result_target_peer_id = ""
    if cap_id not in _active_allowlist():
        return {"success": False, "error": "capability_not_active", "capability_id": cap_id}
    intervention = _store.get_intervention(iid)
    if not intervention:
        return {"success": False, "error": "unknown_intervention", "intervention_id": iid}
    if intervention.get("capability_id") != cap_id or intervention.get("capability_version") != cap_ver:
        return {"success": False, "error": "intervention_capability_mismatch"}
    contract = reg.get_contract(cap_id, cap_ver) or {}
    if contract.get("trust_state") != "trusted":
        events.emit_failure_escalation(iid, invocation_id, contract.get("effect_class", "unknown"), "capability_not_trusted")
        return {"success": False, "error": "capability_not_trusted", "capability_id": cap_id, "trust_state": contract.get("trust_state", "missing")}
    if contract.get("effect_class") != "read_only":
        events.emit_failure_escalation(iid, invocation_id, contract.get("effect_class", "unknown"), "mutating_active_dispatch_blocked")
        return {"success": False, "error": "effect_class_not_active_safe"}
    try:
        plan = dispatcher.build_execution_plan(cap_id, cap_ver, inputs)
        preview_target_peer_id = plan.get("target_peer_id") or ""
        dispatcher_target_peer_id = preview_target_peer_id
    except Exception:
        plan = {}
    check = comp.strict_validate_against_schema(inputs, contract.get("input_schema", {}))
    if not check.compatible:
        events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "failed", "failed", "invalid_input", "none", None, (time.monotonic()-start)*1000, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
        return {"success": False, "error": "invalid_input", "message": check.reason}
    if not _store.claim_intervention(iid, "capability", invocation_id):
        return {"success": False, "error": "intervention_already_claimed", "intervention_id": iid}
    events.emit_state_transition(iid, "open", "claimed_by_capability", reason="invoke_capability")
    result = dispatcher.dispatch(cap_id, cap_ver, inputs, contract)
    try:
        out = result.get("output")
        if isinstance(out, list) and out:
            result_target_peer_id = ",".join(str(x.get("peer", "")) for x in out if isinstance(x, dict) and x.get("peer"))
        elif isinstance(out, dict):
            result_target_peer_id = str(out.get("peer") or out.get("target_peer_id") or "")
    except Exception:
        result_target_peer_id = ""
    latency = (time.monotonic() - start) * 1000
    if result.get("success"):
        output_check = comp.strict_validate_against_schema(result.get("output"), contract.get("output_schema", {}))
        if not output_check.compatible:
            _store.transition(iid, "failed_unclean_read_only", invocation_id=invocation_id, failure_code="output_contract_violation")
            events.emit_state_transition(iid, "claimed_by_capability", "failed_unclean_read_only", reason="output_contract_violation")
            events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "passed", "output_contract_violation", "output_contract_violation", "none", None, latency, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
            return {"success": False, "error": "output_contract_violation", "message": output_check.reason, "intervention_id": iid, "state": "failed_unclean_read_only", "invocation_id": invocation_id}
        _store.transition(iid, "resolved_success")
        events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "passed", "succeeded", None, "none", None, latency, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
        events.emit_state_transition(iid, "claimed_by_capability", "resolved_success", reason="dispatcher_success")
        events.emit_outcome(intervention.get("episode_id", ""), iid, "resolved_success", "capability_success", latency, reg.get_contract_hash(cap_id, cap_ver))
        return {"success": True, "capability_id": cap_id, "capability_version": cap_ver, "output": result.get("output"), "intervention_id": iid, "invocation_id": invocation_id}
    failure_code = result.get("error") or "dispatcher_failure"
    effect = contract.get("effect_class", "unknown")
    fallback_id = None
    clean_failure_codes = set(contract.get("error_schema", {}).get("clean_failure_codes", []))
    # v2.4.1: unsupported HMP targets are a deterministic clean read-only
    # incompatibility even on peers whose registry JSON has not yet been migrated.
    if cap_id == "hmp-healthcheck":
        clean_failure_codes.add("unsupported_target")
    if effect == "read_only" and failure_code in clean_failure_codes:
        fallback_id = _store.issue_fallback_token(iid, invocation_id, failure_code)
        events.emit_fallback_authorization(iid, fallback_id or "", invocation_id, failure_code, DEFAULT_FALLBACK_TTL_SECONDS, action="issued")
        state = "fallback_authorized" if fallback_id else "claimed_by_capability"
        events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "passed", "failed_clean", failure_code, "none", fallback_id, latency, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
        return {"success": False, "error": failure_code, "fallback_authorization_id": fallback_id, "intervention_id": iid, "state": state, "invocation_id": invocation_id}
    if effect == "read_only":
        _store.transition(iid, "failed_unclean_read_only", invocation_id=invocation_id, failure_code=failure_code)
        events.emit_state_transition(iid, "claimed_by_capability", "failed_unclean_read_only", reason=failure_code)
        events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "passed", "failed_unclean", failure_code, "none", None, latency, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
        return {"success": False, "error": failure_code, "intervention_id": iid, "state": "failed_unclean_read_only", "invocation_id": invocation_id}
    _store.transition(iid, "failed_requires_safety", invocation_id=invocation_id, failure_code=failure_code)
    events.emit_failure_escalation(iid, invocation_id, effect, failure_code)
    events.emit_invocation(iid, cap_id, cap_ver, reg.get_contract_hash(cap_id, cap_ver), "passed", "failed_requires_safety", failure_code, "unknown", None, latency, invocation_id=invocation_id, validated_inputs=inputs if isinstance(inputs, dict) else {}, preview_target_peer_id=preview_target_peer_id, dispatcher_target_peer_id=dispatcher_target_peer_id, result_target_peer_id=result_target_peer_id)
    return {"success": False, "error": failure_code, "intervention_id": iid, "state": "failed_requires_safety", "invocation_id": invocation_id}

def _stable_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:16]

def observe_alternate_tool_if_relevant(tool_name="", args=None, task_id="", hook_context=None):
    """Observe only known arbitrary-execution surfaces, not every ordinary tool."""
    known_execution_surfaces = {"terminal", "shell", "notebook", "ssh", "remote_exec", "execute_shell"}
    if tool_name not in known_execution_surfaces:
        return None
    try:
        events = _import_sibling("event_store")
        events.emit_alternate_execution(tool_name=tool_name, args_preview=json.dumps(args or {}, default=str), task_id=task_id)
    except Exception:
        return None

def record_tool_outcome(tool_name="", args=None, result=None, task_id="", duration_ms=0, hook_context=None):
    """Record post-tool outcome for passive forward collection."""
    _maintenance_cleanup()
    try:
        events = _import_sibling("event_store")
        args = args or {}
        if tool_name == "execute_code":
            code = args.get("code", "") if isinstance(args, dict) else ""
            code_hash = _stable_hash(code)
            outcome = "success"
            error = None
            session_id = (hook_context or {}).get("session_id", "")
            episode_id = (hook_context or {}).get("episode_id", "") or session_id
            turn_id = (hook_context or {}).get("turn_id", "")
            tool_call_id = (hook_context or {}).get("tool_call_id", task_id)
            blocked = _store.pop_blocked_call(tool_call_id)
            block_origin = ""
            if blocked:
                outcome = "blocked"
                block_origin = blocked.get("origin", events.BLOCK_ORIGIN_PROTOCOL)
                error = blocked.get("reason", "blocked")
            elif isinstance(result, dict):
                if result.get("action") == "block" or result.get("blocked") is True:
                    outcome = "blocked"
                    block_origin = result.get("block_origin") or events.BLOCK_ORIGIN_UNKNOWN
                    error = result.get("reason") or result.get("message") or "blocked"
                elif result.get("exit_code", 0) not in (0, None) or result.get("error"):
                    outcome = "failure"
                    error = result.get("error") or result.get("output", "")
            retrieval = _latest_retrieval_envelope(session_id, episode_id, turn_id)
            events.emit_execute_code_complete(
                code_hash=code_hash,
                outcome=outcome,
                duration_ms=duration_ms,
                error=error,
                session_id=session_id,
                episode_id=episode_id,
                turn_id=turn_id,
                task_id=task_id,
                tool_call_id=tool_call_id,
                retrieval_event_id=retrieval.get("retrieval_event_id", ""),
                block_origin=block_origin,
            )
        else:
            events.emit_observation(capability_id="", capability_version="", effect_class="unknown", observation_coverage={"tool_name": tool_name})
    except Exception:
        return None

# ── Utilities ──

def _now():
    """Return current UTC timestamp as float for age calculations."""
    return time.time()

def get_store_stats() -> dict:
    """Return basic store stats for health check."""
    interventions = _store._interventions
    state_counts = {}
    for inv in interventions.values():
        state = inv.get("state", "?")
        state_counts[state] = state_counts.get(state, 0) + 1
    return {
        "total_interventions": len(interventions),
        "total_tokens": len(_store._tokens),
        "total_unclean": len(_store._unclean),
        "states": state_counts,
        "version": VERSION,
    }