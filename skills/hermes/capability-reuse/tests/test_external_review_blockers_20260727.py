import importlib
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ExternalReviewBlockerTests(unittest.TestCase):
    def setUp(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        self.protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        self.dispatcher = importlib.reload(importlib.import_module("plugin.dispatcher"))
        self.retriever = importlib.reload(importlib.import_module("plugin.retriever"))
        self.registry = importlib.reload(importlib.import_module("plugin.registry"))
        self.events = importlib.reload(importlib.import_module("plugin.event_store"))
        self.protocol._store = self.protocol.InterventionStore()
        try:
            self.events.EVENT_LOG.unlink()
        except FileNotFoundError:
            pass

    def tearDown(self):
        for key in ["CAPABILITY_REUSE_MODE", "CAPABILITY_REUSE_ACTIVE_CAPABILITIES", "CAPABILITY_REUSE_PERMISSIONS", "CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"]:
            os.environ.pop(key, None)

    def _events(self, event_type):
        if not self.events.EVENT_LOG.exists():
            return []
        return [json.loads(line) for line in self.events.EVENT_LOG.read_text().splitlines() if line.strip() and json.loads(line).get("event_type") == event_type]

    def _open_intervention(self, iid="int_review", session="sess-review", turn="turn-review"):
        self.protocol._store.create_intervention(iid, "ep-review", "hmp-healthcheck", "1.0.0", session_id=session, turn_id=turn)
        return iid

    def test_second_decision_capable_execute_code_in_same_turn_is_rejected_after_bypass(self):
        iid = self._open_intervention()
        bypass = {
            "intervention_id": iid,
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "reason_code": "missing_feature",
            "proposed_feature_slug": "needs-custom-report",
            "detail": "capability does not provide requested report shape",
        }
        first = self.protocol.authorize_execute_code(
            {"code": "print('first')", "capability_reuse_bypass": bypass},
            "task-first",
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-first"},
        )
        self.assertTrue(first.allowed, first.message)
        second = self.protocol.authorize_execute_code(
            {"code": "print('second')"},
            "task-second",
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-second"},
        )
        self.assertFalse(second.allowed)
        self.assertIn("already consumed", second.message)

    def test_clean_fallback_requires_structured_harness_failure_bypass_not_token_only(self):
        iid = self._open_intervention("int_clean")
        old_dispatch = self.dispatcher.dispatch
        self.dispatcher.dispatch = lambda *a, **k: {"success": False, "error": "timeout", "output": None}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": iid,
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher.dispatch = old_dispatch
        token = result.get("fallback_authorization_id")
        self.assertTrue(token, result)
        token_only = self.protocol.authorize_execute_code(
            {"code": "print('fallback')", "capability_reuse_fallback_token": token},
            "task-token-only",
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-token-only"},
        )
        self.assertFalse(token_only.allowed)
        bypass = {
            "intervention_id": iid,
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "reason_code": "harness_failure",
            "prior_invocation_id": result.get("invocation_id"),
            "failure_code": "timeout",
            "fallback_authorization_id": token,
        }
        structured = self.protocol.authorize_execute_code(
            {"code": "print('fallback')", "capability_reuse_bypass": bypass},
            "task-structured",
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-structured"},
        )
        self.assertTrue(structured.allowed, structured.message)

    def test_protocol_blocked_execute_code_records_blocked_outcome_with_protocol_origin(self):
        self._open_intervention("int_block")
        verdict = self.protocol.authorize_execute_code(
            {"code": "print('blocked')"},
            "task-blocked",
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-blocked"},
        )
        self.assertFalse(verdict.allowed)
        self.protocol.record_tool_outcome(
            "execute_code",
            {"code": "print('blocked')"},
            {"action": "block", "message": verdict.message},
            "task-blocked",
            1.0,
            {"session_id": "sess-review", "episode_id": "ep-review", "turn_id": "turn-review", "tool_call_id": "tc-blocked"},
        )
        completed = self._events("execute_code_completed_event")[-1]["data"]
        self.assertEqual("blocked", completed["outcome"])
        self.assertEqual("protocol", completed["block_origin"])

    def test_all_v16_bypass_reason_codes_are_accepted_with_spec_fields(self):
        cases = [
            ("missing_feature", {"proposed_feature_slug": "json-lines-output"}),
            ("taxonomy_gap", {"proposed_feature_slug": "new-health-target-kind"}),
            ("incompatible_input", {"schema_path": "/properties/peer_list", "detail": "needs derived dynamic target"}),
            ("incompatible_output", {"schema_path": "/items/properties/status", "detail": "needs aggregate not rows"}),
            ("environment_constraint", {"constraint_id": "hmp_client_installed", "detail": "client missing in this environment"}),
        ]
        for idx, (reason, fields) in enumerate(cases, 1):
            iid = self._open_intervention("int_reason_%02d" % idx, session="sess-reason-%02d" % idx, turn="turn-reason")
            bypass = {"intervention_id": iid, "capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "reason_code": reason}
            bypass.update(fields)
            verdict = self.protocol.authorize_execute_code(
                {"code": "print('bypass')", "capability_reuse_bypass": bypass},
                "task-reason-%02d" % idx,
                {"session_id": "sess-reason-%02d" % idx, "episode_id": "ep-review", "turn_id": "turn-reason", "tool_call_id": "tc-reason-%02d" % idx},
            )
            self.assertTrue(verdict.allowed, "%s rejected: %s" % (reason, verdict.message))

    def test_invalid_dispatcher_output_is_contract_violation_not_resolved_success(self):
        iid = self._open_intervention("int_output")
        old_dispatch = self.dispatcher.dispatch
        self.dispatcher.dispatch = lambda *a, **k: {"success": True, "error": None, "output": {"not": "the required array"}}
        try:
            result = self.protocol.invoke_capability({
                "intervention_id": iid,
                "capability_id": "hmp-healthcheck",
                "capability_version": "1.0.0",
                "inputs": {"peer_list": ["peer70"], "timeout_seconds": 1},
            })
        finally:
            self.dispatcher.dispatch = old_dispatch
        self.assertFalse(result["success"])
        self.assertEqual("output_contract_violation", result["error"])
        self.assertNotEqual("resolved_success", self.protocol._store.get_intervention(iid)["state"])

    def test_actual_retriever_blocks_non_operational_and_mutating_composite_health_prompts(self):
        prompts = [
            "do not check HMP health for peer128",
            "what is the HMP health endpoint?",
            "generate Python code to check HMP health for peer128",
            "check HMP health and restart peer128 if unhealthy",
        ]
        for prompt in prompts:
            result = self.retriever.retrieve(
                session_id="sess-retriever-negative",
                user_message=prompt,
                hook_context={"session_id": "sess-retriever-negative", "episode_id": "ep-retriever-negative"},
                available_permissions=["hmp.network.read"],
                available_capabilities=["hmp_client_installed"],
                intervention_threshold=0.65,
                minimum_margin=0.10,
                shadow_mode=False,
            )
            self.assertTrue(result is None or not result.intervened, "%r incorrectly intervened: %r" % (prompt, result))

    def test_cleanup_and_next_retrieval_clear_missing_turn_tombstones(self):
        iid = self._open_intervention("int_missing_turn", session="sess-missing-turn", turn="")
        bypass = {
            "intervention_id": iid,
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "reason_code": "missing_feature",
            "proposed_feature_slug": "needs-custom-report",
        }
        first = self.protocol.authorize_execute_code(
            {"code": "print('first')", "capability_reuse_bypass": bypass},
            "task-missing-turn-first",
            {"session_id": "sess-missing-turn", "episode_id": "ep-review", "tool_call_id": "tc-missing-turn-first"},
        )
        self.assertTrue(first.allowed, first.message)
        blocked = self.protocol.authorize_execute_code(
            {"code": "print('second')"},
            "task-missing-turn-second",
            {"session_id": "sess-missing-turn", "episode_id": "ep-review", "tool_call_id": "tc-missing-turn-second"},
        )
        self.assertFalse(blocked.allowed)
        self.assertIn("already consumed", blocked.message)

        self.protocol.cleanup_expired(max_age_seconds=0)
        after_cleanup = self.protocol.authorize_execute_code(
            {"code": "print('third')"},
            "task-missing-turn-third",
            {"session_id": "sess-missing-turn", "episode_id": "ep-review", "tool_call_id": "tc-missing-turn-third"},
        )
        self.assertTrue(after_cleanup.allowed, after_cleanup.message)

        iid2 = self._open_intervention("int_missing_turn_next", session="sess-next-turn", turn="")
        bypass["intervention_id"] = iid2
        consumed = self.protocol.authorize_execute_code(
            {"code": "print('turn1')", "capability_reuse_bypass": bypass},
            "task-next-turn-first",
            {"session_id": "sess-next-turn", "episode_id": "ep-review", "tool_call_id": "tc-next-turn-first"},
        )
        self.assertTrue(consumed.allowed, consumed.message)
        self.protocol.retrieve(session_id="sess-next-turn", user_message="ordinary next turn; no HMP health action", hook_context={"session_id": "sess-next-turn", "episode_id": "ep-review"})
        next_turn = self.protocol.authorize_execute_code(
            {"code": "print('turn2')"},
            "task-next-turn-second",
            {"session_id": "sess-next-turn", "episode_id": "ep-review", "tool_call_id": "tc-next-turn-second"},
        )
        self.assertTrue(next_turn.allowed, next_turn.message)

    def test_unknown_exact_contract_version_returns_none(self):
        self.assertIsNone(self.registry.get_contract("hmp-healthcheck", "9.9.9"))


if __name__ == "__main__":
    unittest.main()
