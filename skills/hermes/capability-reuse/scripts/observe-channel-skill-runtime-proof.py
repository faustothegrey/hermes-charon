#!/usr/bin/env python3
"""observe-channel-skill-runtime-proof.py — v2.5.0 pinned-runtime
component integration proof.

Dimostra il contratto fra i componenti del percorso observe, sul runtime
installato, SENZA modificare il core:

  retrieval envelope (stesso turno)
    → on_pre_tool_call (plugin capability-reuse) ritorna {"action":"observe"}
    → resolve_pre_tool_block REALE (hermes_cli.plugins)
    → feedback_sink (replica delle ~5 righe del sink di dispatch)
    → tool_progress_callback("tool.considered", ...)
    → _render_observed_bubble REALE (gateway/run.py) → bubble 🔍

NOTA DI CLASSIFICAZIONE (review 2): questo e' COMPONENT RUNTIME
INTEGRATION — il resolver e il renderer sono reali, ma il driver usa un
FakeAgent, crea l'envelope manualmente, carica il plugin installato e
sostituisce temporaneamente mgr._hooks["pre_tool_call"]. NON attraversa
il dispatch completo agent/tool_executor.py da una richiesta gateway
reale: quel tratto resta il real-gateway smoke PENDING (scope formale
peer58<->peer106). La richiesta gateway REALE (envelope HMP da peer70 →
hook live feedback=YES) e' documentata in
evidence/e2e-mesh-v250-peer70-requester.txt.

Esce 0 solo se TUTTI i link sono osservati. Il plugin usato e' quello
caricato dal runtime gateway (stesso modulo, stesso delivery manager).
"""
import sys, traceback

EVIDENCE = []


def ev(line):
    EVIDENCE.append(line)
    print(line)


