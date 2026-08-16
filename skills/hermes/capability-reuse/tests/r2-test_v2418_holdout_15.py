"""v2.5.0 spec point 15 — formal holdout eligibility (derived only).

Matrix over the 8 required conditions plus the traffic-class auto-exclusions:
plugin_version==2.6.0, correct deployment_id, correct artifact_hash, valid
provenance, allowed organic traffic, known requester, known processor,
schema==1.3, complete trace envelope. registry_sync/test/acceptance/calibration
traffic automatically evaluate to false.
"""
from __future__ import annotations
import importlib, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

review_queue = importlib.import_module("plugin.review_queue")


def valid_event():
    event = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
    data = {
        "plugin_version": "2.6.0",
        "deployment_id": "dep-v2418-live",
        "plugin_artifact_hash": "sha256:c861593ebcc3bcf68d11415d45b5075d",
        "cohort_label": "v2.5.0_live",
        "deployment_timestamp": "2026-08-16T10:08:44Z",
        "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.capability_reuse_provenance"},
        "traffic_type": "organic_peer",
        "requester_peer_id": "peer58",
        "trace_id": "trace-v2418-peer58",
        "producer_surface": "hmp_ingress",
    }
    requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer106"}
    return event, data, requester


class V2418HoldoutMatrixTests(unittest.TestCase):
    def test_valid_event_is_eligible(self):
        ok, reasons = review_queue.formal_holdout_validation(*valid_event())
        self.assertTrue(ok, reasons)

    def test_matrix_eight_conditions(self):
        cases = [
            ("schema_version_not_1_3", lambda e, d, r: e.update({"schema_version": "1.2"})),
            ("plugin_version_not_2_6_0", lambda e, d, r: d.update({"plugin_version": "2.4.16"})),
            ("missing_deployment_id", lambda e, d, r: d.pop("deployment_id")),
            ("missing_or_placeholder_artifact_hash", lambda e, d, r: d.update({"plugin_artifact_hash": "placeholder-hash"})),
            ("wrong_cohort_label", lambda e, d, r: d.update({"cohort_label": "v2.4.16_peer58_peer106"})),
            ("not_organic_live_provenance", lambda e, d, r: d.update({"provenance": {"stream": "operator_seeded", "valid": False}})),
            ("non_organic_traffic_type", lambda e, d, r: d.update({"traffic_type": "unknown"})),
            ("unknown_requester", lambda e, d, r: r.update({"requester_type": "unknown"})),
            ("missing_processing_peer_id", lambda e, d, r: (r.update({"processing_peer_id": ""}), d.update({"peer_id": ""}))),
            ("missing_requester_peer_id", lambda e, d, r: d.pop("requester_peer_id")),
            ("missing_trace_id", lambda e, d, r: d.pop("trace_id")),
            ("missing_producer_surface", lambda e, d, r: d.update({"producer_surface": ""})),
        ]
        for reason, tamper in cases:
            with self.subTest(reason=reason):
                e, d, r = valid_event()
                tamper(e, d, r)
                ok, reasons = review_queue.formal_holdout_validation(e, d, r)
                self.assertFalse(ok)
                self.assertIn(reason, reasons, f"expected {reason} in {reasons}")

    def test_excluded_traffic_classes_auto_false(self):
        for traffic in ("registry_sync", "test", "acceptance", "calibration", "cron", "retry"):
            with self.subTest(traffic=traffic):
                e, d, r = valid_event()
                d["traffic_type"] = traffic
                ok, reasons = review_queue.formal_holdout_validation(e, d, r)
                self.assertFalse(ok)
                self.assertIn("non_organic_traffic_type", reasons)
                self.assertIn("excluded_traffic_class", reasons)

    def test_scheduled_protocol_is_not_organic(self):
        e, d, r = valid_event()
        d["traffic_type"] = "scheduled_protocol"
        ok, reasons = review_queue.formal_holdout_validation(e, d, r)
        self.assertFalse(ok)
        self.assertIn("non_organic_traffic_type", reasons)


if __name__ == "__main__":
    unittest.main()
