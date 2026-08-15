from __future__ import annotations
"""
harness-feedback — Hermes Plugin (dummy v0.1.1)
================================================
🔍 Non-blocking 'observe' channel for the pre_tool_call hook.

Proves the plumbing: a visible mid-turn bubble stating the action was
considered and whether a dedicated harness was applied (dummy rule).
For capability-reuse 2.4.18 the dummy rule is replaced with real
retrieval decisions.

Mode resolution (0.20.1):
  1. plugins.entries.harness-feedback.settings.mode in config.yaml
     ("dummy" → enabled, anything else → off). Canonical knob: the 0.20.1
     gateway does NOT load ~/.hermes/.env into os.environ (verified via
     /proc/<pid>/environ), so the 0.17.0-style env gate is only a fallback.
  2. Legacy env fallback: HARNESS_FEEDBACK_MODE=dummy (peer70 0.17.0 gate).
  3. Default ON when unset: being listed in plugins.enabled IS the opt-in.

Always fail-open: the observe contract never blocks or alters a tool call.
"""
import os

_HARNESS_TOOLS = frozenset({"terminal", "execute_code", "web_extract", "image_generate"})

# Set by register(); hook callbacks receive no ctx in their kwargs.
_CTX = None


def _enabled() -> bool:
    global _CTX
    if _CTX is not None:
        try:
            mode = _CTX.get_config("mode", "") or ""
        except Exception:
            mode = ""
        if str(mode).strip():
            return str(mode).strip().lower() == "dummy"
    env_mode = os.environ.get("HARNESS_FEEDBACK_MODE", "").strip().lower()
    if env_mode:
        return env_mode == "dummy"
    return True


def register(ctx):
    """Plugin entry point. Called once at Hermes startup."""
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_tool_call", on_pre_tool_call)


def on_pre_tool_call(tool_name, args, **kwargs):
    """Non-blocking observe: emit compact structured feedback (v2.4.18.1).

    Shows WHICH tool was considered + whether the (dummy) harness rule
    applies to it:  ⚙️ terminal · harness ok | ⚙️ web_search · harness no
    (kind=generic keeps the legacy string contract working for any consumer;
    structured dicts enable per-kind emoji + duration in the bubble.)
    """
    if not _enabled():
        return None
    applied = "ok" if tool_name in _HARNESS_TOOLS else "no"
    return {
        "action": "observe",
        "feedback": {
            "kind": "generic",
            "text": f"{tool_name} · harness {applied}",
        },
    }