try:
    # 1. agent con i soli attributi usati dal sink reale
    class FakeAgent:
        session_id = "skill-proof-session"
        _current_turn_id = "t_skill_1"
        _current_api_request_id = "req-skill-1"
        tool_progress_callback = None

    agent = FakeAgent()
    progress_events = []

    def progress_cb(kind, fn, feedback, final_args):
        progress_events.append((kind, fn, feedback, final_args))

    agent.tool_progress_callback = progress_cb

    # 2. hook REALE del plugin capability-reuse registrato nel delivery
    #    manager (stesso manager che usa il gateway)
    from hermes_cli.plugins import (
        get_plugin_manager,
        _delivery_manager,
    )
    try:
        mgr = _delivery_manager()
    except Exception:
        mgr = get_plugin_manager()

    import importlib.util
    import sys as _sys

    # il plugin runtime capability-reuse vive in ~/.hermes/plugins/capability-reuse/
    # con __init__.py e i moduli alla radice: caricalo come package.
    # I sibling (from . import protocol/...) vanno caricati PRIMA di __init__.
    _PLUGIN_DIR = "/home/fausto/.hermes/plugins/capability-reuse"
    _sys.modules["capreuse_rt"] = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            "capreuse_rt",
            f"{_PLUGIN_DIR}/__init__.py",
            submodule_search_locations=[_PLUGIN_DIR],
        )
    )
    for _name in ("protocol", "event_store", "retriever", "registry", "review_queue", "dispatcher", "labels_store", "v244_metadata", "execution_plan", "compatibility"):
        _sib = importlib.util.spec_from_file_location(
            f"capreuse_rt.{_name}",
            f"{_PLUGIN_DIR}/{_name}.py",
        )
        _m = importlib.util.module_from_spec(_sib)
        _sys.modules[f"capreuse_rt.{_name}"] = _m
        _sib.loader.exec_module(_m)
    _spec = importlib.util.spec_from_file_location(
        "capreuse_rt",
        f"{_PLUGIN_DIR}/__init__.py",
        submodule_search_locations=[_PLUGIN_DIR],
    )
    _mod = importlib.util.module_from_spec(_spec)
    _sys.modules["capreuse_rt"] = _mod
    _spec.loader.exec_module(_mod)
    # l'import relativo (from . import protocol) non sempre setta l'attributo
    # sul modulo package: lo fissiamo esplicitamente
    for _name in ("protocol", "event_store", "retriever", "registry", "review_queue", "dispatcher", "labels_store", "v244_metadata", "execution_plan", "compatibility"):
        if f"capreuse_rt.{_name}" in _sys.modules:
            setattr(_mod, _name, _sys.modules[f"capreuse_rt.{_name}"])
    plugin = _mod  # capability-reuse (runtime)

    hooks = mgr._hooks.setdefault("pre_tool_call", [])
    prev = list(hooks)
    hooks[:] = [plugin.on_pre_tool_call]

    try:
        # 3. crea l'envelope retrieval attivo per (session, turn)
        class R:
            def __init__(self):
                self.retrieval_event_id = "rev_skill_1"
                self.session_id = "skill-proof-session"
                self.episode_id = "ep_skill"
                self.turn_id = "t_skill_1"
                # SHADOW-like: capability_id vuoto, candidates popolati
                # (fix v2.5.0 e2e — il gateway gira in shadow mode)
                self.capability_id = ""
                self.capability_version = ""
                self.retrieval_score = 0.6818
                self.latency_ms = 4.0
                self.intervened = False
                self.candidates = [
                    {"capability_id": "hmp-healthcheck",
                     "capability_version": "1.0.0",
                     "score": 0.6818, "eligibility": "rejected",
                     "effect_class": "read_only"}
                ]

        plugin.protocol._remember_retrieval(R())
        ev("[1] envelope retrieval attivo: hmp-healthcheck · score 0.68 (same turn, shadow)")

        # 4. sink come _harness_feedback_sink (replica 5 righe dispatch)
        def harness_sink(feedback):
            cb = getattr(agent, "tool_progress_callback", None)
            if cb is not None:
                cb("tool.considered", "terminal", feedback, {"cmd": "echo skill-proof"})

        from hermes_cli.plugins import resolve_pre_tool_block

        directive = resolve_pre_tool_block(
            tool_name="terminal",
            args={"cmd": "echo skill-proof"},
            task_id="t_skill_1",
            session_id="skill-proof-session",
            tool_call_id="tc-skill-1",
            turn_id="t_skill_1",
            api_request_id="req-skill-1",
            middleware_trace=[],
            feedback_sink=harness_sink,
        )
        ev(f"[2] hook invocato 1 volta (single-fire), block_message={directive!r}")
        assert directive is None  # nessun block: observe non blocca mai

        ev(f"[3] eventi progress: {len(progress_events)} (atteso 1)")
        assert len(progress_events) == 1, "tool.considered non emesso"
        kind, fn, fb, fa = progress_events[0]
        ev(f"[4] kind={kind!r} tool={fn!r} feedback={fb!r}")
        assert kind == "tool.considered" and fn == "terminal"
        assert fb["kind"] == "retrieval" and "hmp-healthcheck" in fb["text"]

        # 5. bubble via renderer gateway reale
        from gateway.run import _render_observed_bubble

        bubble = _render_observed_bubble(fb)
        ev(f"[5] bubble gateway: {bubble!r}")
        assert bubble is not None and "hmp-healthcheck" in bubble

        # 6. single-fire: secondo hook call -> nessun nuovo observe
        from hermes_cli.plugins import resolve_pre_tool_block as rd2

        d2 = rd2(
            tool_name="terminal",
            args={"cmd": "echo skill-proof-2"},
            task_id="t_skill_1",
            session_id="skill-proof-session",
            tool_call_id="tc-skill-2",
            turn_id="t_skill_1",
            api_request_id="req-skill-1",
            middleware_trace=[],
            feedback_sink=harness_sink,
        )
        ev(f"[6] seconda tool call stesso turno: directive={d2!r}, progress totali={len(progress_events)}")
        assert len(progress_events) == 1, "single-fire envelope violato (bubble duplicata)"

        ev("RESULT: PASS — retrieval envelope → observe → feedback_sink → tool.considered → 🔍")
        sys.exit(0)
    finally:
        hooks[:] = prev

except SystemExit:
    raise
except Exception as e:
    ev(f"RESULT: FAIL — {e}")
    traceback.print_exc()
    sys.exit(1)
