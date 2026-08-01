"""Passive forward collector for capability-reuse live-shadow episodes."""
import hashlib, json, time
try:
    from plugin import event_store as events
except Exception:
    events = None

def stable_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:16]

def observe_execute_code_start(code: str, session_id: str = "", task_id: str = ""):
    if events is None: return None
    return events.emit_execute_code_start(code_preview=code, code_hash=stable_hash(code), session_id=session_id, task_id=task_id)

def observe_execute_code_complete(code: str, result=None, duration_ms: float = 0.0):
    if events is None: return None
    outcome = "success"
    error = None
    if isinstance(result, dict) and (result.get("error") or result.get("exit_code", 0) not in (0, None)):
        outcome = "failure"; error = result.get("error") or result.get("output", "")
    return events.emit_execute_code_complete(code_hash=stable_hash(code), outcome=outcome, duration_ms=duration_ms, error=error)
