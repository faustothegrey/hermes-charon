import importlib
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ReviewBlockerRegressionTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CAPABILITY_REUSE_PERMISSIONS", None)
        os.environ.pop("CAPABILITY_REUSE_AVAILABLE_CAPABILITIES", None)
        os.environ["CAPABILITY_REUSE_INTERVENTION_THRESHOLD"] = "0.65"
        os.environ["CAPABILITY_REUSE_MINIMUM_MARGIN"] = "0.10"
        self.protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        self.retriever = importlib.reload(importlib.import_module("plugin.retriever"))
        self.dispatcher = importlib.reload(importlib.import_module("plugin.dispatcher"))
        self.events = importlib.reload(importlib.import_module("plugin.event_store"))
        self.protocol._store = self.protocol.InterventionStore()
        try:
            self.events.EVENT_LOG.unlink()
        except FileNotFoundError:
            pass

    def tearDown(self):
        for key in [
            "CAPABILITY_REUSE_MODE",
            "CAPABILITY_REUSE_ACTIVE_CAPABILITIES",
            "CAPABILITY_REUSE_INTERVENTION_THRESHOLD",
            "CAPABILITY_REUSE_MINIMUM_MARGIN",
            "CAPABILITY_REUSE_PERMISSIONS",
            "CAPABILITY_REUSE_AVAILABLE_CAPABILITIES",
        ]:
            os.environ.pop(key, None)

    def _events(self):
        if not self.events.EVENT_LOG.exists():
            return []
        return [json.loads(line) for line in self.events.EVENT_LOG.read_text().splitlines() if line.strip()]

    def test_shadow_execute_code_events_have_full_correlation_envelope(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
        self.protocol.retrieve(
            session_id="sess-1",
            user_message="check HMP health for peer128",
            hook_context={"episode_id": "ep-1", "turn_id": "turn-1"},
        )
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print(42)"},
            task_id="task-1",
            hook_context={"session_id": "sess-1", "episode_id": "ep-1", "turn_id": "turn-1", "tool_call_id": "tc-1"},
        )
        self.assertTrue(verdict.allowed)
        self.protocol.record_tool_outcome(
            tool_name="execute_code",
            args={"code": "print(42)"},
            result={"exit_code": 0},
            task_id="task-1",
            duration_ms=3.2,
            hook_context={"session_id": "sess-1", "episode_id": "ep-1", "turn_id": "turn-1", "tool_call_id": "tc-1"},
        )
        events = self._events()
        retrieval = next(e for e in events if e["event_type"] == "retrieval_event")
        started = next(e for e in events if e["event_type"] == "execute_code_started_event")
        completed = next(e for e in events if e["event_type"] == "execute_code_completed_event")
        for ev in [started, completed]:
            self.assertEqual("ep-1", ev["data"]["episode_id"])
            self.assertEqual("sess-1", ev["data"]["session_id"])
            self.assertEqual("turn-1", ev["data"]["turn_id"])
            self.assertEqual("task-1", ev["data"]["task_id"])
            self.assertEqual("tc-1", ev["data"]["tool_call_id"])
            self.assertEqual(retrieval["event_id"], ev["data"]["retrieval_event_id"])
        self.assertEqual(started["data"]["code_hash"], completed["data"]["code_hash"])

    def test_active_execute_code_blocks_when_session_and_episode_ids_differ(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        decision = self.protocol.retrieve(
            session_id="sess-A",
            user_message="check HMP health for peer128",
            hook_context={"episode_id": "ep-A", "turn_id": "turn-A"},
        )
        self.assertIsInstance(decision, dict)
        self.protocol.persist_intervention(decision)
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print(1)"},
            task_id="task-A",
            hook_context={"session_id": "sess-A", "episode_id": "ep-A", "turn_id": "turn-A", "tool_call_id": "tc-A"},
        )
        self.assertFalse(verdict.allowed)

    def test_active_execute_code_blocks_when_hook_omits_episode_id(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        self.protocol._store.create_intervention(
            "int_session_only",
            "ep-real",
            "hmp-healthcheck",
            "1.0.0",
            session_id="sess-real",
            turn_id="turn-real",
        )
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print(1)"},
            task_id="task-real",
            hook_context={"session_id": "sess-real", "turn_id": "turn-real", "tool_call_id": "tc-real"},
        )
        self.assertFalse(verdict.allowed)

    def test_fallback_token_must_match_current_blocking_intervention(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        self.protocol._store.create_intervention("int_old", "ep", "hmp-healthcheck", "1.0.0", session_id="sess", turn_id="turn")
        self.assertTrue(self.protocol._store.claim_intervention("int_old", "capability", "inv_old"))
        token = self.protocol._store.issue_fallback_token("int_old", "inv_old", "timeout")
        self.assertIsNotNone(token)
        self.protocol._store.create_intervention("int_new", "ep", "hmp-healthcheck", "1.0.0", session_id="sess", turn_id="turn")
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print(1)", "capability_reuse_fallback_token": token},
            task_id="task",
            hook_context={"session_id": "sess", "episode_id": "ep", "turn_id": "turn", "tool_call_id": "tc"},
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual("fallback_authorized", self.protocol._store.get_intervention("int_old")["state"])
        self.assertEqual("open", self.protocol._store.get_intervention("int_new")["state"])

    def test_injection_contains_intervention_id_and_structured_bypass_contract(self):
        decision = {
            "intervention_id": "int_example",
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "inputs_description": "peer_list",
            "output_description": "network_read",
        }
        text = self.protocol.render_injection(decision)
        self.assertIn("int_example", text)
        self.assertIn("capability_reuse_bypass", text)
        self.assertIn("reason_code", text)

    def test_retriever_generates_unique_uuid_intervention_ids(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        first = self.protocol.retrieve("s", "check HMP health for peer128", {"episode_id": "e1", "turn_id": "t1"})
        second = self.protocol.retrieve("s", "check HMP health for peer128", {"episode_id": "e2", "turn_id": "t2"})
        self.assertNotEqual(first["intervention_id"], second["intervention_id"])
        self.assertTrue(first["intervention_id"].startswith("int_"))

    def test_peer128_gateway_health_prompt_intervenes(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        decision = self.protocol.retrieve("sess", "show peer128 HMP gateway health", {"episode_id": "ep", "turn_id": "turn"})
        self.assertIsInstance(decision, dict)
        self.assertEqual("hmp-healthcheck", decision["capability_id"])

    def test_invalid_bypass_reason_code_is_rejected(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        self.protocol._store.create_intervention("int_bypass", "ep", "hmp-healthcheck", "1.0.0", session_id="sess", turn_id="turn")
        verdict = self.protocol.authorize_execute_code(
            args={"code": "print(1)", "capability_reuse_bypass": {"intervention_id": "int_bypass", "reason_code": "anything"}},
            task_id="task",
            hook_context={"session_id": "sess", "episode_id": "ep", "turn_id": "turn", "tool_call_id": "tc"},
        )
        self.assertFalse(verdict.allowed)

    def test_unclean_read_only_failure_allows_one_structured_continuation(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        self.protocol._store.create_intervention("int_unclean", "ep", "hmp-healthcheck", "1.0.0", session_id="sess", turn_id="turn")
        old_dispatch = self.dispatcher.dispatch
        self.dispatcher.dispatch = lambda *a, **k: {"success": False, "error": "malformed_response", "output": None}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": "int_unclean",
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher.dispatch = old_dispatch
        self.assertEqual("failed_unclean_read_only", result["state"])
        prior_invocation_id = result["invocation_id"]
        verdict = self.protocol.authorize_execute_code(
            args={
                "code": "print('manual recovery')",
                "capability_reuse_bypass": {
                    "intervention_id": "int_unclean",
                    "capability_id": "hmp-healthcheck",
                    "capability_version": "1.0.0",
                    "reason_code": "harness_failure_unclean",
                    "prior_invocation_id": prior_invocation_id,
                    "failure_code": "malformed_response",
                    "detail": "dispatcher returned malformed response; manual code is required",
                },
            },
            task_id="task",
            hook_context={"session_id": "sess", "episode_id": "ep", "turn_id": "turn", "tool_call_id": "tc"},
        )
        self.assertTrue(verdict.allowed, verdict.message)
        self.assertEqual("unclean_fallback_recorded", self.protocol._store.get_intervention("int_unclean")["state"])

    def test_invocation_event_uses_actual_invocation_id(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        self.protocol._store.create_intervention("int_ok", "ep", "hmp-healthcheck", "1.0.0", session_id="sess", turn_id="turn")
        old_probe = self.dispatcher._probe_hmp_health
        self.dispatcher._probe_hmp_health = lambda peer, timeout: {"peer": peer, "status": "ok", "latency_ms": 1, "error": None}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": "int_ok",
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher._probe_hmp_health = old_probe
        self.assertTrue(result["success"])
        inv_event = next(e for e in self._events() if e["event_type"] == "capability_invocation_event")
        self.assertEqual(result["invocation_id"], inv_event["data"]["invocation_id"])

    def test_active_retrieval_does_not_invent_permissions_or_availability(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        decision = self.protocol.retrieve(
            session_id="sess",
            user_message="check HMP health for peer128",
            hook_context={"episode_id": "ep", "turn_id": "turn"},
        )
        self.assertIsNone(decision)

    def test_alternate_execution_logging_only_for_known_execution_surfaces(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
        self.protocol.observe_alternate_tool_if_relevant("search_files", {}, "task", {})
        self.protocol.observe_alternate_tool_if_relevant("terminal", {"command": "date"}, "task", {})
        alt_events = [e for e in self._events() if e["event_type"] == "alternate_execution_event"]
        self.assertEqual(1, len(alt_events))
        self.assertEqual("terminal", alt_events[0]["data"]["tool_name"])

    def test_hmp_healthcheck_rejects_raw_ip_targets(self):
        result = self.dispatcher.hmp_healthcheck({"peer_list": ["192.168.178.70"], "timeout_seconds": 1})
        self.assertFalse(result["success"])
        self.assertEqual("unsupported_target", result["error"])

    def test_hmp_healthcheck_row_failure_is_clean_dispatch_failure(self):
        old_probe = self.dispatcher._probe_hmp_health
        self.dispatcher._probe_hmp_health = lambda peer, timeout: {"peer": peer, "status": "timeout", "latency_ms": None, "error": "timeout"}
        try:
            result = self.dispatcher.hmp_healthcheck({"peer_list": ["peer128"], "timeout_seconds": 1})
        finally:
            self.dispatcher._probe_hmp_health = old_probe
        self.assertFalse(result["success"])
        self.assertEqual("timeout", result["error"])


if __name__ == "__main__":
    unittest.main()
