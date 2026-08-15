import importlib
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Phase1BActiveHealthcheckTests(unittest.TestCase):
    def setUp(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        os.environ["CAPABILITY_REUSE_INTERVENTION_THRESHOLD"] = "0.65"
        os.environ["CAPABILITY_REUSE_MINIMUM_MARGIN"] = "0.10"
        self.protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        self.dispatcher = importlib.reload(importlib.import_module("plugin.dispatcher"))
        self.events = importlib.reload(importlib.import_module("plugin.event_store"))
        self.protocol._store = self.protocol.InterventionStore()
        try:
            self.events.EVENT_LOG.unlink()
        except FileNotFoundError:
            pass

    def tearDown(self):
        for key in ["CAPABILITY_REUSE_MODE", "CAPABILITY_REUSE_ACTIVE_CAPABILITIES", "CAPABILITY_REUSE_PERMISSIONS", "CAPABILITY_REUSE_AVAILABLE_CAPABILITIES", "CAPABILITY_REUSE_INTERVENTION_THRESHOLD", "CAPABILITY_REUSE_MINIMUM_MARGIN"]:
            os.environ.pop(key, None)

    def _events(self):
        if not self.events.EVENT_LOG.exists():
            return []
        return [json.loads(line) for line in self.events.EVENT_LOG.read_text().splitlines() if line.strip()]

    def test_active_pre_llm_injects_healthcheck_and_blocks_raw_execute_code(self):
        decision = self.protocol.retrieve(
            session_id="phase1b-session",
            user_message="check all HMP peers multiple peers partial failures configurable timeout",
            hook_context={"episode_id": "phase1b-episode"},
        )
        self.assertIsInstance(decision, dict)
        self.assertEqual("hmp-healthcheck", decision["capability_id"])
        self.protocol.persist_intervention(decision)
        injection = self.protocol.render_injection(decision)
        self.assertIn("hmp-healthcheck@1.0.0", injection)
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print('manual fallback')"},
            task_id="task1",
            hook_context={"session_id": "phase1b-episode", "tool_call_id": "tc1"},
        )
        self.assertFalse(verdict.allowed)
        self.assertIn(decision["intervention_id"], verdict.message)
        types = [e["event_type"] for e in self._events()]
        self.assertIn("retrieval_event", types)
        self.assertIn("intervention_event", types)

    def test_invoke_hmp_healthcheck_success_resolves_intervention_and_logs_chain(self):
        self.protocol._store.create_intervention("int_ok", "episode_ok", "hmp-healthcheck", "1.0.0")
        old_probe = self.dispatcher._probe_hmp_health
        self.dispatcher._probe_hmp_health = lambda peer, timeout: {"peer": peer, "status": "ok", "latency_ms": 1.5, "error": None}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": "int_ok",
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher._probe_hmp_health = old_probe
        self.assertTrue(result["success"], result)
        self.assertEqual("resolved_success", self.protocol._store.get_intervention("int_ok")["state"])
        types = [e["event_type"] for e in self._events()]
        self.assertIn("capability_invocation_event", types)
        self.assertIn("outcome_event", types)

    def test_clean_read_only_failure_issues_single_fallback_token_that_allows_one_execute_code(self):
        self.protocol._store.create_intervention("int_fail", "episode_fail", "hmp-healthcheck", "1.0.0")
        old_dispatch = self.dispatcher.dispatch
        self.dispatcher.dispatch = lambda *a, **k: {"success": False, "error": "timeout", "output": None}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": "int_fail",
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher.dispatch = old_dispatch
        token = result.get("fallback_authorization_id")
        self.assertFalse(result["success"])
        self.assertTrue(token, result)
        bypass = {
            "intervention_id": "int_fail",
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "reason_code": "harness_failure",
            "prior_invocation_id": result.get("invocation_id"),
            "failure_code": "timeout",
            "fallback_authorization_id": token,
        }
        allowed = self.protocol.authorize_execute_code(
            args={"code": "print('fallback')", "capability_reuse_bypass": bypass},
            task_id="task-fb",
            hook_context={"session_id": "episode_fail", "tool_call_id": "tc-fb"},
        )
        self.assertTrue(allowed.allowed, allowed.message)
        reused = self.protocol.authorize_execute_code(
            args={"code": "print('fallback again')", "capability_reuse_bypass": bypass},
            task_id="task-fb2",
            hook_context={"session_id": "episode_fail", "tool_call_id": "tc-fb2"},
        )
        self.assertFalse(reused.allowed, "terminal fallback decision should be exactly-once per turn")
        self.assertEqual("fallback_consumed", self.protocol._store.get_intervention("int_fail")["state"])

    def test_mutating_capability_not_in_active_allowlist(self):
        self.protocol._store.create_intervention("int_send", "episode_send", "hmp-send", "1.0.0")
        result = self.protocol.invoke_capability({
            "intervention_id": "int_send",
            "capability_id": "hmp-send",
            "capability_version": "1.0.0",
            "inputs": {"peer": "peer70", "text": "hello"},
        })
        self.assertFalse(result["success"])
        self.assertEqual("capability_not_active", result["error"])

    def test_observed_read_only_capability_cannot_be_invoked_even_if_allowlisted(self):
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck,peer-heartbeat"
        self.protocol._store.create_intervention("int_heartbeat", "episode_heartbeat", "peer-heartbeat", "1.0.0")
        result = self.protocol.invoke_capability({
            "intervention_id": "int_heartbeat",
            "capability_id": "peer-heartbeat",
            "capability_version": "1.0.0",
            "inputs": {"peer": "peer70", "timeout_seconds": 1},
        })
        self.assertFalse(result["success"])
        self.assertEqual("capability_not_trusted", result["error"])
        self.assertEqual("observed", result["trust_state"])

    def test_peer138_is_supported_healthcheck_target(self):
        label, ip, path = self.dispatcher._resolve_peer("peer138")
        self.assertEqual(("peer138", "192.168.178.138", "/hmp/health"), (label, ip, path))

    def test_healthcheck_shorthand_prompt_retrieves_for_peer138(self):
        decision = self.protocol.retrieve(
            session_id="peer138-shorthand-session",
            user_message="healthcheck peer138 via HMP",
            hook_context={"episode_id": "peer138-shorthand-episode", "turn_id": "turn-01"},
        )
        self.assertIsInstance(decision, dict)
        self.assertEqual("hmp-healthcheck", decision["capability_id"])
        self.assertGreaterEqual(decision["retrieval_score"], 0.65)

    def test_plugin_entrypoint_routes_through_controller_active_blocking_and_correlation(self):
        class FakeCtx:
            def __init__(self):
                self.tools = []
                self.hooks = []

            def register_tool(self, **kwargs):
                self.tools.append(kwargs)

            def register_hook(self, name, handler):
                self.hooks.append((name, handler))

        plugin = importlib.reload(importlib.import_module("plugin"))

        os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
        shadow_ctx = FakeCtx()
        plugin.register(shadow_ctx)
        self.assertEqual([], [t for t in shadow_ctx.tools if t.get("name") == "invoke_capability"])

        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        active_ctx = FakeCtx()
        plugin.register(active_ctx)
        self.assertEqual(1, len([t for t in active_ctx.tools if t.get("name") == "invoke_capability"]))

        hook_context = {
            "episode_id": "entry-episode",
            "turn_id": "entry-turn",
            "tool_call_id": "entry-tool-call",
        }
        injection = plugin.on_pre_llm_call(
            session_id="entry-session",
            user_message="healthcheck peer138 via HMP",
            **hook_context,
        )
        self.assertIsInstance(injection, dict)
        self.assertIn("hmp-healthcheck@1.0.0", injection.get("context", ""))

        block = plugin.on_pre_tool_call(
            "execute_code",
            {"code": "print('manual fallback')"},
            task_id="entry-task",
            session_id="entry-session",
            **hook_context,
        )
        self.assertEqual("block", block.get("action"))
        self.assertIn("capability-reuse active intervention", block.get("message", ""))

        plugin.on_post_tool_call(
            "execute_code",
            {"code": "print('manual fallback')"},
            {"action": "block", "message": block["message"]},
            task_id="entry-task",
            duration_ms=3,
            session_id="entry-session",
            **hook_context,
        )

        events = self._events()
        retrieval = next(e for e in events if e["event_type"] == "retrieval_event")
        started = next(e for e in events if e["event_type"] == "execute_code_started_event")
        completed = next(e for e in events if e["event_type"] == "execute_code_completed_event")
        for ev in (started, completed):
            data = ev["data"]
            self.assertEqual("entry-session", data["session_id"])
            self.assertEqual("entry-episode", data["episode_id"])
            self.assertEqual("entry-turn", data["turn_id"])
            self.assertEqual("entry-tool-call", data["tool_call_id"])
            self.assertEqual(retrieval["event_id"], data["retrieval_event_id"])
        self.assertTrue(started["data"]["code_hash"])
        self.assertEqual("blocked", completed["data"]["outcome"])
        self.assertEqual("protocol", completed["data"]["block_origin"])

    def test_request_scoped_provenance_is_emitted_and_env_does_not_override_hook(self):
        os.environ["CAPABILITY_REUSE_PROVENANCE"] = "calibration_probe"
        decision = self.protocol.retrieve(
            session_id="prov-session",
            user_message="healthcheck peer138 via HMP",
            hook_context={
                "episode_id": "prov-episode",
                "turn_id": "prov-turn",
                "capability_reuse_provenance": "operator_seeded",
                "capability_reuse_provenance_detail": "manual realistic prompt",
            },
        )
        self.assertIsInstance(decision, dict)
        retrieval = next(e for e in self._events() if e["event_type"] == "retrieval_event")
        self.assertEqual("1.3", retrieval["schema_version"])
        self.assertEqual("operator_seeded", retrieval["data"]["provenance"]["stream"])
        self.assertEqual("hook_context.capability_reuse_provenance", retrieval["data"]["provenance"]["source"])

    def test_uncovered_multistep_health_prompt_does_not_intervene(self):
        prompts = [
            "check HMP health for peer138 and if it is down investigate the gateway",
            "ping HMP peer138 then open a ticket if not ok",
            "healthcheck peer138 via HMP and then notify me if failing",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                decision = self.protocol.retrieve(
                    session_id="multi-session",
                    user_message=prompt,
                    hook_context={"episode_id": "multi-episode", "turn_id": prompt[:8]},
                )
                self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
