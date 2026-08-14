from __future__ import annotations
"""
capability-reuse — Hermes Plugin (Phase 1 skeleton)
====================================================
Appendix A — Reference Hermes Plugin Skeleton (spec v1.6)

Plugin lifecycle:
  1. Hermes discovers plugin via plugin.yaml in ~/.hermes/plugins/capability-reuse/
  2. Calls register(ctx) → registers tool + hooks
  3. Hooks fire on each turn/tool call

Exact callback kwargs and block return contract are accepted only
after the pinned-runtime conformance suite passes.
"""
import json, os
from pathlib import Path

# Local controller module (can be imported from skill dir or bundled)
# In production, these would be in ~/.hermes/plugins/capability-reuse/
from . import protocol as ctrl


def _mode() -> str:
    return os.environ.get("CAPABILITY_REUSE_MODE", "shadow").strip().lower() or "shadow"


def register(ctx):
    """Plugin entry point. Called once at Hermes startup.

    Shadow/live-shadow mode must not expose executable tools to the model.
    invoke_capability is registered only when explicitly enabled with
    CAPABILITY_REUSE_MODE=active. Hooks remain enabled for passive collection.
    """
    if _mode() == "active":
        ctx.register_tool(
            name="invoke_capability",
            toolset="capability_reuse",
            schema=ctrl.invoke_schema(),
            handler=handle_invoke_capability,
            description="Invoke an exact trusted registered capability version with typed inputs. "
                        "Uses the capability's invocation contract for validation and dispatch.",
        )

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)


def on_pre_llm_call(session_id="", user_message="", **kwargs):
    """
    Called once per turn, before the tool-calling loop.

    Returns:
      None (below threshold) or {"context": str} (injection into user message).
    """
    decision = ctrl.retrieve(
        session_id=session_id,
        user_message=user_message,
        hook_context=kwargs,
    )
    if decision is None:
        return None

    ctrl.persist_intervention(decision)
    return {"context": ctrl.render_injection(decision)}


def on_pre_tool_call(tool_name, args, task_id="", **kwargs):
    """
    Called before each tool call.

    For execute_code: validates bypass or allows.
    For other tools: observes for alternate execution tracking.
    """
    if tool_name != "execute_code":
        ctrl.observe_alternate_tool_if_relevant(
            tool_name=tool_name,
            args=args,
            task_id=task_id,
            hook_context=kwargs,
        )
        return None

    verdict = ctrl.authorize_execute_code(
        args=args,
        task_id=task_id,
        hook_context=kwargs,
    )
    if verdict.allowed:
        return None
    return {"action": "block", "message": verdict.message}


def handle_invoke_capability(params, **kwargs):
    """
    Tool handler for invoke_capability.
    Receives validated params from Hermes tool dispatch.

    Returns JSON string (Hermes tool convention).
    """
    result = ctrl.invoke_capability(params=params, hook_context=kwargs)
    return json.dumps(result, ensure_ascii=False)


def on_post_tool_call(
    tool_name,
    args,
    result,
    task_id="",
    duration_ms=0,
    **kwargs,
):
    """
    Called after each tool call completes (success, failure, or blocked).
    Records outcomes, latency, and observation signals.
    """
    ctrl.record_tool_outcome(
        tool_name=tool_name,
        args=args,
        result=result,
        task_id=task_id,
        duration_ms=duration_ms,
        hook_context=kwargs,
    )
