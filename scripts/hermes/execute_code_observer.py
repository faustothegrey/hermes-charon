"""
execute_code_observer — Phase 0.3: Forward instrumentation wrapper.

Wraps execute_code calls to capture request, code, and outcome events.
Non-blocking, append-only JSONL log. No behavioral changes.
Kill switch via env var HERMES_OBSERVER_DISABLE=1.

Import in the agent init or load as a plugin:
  from execute_code_observer import observe_execute_code
  observe_execute_code()  # patches execute_code tool

Output: ~/.hermes/data/reuse-observer/events.jsonl
"""
import json, os, time, uuid, functools, inspect
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

OBSERVER_DIR = Path.home() / ".hermes" / "data" / "reuse-observer"
EVENTS_LOG = OBSERVER_DIR / "events.jsonl"
SESSION_CONTEXT_LOG = OBSERVER_DIR / "session-context.jsonl"

# ── Kill switch ──
DISABLED = os.environ.get("HERMES_OBSERVER_DISABLE", "0") == "1"

# ── Private event counter (thread-safe enough for logging) ──
_event_counter = 0

def _ensure_dir():
    OBSERVER_DIR.mkdir(parents=True, exist_ok=True)

def _episode_id():
    """Return current episode/session ID if available."""
    try:
        from hermes_agent.agent import agent_context
        ctx = agent_context.get()
        return getattr(ctx, "session_id", None) or getattr(ctx, "episode_id", None)
    except (ImportError, AttributeError):
        return None

def _context_snapshot():
    """Capture deterministic context: current session, recent messages, active tools."""
    ctx = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from hermes_agent.agent import agent_context
        actx = agent_context.get()
        ctx["session_id"] = getattr(actx, "session_id", None)
        ctx["episode_id"] = getattr(actx, "episode_id", None)
        # Capture last user message if available
        if hasattr(actx, "conversation") and actx.conversation:
            last_user = None
            for msg in reversed(actx.conversation.messages):
                if getattr(msg, "role", "") == "user":
                    last_user = getattr(msg, "content", "")[:500]
                    break
            ctx["last_user_request"] = last_user
    except (ImportError, AttributeError):
        pass
    return ctx

def _emit_event(event_type, data):
    """Write one event to the JSONL log."""
    global _event_counter
    if DISABLED:
        return
    
    _event_counter += 1
    _ensure_dir()
    
    event = {
        "event_id": f"{uuid.uuid4().hex[:16]}",
        "event_type": event_type,
        "schema_version": "1.0",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seq": _event_counter,
        "data": data,
    }
    
    try:
        with open(EVENTS_LOG, "a") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass  # silent — never block execution for logging

def _hash_code(code):
    """Simple hash for deduplication without storing full code."""
    return str(hash(code))

def _fingerprint_code(code):
    """Lightweight code fingerprint: imports, tools called, URL patterns."""
    import re
    fp = {
        "imports": [],
        "tool_calls": [],
        "urls": [],
        "patterns": [],
        "has_curl": False,
        "has_subprocess": False,
    }
    
    if not code:
        return fp
    
    # Imports
    for m in re.finditer(r'(?:import|from)\s+([a-zA-Z0-9_]+)', code):
        fp["imports"].append(m.group(1))
    
    # Tool calls (hermes_tools or direct)
    for m in re.finditer(r'(?:from hermes_tools import|hermes_tools\.)(\w+)', code):
        fp["tool_calls"].append(m.group(1))
    for m in re.finditer(r'terminal\(|read_file\(|write_file\(|search_files\(|web_search\(|web_extract\(', code):
        fp["tool_calls"].append(m.group()[:-1])
    
    # URLs
    for m in re.finditer(r'https?://[^\s"\'\)]+', code):
        fp["urls"].append(m.group()[:100])
    
    # curl / subprocess detection
    fp["has_curl"] = "curl" in code
    fp["has_subprocess"] = "subprocess" in code
    
    # Operation patterns
    if "health" in code.lower():
        fp["patterns"].append("healthcheck")
    if "/hmp/send" in code or "hmp.send" in code:
        fp["patterns"].append("hmp_send")
    if "json.loads" in code or "json.dumps" in code:
        fp["patterns"].append("json")
    if "ssh" in code.lower():
        fp["patterns"].append("ssh")
    if "cronjob" in code or "cron" in code.lower():
        fp["patterns"].append("cron")
    if "scp" in code or "sftp" in code:
        fp["patterns"].append("scp")
    if "broadcast" in code.lower():
        fp["patterns"].append("broadcast")
    
    return fp

# ── Public API ──

def log_execute_code_start(code, tool_name="execute_code"):
    """Call BEFORE execute_code runs. Returns context_id for correlation."""
    ctx = _context_snapshot()
    fp = _fingerprint_code(code)
    
    event_data = {
        "tool": tool_name,
        "code_hash": _hash_code(code),
        "code_length": len(code) if code else 0,
        "code_preview": code[:200] if code else "",
        "fingerprint": fp,
        "context": ctx,
    }
    
    _emit_event("execute_code_started", event_data)
    return event_data["code_hash"]

def log_execute_code_complete(context_id, outcome, duration_ms=None, error=None):
    """Call AFTER execute_code completes. outcome: 'success', 'failure', 'blocked'."""
    event_data = {
        "code_hash": context_id,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "error_preview": str(error)[:200] if error else None,
    }
    _emit_event("execute_code_completed", event_data)

def log_retrieval(operation_text, candidates=None):
    """Log a retrieval attempt (Phase 1A+). No-op in Phase 0."""
    if DISABLED:
        return
    event_data = {
        "operation_preview": operation_text[:200] if operation_text else "",
        "candidates": candidates or [],
        "phase": "0.3",
    }
    _emit_event("retrieval_shadow", event_data)

def get_stats():
    """Return basic observer stats."""
    if not EVENTS_LOG.exists():
        return {"total_events": 0}
    try:
        with open(EVENTS_LOG) as f:
            lines = [l for l in f if l.strip()]
        return {
            "total_events": len(lines),
            "file_path": str(EVENTS_LOG),
            "disabled": DISABLED,
        }
    except OSError:
        return {"total_events": 0, "error": "cannot_read"}

# ── Auto-initialize ──
if not DISABLED:
    _ensure_dir()
    _emit_event("observer_initialized", {
        "phase": "0.3",
        "mode": "forward_collection",
        "behavior_change": False,
    })
