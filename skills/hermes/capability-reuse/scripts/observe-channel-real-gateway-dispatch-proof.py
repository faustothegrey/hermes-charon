#!/usr/bin/env python3
"""observe-channel-real-gateway-dispatch-proof.py — v2.5.0 real-gateway
dispatch smoke (integration_only, peer141 local runtime).

Obiettivo (review 3 / accordo peer70): una SOLA trace runtime che attraversa
il DISPATCH REALE di agent/tool_executor.py:

    hook pre_tool_call (plugin capability-reuse installato)
      → resolve_pre_tool_block REALE (hermes_cli.plugins)
      → feedback_sink INTERNO del dispatch reale (_harness_feedback_sink,
        creato da _run_agent_tool_execution_middleware — NON replica)
      → agent.tool_progress_callback("tool.considered", ...) REALE
      → _render_observed_bubble REALE (gateway/run.py)
      → 🔍

NOTA DI CLASSIFICAZIONE: il driver NON instanzia l'agente LLM completo
(non e' necessario per il wiring observe); usa un agent con i soli
attributi che il dispatch legge per il canale observe
(tool_progress_callback, session_id, _current_turn_id, ecc.). La richiesta
gateway REALE (HMP peer70 -> peer141, hook live feedback=YES) e'
documentata separatamente in evidence/e2e-mesh-v250-peer70-requester.txt;
questa prova chiude il tratto dispatch-sink->tool.considered->bubble in
una trace unica e riproducibile.

Esce 0 solo se la catena completa e' osservata in UNA esecuzione.
"""
import importlib.util
import json
import sys
import traceback

FAIL = []
EVENTS = []


def ev(msg):
    print(msg)
    EVENTS.append(msg)


