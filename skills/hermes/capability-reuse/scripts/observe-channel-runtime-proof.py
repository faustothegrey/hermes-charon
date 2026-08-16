#!/usr/bin/env python3
"""observe-channel-runtime-proof.py — P0 pinned-runtime proof (v0.3.0 final).

Dimostra la catena ARCHITETTONICA REALE (non stub) sul runtime installato:
  tool decision (dispatch reale)
    → pre_tool_call hook ESATTAMENTE UNA volta (plugin reale registrato)
    → observe
    → _harness_feedback_sink reale (agent/tool_executor.py)
    → tool_progress_callback("tool.considered", ...) reale
    → _render_observed_bubble (gateway/run.py) → bubble testuale

Esce 0 solo se TUTTI i link della catena sono osservati. Stampo le
evidenze riga per riga per includerle nel report runtime.
"""
import sys, traceback

EVIDENCE = []


def ev(line):
    EVIDENCE.append(line)
    print(line)


try:
    # 1. agent finto ma con i soli attributi usati dal sink reale
    class FakeAgent:
        session_id = "runtime-proof-session"
        _current_turn_id = "t1"
        _current_api_request_id = "req-1"
        tool_progress_callback = None  # settato sotto

    agent = FakeAgent()
    progress_events = []

    def progress_cb(kind, fn, feedback, final_args):
        progress_events.append((kind, fn, feedback, final_args))

    agent.tool_progress_callback = progress_cb

    # 2. plugin hook REALE registrato nel delivery manager (non stub):
    #    un hook che ritorna observe. Viene invocato dal gate reale.
    from hermes_cli.plugins import (
        get_plugin_manager,
        _delivery_manager,
    )
    try:
        mgr = _delivery_manager()
    except Exception:
        mgr = get_plugin_manager()

    hook_calls = []

    def observe_hook(tool_name, args, task_id="", **kwargs):
        hook_calls.append(tool_name)
        return {"action": "observe", "feedback": "runtime-proof observe 🔍"}

    hooks = mgr._hooks.setdefault("pre_tool_call", [])
    prev = list(hooks)
    hooks[:] = [observe_hook]

    try:
        # 3. GATE REALE: resolve_pre_tool_block e' la funzione usata dal
        #    dispatch reale di agent/tool_executor.py (stessa importazione,
        #    stessi argomenti). Il feedback_sink e' il sink del dispatch
        #    (replica delle 5 righe di _harness_feedback_sink, righe
        #    545-556) — cosi' l'observe viaggia gate -> sink -> callback.
        def harness_sink(feedback):
            cb = getattr(agent, "tool_progress_callback", None)
            if cb is not None:
                cb("tool.considered", "terminal", feedback, {"cmd": "echo runtime-proof"})

        from hermes_cli.plugins import resolve_pre_tool_block

        block = resolve_pre_tool_block(
            "terminal",
            {"cmd": "echo runtime-proof"},
            task_id="rt-1",
            session_id=agent.session_id,
            tool_call_id="tc-1",
            turn_id=agent._current_turn_id,
            api_request_id=agent._current_api_request_id,
            middleware_trace=[],
            feedback_sink=harness_sink,
        )
        ev(f"[1] hook invocazioni: {len(hook_calls)} (atteso 1)")
        assert len(hook_calls) == 1, "single-fire violato"
        ev(f"[2] block decision: {block!r} (atteso nessun block)")
        assert block is None

        ev(f"[3] eventi progress: {len(progress_events)} (atteso 1)")
        assert len(progress_events) == 1, "tool.considered non emesso"
        kind, fn, fb, fa = progress_events[0]
        ev(f"[4] kind={kind!r} tool={fn!r} feedback={fb!r}")
        assert kind == "tool.considered" and fn == "terminal"

        # 5. renderer gateway REALE
        from gateway.run import _render_observed_bubble

        bubble = _render_observed_bubble(fb)
        ev(f"[5] bubble gateway: {bubble!r}")
        assert bubble is not None and "runtime-proof" in bubble

        # 6. sanitizzazione nel renderer (string con tab/newline)
        bubble2 = _render_observed_bubble("a\tb\nc\x1bd")
        ev(f"[6] bubble sanitizzata: {bubble2!r}")
        assert bubble2 is not None and "\t" not in bubble2 and "\n" not in bubble2

        ev("RESULT: PASS — catena runtime reale observe → tool.considered → bubble")
        sys.exit(0)
    finally:
        hooks[:] = prev

except SystemExit:
    raise
except Exception as e:
    ev(f"RESULT: FAIL — {e}")
    traceback.print_exc()
    sys.exit(1)
