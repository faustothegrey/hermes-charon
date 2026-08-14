from __future__ import annotations
"""
harness-feedback — dummy plugin for the 2.4.18 pre_tool_call observe hook.

Emits a short user-visible feedback line before every tool call stating
that the prompt action was considered and whether a dedicated harness
was applied. Purely informational: action "observe" NEVER blocks.

Replace the dummy logic with real capability-reuse decisions later.
"""
import os

# Dummy rule: "harness applied" for a fixed set of tool names; everything
# else is "not applied". Replace with real capability-reuse retrieval.
_HARNESS_TOOLS = {"terminal", "execute_code", "web_extract", "image_generate"}


def _harness_applied(tool_name: str) -> str:
    if tool_name in _HARNESS_TOOLS:
        return "applicato"
    return "non applicato"


def _mode() -> str:
    return os.environ.get("HARNESS_FEEDBACK_MODE", "dummy").strip().lower() or "dummy"


def register(ctx):
    ctx.register_hook("pre_tool_call", on_pre_tool_call)


def on_pre_tool_call(tool_name="", args=None, **kwargs):
    """Return observe feedback for every tool call (dummy)."""
    if _mode() != "dummy":
        return None
    harness = _harness_applied(str(tool_name or ""))
    feedback = f"azione considerata · harness {harness} (dummy)"
    return {"action": "observe", "feedback": feedback}