def main() -> int:
    # 0. carica il plugin capability-reuse INSTALLATO (runtime gateway)
    plugin = None
    try:
        _PLUGIN_DIR = "/home/fausto/.hermes/plugins/capability-reuse"
        _spec = importlib.util.spec_from_file_location(
            "capreuse_rt",
            f"{_PLUGIN_DIR}/__init__.py",
            submodule_search_locations=[_PLUGIN_DIR],
        )
        plugin = importlib.util.module_from_spec(_spec)
        import sys as _sys
        _sys.modules["capreuse_rt"] = plugin
        _spec.loader.exec_module(plugin)
        ev("[0] plugin capability-reuse caricato (runtime installato)")
    except Exception:
        traceback.print_exc()
        FAIL.append("plugin load")

    # 1. crea l'envelope retrieval attivo per (session, turn) — shadow-like
    #    (capability_id vuoto, candidates popolati: esattamente come nel
    #    gateway in shadow mode)
    class R:
        def __init__(self):
            self.retrieval_event_id = "rev_gw_dispatch"
            self.session_id = "gw-dispatch-session"
            self.episode_id = "ep_gw"
            self.turn_id = "t_gw_1"
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
    ev("[1] envelope retrieval attivo (same session+turn, shadow)")

    # 2. registra l'hook pre_tool_call del plugin nel delivery manager reale
    from hermes_cli import plugins as hp
    # 0.20.1+ espone _delivery_manager(); 0.17.x usa get_plugin_manager() —
    # entrambi hanno _hooks[hook_name] = [callbacks].
    try:
        mgr = hp._delivery_manager()
    except AttributeError:
        mgr = hp.get_plugin_manager()
    orig_hooks = mgr._hooks.get("pre_tool_call", [])
    mgr._hooks["pre_tool_call"] = [plugin.on_pre_tool_call]
    ev("[2] hook pre_tool_call = plugin capability-reuse (delivery manager reale)")

    # 3. agent con gli attributi che il dispatch legge per il canale observe
    progress = []

    def real_tool_progress_callback(kind, tool_name, feedback, final_args):
        progress.append((kind, tool_name, feedback, final_args))

    class Agent:
        session_id = "gw-dispatch-session"
        _current_turn_id = "t_gw_1"
        _current_api_request_id = "api_gw_1"
        _turns_since_memory = 99
        _iters_since_skill = 99
        quiet_mode = False
        tool_progress_mode = "all"
        verbose_logging = False
        log_prefix_chars = 1000

        def _touch_activity(self, msg=None):
            pass

        tool_start_callback = None

        class _CheckpointMgr:
            enabled = False

        _checkpoint_mgr = _CheckpointMgr()
        tool_progress_callback = staticmethod(real_tool_progress_callback)

        class _AllowDecision:
            allows_execution = True

        class _Guardrails:
            def before_call(self, name, args):
                return Agent._AllowDecision()

        _tool_guardrails = _Guardrails()

        def _guardrail_block_result(self, decision):
            return json.dumps({"error": "guardrail_block"})

        def __getattr__(self, name):
            # Fallback benigno per gli attributi non essenziali che il
            # dispatch 0.17 legge (il target del driver è il gate+sink,
            # NON la fedeltà completa dell'esecuzione tool).
            if name == "_subdirectory_hints":
                class _H:
                    def check_tool_call(self, *a, **k):
                        return []
                    def record(self, *a, **k):
                        pass
                return _H()
            if name == "_tool_result_content_for_active_model":
                return lambda function_name, result: str(result)
            if name in ("_apply_pending_steer_to_tool_results", "_emit_skill_progress"):
                return lambda *a, **k: None
            return None

    agent = Agent()

    # 4. dispatch REALE. Architetture core diverse:
    #    - 0.20.1+: _run_agent_tool_execution_middleware contiene il gate
    #      con _harness_feedback_sink INTERNO
    #    - 0.17.x: il gate col sink interno vive in
    #      execute_tool_calls_sequential (il middleware 0.17 non ha gate)

    def _core_is_ge_020():
        import hermes_cli
        v = getattr(hermes_cli, "__version__", "") or ""
        parts = [int(p) for p in v.split(".")[:2] if p.isdigit()]
        return len(parts) == 2 and tuple(parts) >= (0, 20)

    def fake_execute(final_args):
        return {"success": True, "output": "echo v250-gw-dispatch"}

    if _core_is_ge_020():
        from agent.tool_executor import _run_agent_tool_execution_middleware

        ev("[3] invio del dispatch reale (middleware, core >= 0.20)...")
        result = _run_agent_tool_execution_middleware(
            agent,
            function_name="terminal",
            function_args={"command": "echo v250-gw-dispatch"},
            effective_task_id="task_gw_1",
            tool_call_id="call_gw_1",
            execute=fake_execute,
            display_index=1,
        )
        ev(f"[4] dispatch completato: blocked={result.blocked if hasattr(result, 'blocked') else '?'}")
    else:
        # 0.17.x: execute_tool_calls_sequential (gate+sink reale a riga 939)
        from types import SimpleNamespace
        from agent.tool_executor import execute_tool_calls_sequential

        agent.valid_tool_names = ["terminal"]
        agent.enabled_toolsets = None
        agent.disabled_toolsets = None
        agent._print_fn = lambda *a, **k: None
        agent._hermes_home = None
        agent._should_emit_quiet_tool_messages = lambda: False
        agent._vprint = lambda *a, **k: None
        agent._memory_manager = None
        agent._interrupt_requested = False
        agent._context_engine_tool_names = None
        agent._recent_tools = []
        agent._append_guardrail_observation = lambda *a, **k: json.dumps({"error": "noop"})
        agent.tool_complete_callback = None
        agent.tool_delay = 0

        def _mk_msg(call_id, cmd):
            return SimpleNamespace(
                tool_calls=[SimpleNamespace(
                    id=call_id,
                    function=SimpleNamespace(name="terminal", arguments=f'{{"command": "{cmd}"}}'),
                )]
            )

        ev("[3] invio del dispatch reale (execute_tool_calls_sequential, core 0.17)...")
        execute_tool_calls_sequential(agent, _mk_msg("call_gw_1", "echo v250-gw-dispatch"), [], "task_gw_1", 0)
        ev("[4] dispatch completato (sequential)")

    # 5. verifica la catena: hook chiamato 1 volta, observe -> sink interno
    #    -> tool.considered -> bubble renderizzata
    from gateway.run import _render_observed_bubble as render

    n_considered = 0
    n_generic = 0
    for kind, tool, feedback, fargs in progress:
        if kind != "tool.considered":
            continue
        # v2.5.0 fix (verifica peer70): conta SOLO i feedback kind=retrieval
        # (capability-reuse). I kind=generic (es. plugin dummy
        # harness-feedback 'terminal · harness ok') sono per-call di design
        # e non devono rompere il single-fire — il filtro per kind è robusto
        # e indipendente dall'identità del plugin (il dummy può rinominarsi).
        if isinstance(feedback, dict) and feedback.get("kind") == "retrieval":
            n_considered += 1
            ev(f"[5] tool.considered n={n_considered}: tool={tool!r} feedback={feedback!r}")
            rendered = render(feedback)
            ev(f"[6] bubble renderizzata (renderer REALE): {rendered!r}")
            assert "hmp-healthcheck" in rendered, "bubble manca capability"
            assert "0.68" in rendered, "bubble manca score"
        else:
            n_generic += 1
            ev(f"[5b] tool.considered kind!=retrieval ignorato (n={n_generic}): {feedback!r}")

    if n_considered != 1:
        FAIL.append(f"tool.considered count={n_considered} (atteso 1, single-fire)")

    # 6. single-fire: seconda esecuzione con lo STESSO turno -> nessuna bubble
    progress.clear()
    if _core_is_ge_020():
        from agent.tool_executor import _run_agent_tool_execution_middleware

        _run_agent_tool_execution_middleware(
            agent,
            function_name="terminal",
            function_args={"command": "echo v250-gw-dispatch-2"},
            effective_task_id="task_gw_1",
            tool_call_id="call_gw_2",
            execute=fake_execute,
            display_index=2,
        )
    else:
        from agent.tool_executor import execute_tool_calls_sequential

        execute_tool_calls_sequential(agent, _mk_msg("call_gw_2", "echo v250-gw-dispatch-2"), [], "task_gw_1", 0)
    # conta SOLO le bubble 🔍 kind=retrieval (le ⚙️ kind=generic sono per-call)
    n2 = sum(
        1 for k, _, feedback, _ in progress
        if k == "tool.considered" and isinstance(feedback, dict)
        and feedback.get("kind") == "retrieval"
    )
    ev(f"[7] seconda tool call stesso turno: bubble 🔍 retrieval={n2} (atteso 0)")
    if n2 != 0:
        FAIL.append(f"single-fire violato: {n2}")

    # 7. pulizia hook
    mgr._hooks["pre_tool_call"] = orig_hooks
    ev("[8] hook ripristinati")

    if FAIL:
        ev("RESULT: FAIL — " + ", ".join(FAIL))
        return 1
    ev("RESULT: PASS — dispatch reale → sink interno → tool.considered → 🔍 (single-fire)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
