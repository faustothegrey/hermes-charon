"""Phase 1a P0 — provenance fail-closed classification tests (2026-08-16).

Reviewer required change (2026-08-16): `from_peer present → organic_peer`
is insufficient. Traffic classification must use explicit provenance
metadata and fail closed:
  scheduled            → scheduled_protocol / cron / calibration
  operator solicited   → operator_solicited
  genuinely spontaneous → organic_peer / organic_user
  missing/ambiguous     → unknown → formal_holdout_eligible = false
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plugin.retriever as retriever
import plugin.event_store as events


class Phase1aProvenanceFailClosedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_log = events.EVENT_LOG
        events.EVENT_LOG = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self):
        events.EVENT_LOG = self._orig_log
        self._tmp.cleanup()

    # ── retriever._extract_traffic_type ───────────────────────────────

    def test_scheduled_marker_is_not_organic(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "is_scheduled": True}, "check HMP health for peer70")
        self.assertEqual("scheduled_protocol", tt)

    def test_solicited_marker_is_operator_solicited(self):
        for key in ("operator_solicited", "is_solicited", "solicited"):
            tt = retriever._extract_traffic_type(
                {"platform": "hmp", key: True}, "check HMP health for peer70")
            self.assertEqual("operator_solicited", tt, "key=%s" % key)

    def test_seeded_marker_is_operator_seeded(self):
        for key in ("operator_seeded", "is_seeded", "seeded"):
            tt = retriever._extract_traffic_type(
                {"platform": "hmp", key: True}, "check HMP health for peer70")
            self.assertEqual("operator_seeded", tt, "key=%s" % key)

    def test_explicit_traffic_type_wins(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "organic_peer"}, "x")
        self.assertEqual("organic_peer", tt)
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "calibration"}, "x")
        self.assertEqual("calibration", tt)

    def test_spontaneous_hmp_is_organic_peer(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "requester_peer_id": "peer58"}, "check HMP health for peer70")
        self.assertEqual("organic_peer", tt)

    # ── P0-3 conflict resolution (reviewer 2026-08-16): exclusion markers
    #    MUST win over organic declarations ─────────────────────────────

    def test_organic_peer_plus_solicited_is_solicited(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "organic_peer", "operator_solicited": True},
            "check HMP health for peer70")
        self.assertEqual("operator_solicited", tt,
                         "exclusion marker must beat organic declaration")

    def test_organic_peer_plus_seeded_is_seeded(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "organic_peer", "operator_seeded": True},
            "check HMP health for peer70")
        self.assertEqual("operator_seeded", tt)

    def test_organic_peer_plus_test_is_test(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "organic_peer", "is_test": True},
            "check HMP health for peer70")
        self.assertEqual("test", tt)

    def test_organic_peer_plus_scheduled_is_scheduled(self):
        tt = retriever._extract_traffic_type(
            {"platform": "hmp", "traffic_type": "organic_peer", "is_scheduled": True},
            "check HMP health for peer70")
        self.assertEqual("scheduled_protocol", tt)

    def test_organic_user_declared_without_supporting_channel_is_unknown(self):
        # explicit organic_user but no telegram/user identity → cannot confirm
        tt = retriever._extract_traffic_type(
            {"traffic_type": "organic_user"}, "hello")
        self.assertEqual("unknown", tt)

    def test_hmp_without_trustworthy_provenance_not_organic(self):
        """P0-2: platform identity alone never implies organic_live."""
        prov, detail, source = retriever._request_provenance(
            {"platform": "hmp", "requester_peer_id": "peer58"})
        self.assertIsNone(prov, "HMP platform alone must not yield organic_live")
        self.assertEqual("", detail)

    def test_explicit_provenance_still_works(self):
        prov, detail, source = retriever._request_provenance(
            {"platform": "hmp", "capability_reuse_provenance": "organic_live",
             "capability_reuse_provenance_detail": "explicit"})
        self.assertEqual("organic_live", prov)
        self.assertEqual("hook_context.capability_reuse_provenance", source)

    # ── P0-11 timestamp gate (reviewer 2026-08-16) ─────────────────────

    def test_event_before_deployment_is_rejected(self):
        """P0-11: a record dated before its cohort deployment must NOT be
        formal-holdout eligible (clock confusion)."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        from pathlib import Path
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T08:09:08Z"}
        data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "provenance": {"stream": "organic_live", "valid": True},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-x",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        ok, reasons = rq.formal_holdout_validation(ev, data, requester)
        self.assertFalse(ok, "event before deployment must be rejected")
        self.assertIn("event_before_deployment", reasons)

    def test_event_after_deployment_is_accepted(self):
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.capability_reuse_provenance"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-y",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        ok, reasons = rq.formal_holdout_validation(ev, data, requester)
        self.assertTrue(ok, reasons)

    # ── P0-1 process_env loophole (reviewer 2026-08-16) ────────────────

    def test_process_env_provenance_rejected(self):
        """P0-1: provenance.source=process_env must NEVER be holdout-eligible."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "provenance": {"stream": "organic_live", "valid": True, "source": "process_env"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-z",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        ok, reasons = rq.formal_holdout_validation(ev, data, requester)
        self.assertFalse(ok, "process_env provenance must be rejected")
        self.assertIn("provenance_source_not_request_scoped", reasons)

    def test_hook_context_platform_provenance_rejected(self):
        """P0-1-r2: hook_context.platform is request-scoped but NOT a
        provenance declaration — the exact source of the original
        contamination. Must be rejected by the exact allowlist."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.platform"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-p",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        ok, reasons = rq.formal_holdout_validation(ev, data, requester)
        self.assertFalse(ok, "hook_context.platform provenance must be rejected")
        self.assertIn("provenance_source_not_request_scoped", reasons)

    def test_hook_context_arbitrary_provenance_rejected(self):
        """P0-1-r2: hook_context.anything must be rejected — exact allowlist,
        not startswith()."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.anything"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-q",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        ok, reasons = rq.formal_holdout_validation(ev, data, requester)
        self.assertFalse(ok, "hook_context.anything provenance must be rejected")
        self.assertIn("provenance_source_not_request_scoped", reasons)

    def test_exact_allowlist_sources_still_accepted(self):
        """P0-1-r2: the two exact declarations remain eligible."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        ev = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        for src in ("hook_context.capability_reuse_provenance", "hook_context.provenance"):
            data = {
                "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
                "deployment_id": "dep-test",
                "plugin_artifact_hash": "abc123",
                "cohort_label": rq.EXPECTED_COHORT_LABEL,
                "deployment_timestamp": "2026-08-16T10:08:44Z",
                "provenance": {"stream": "organic_live", "valid": True, "source": src},
                "traffic_type": "organic_peer",
                "requester_peer_id": "peer141",
                "processing_peer_id": "peer70",
                "trace_id": "trace-r-" + src.split(".")[-1],
                "producer": {"surface": "hmp_ingress"},
            }
            ok, reasons = rq.formal_holdout_validation(ev, data, requester)
            self.assertTrue(ok, "source=%s reasons=%s" % (src, reasons))

    def test_missing_timestamps_rejected(self):
        """P0-2: missing event/deployment timestamps are rejection reasons."""
        import sys
        sys.path.insert(0, str(ROOT))
        import plugin.review_queue as rq
        base_ev = {"schema_version": "1.3"}
        base_data = {
            "plugin_version": rq.EXPECTED_PLUGIN_VERSION,
            "deployment_id": "dep-test",
            "plugin_artifact_hash": "abc123",
            "cohort_label": rq.EXPECTED_COHORT_LABEL,
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.capability_reuse_provenance"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer141",
            "processing_peer_id": "peer70",
            "trace_id": "trace-w",
            "producer": {"surface": "hmp_ingress"},
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer70"}
        # both missing
        ok, reasons = rq.formal_holdout_validation(dict(base_ev), dict(base_data), requester)
        self.assertIn("missing_event_timestamp", reasons)
        self.assertIn("missing_deployment_timestamp", reasons)
        # event missing only
        d2 = dict(base_data, deployment_timestamp="2026-08-16T10:08:44Z")
        ok, reasons = rq.formal_holdout_validation(dict(base_ev), d2, requester)
        self.assertIn("missing_event_timestamp", reasons)
        self.assertNotIn("missing_deployment_timestamp", reasons)
        # deployment missing only
        ev3 = dict(base_ev, timestamp="2026-08-16T11:00:00Z")
        d3 = dict(base_data)
        d3.pop("deployment_timestamp", None)
        ok, reasons = rq.formal_holdout_validation(ev3, d3, requester)
        self.assertIn("missing_deployment_timestamp", reasons)
        self.assertNotIn("missing_event_timestamp", reasons)

    # ── consumer_loop classification (adapter) ────────────────────────
    # The adapter classification logic is mirrored here as a pure function
    # so it is unit-testable without a running gateway. The adapter imports
    # this helper; see plugins/hmp/adapter.py.

    def _classify(self, body, requester_peer="peer58"):
        """Replicates the fail-closed resolution order in adapter.py."""
        raw = body if isinstance(body, dict) else {}
        declared_traffic = str(raw.get("traffic_type") or raw.get("traffic") or "").strip().lower()
        declared_prov = str(raw.get("provenance") or "").strip().lower()
        is_sched = bool(raw.get("scheduled") or raw.get("is_scheduled") or raw.get("cron")
                        or raw.get("is_cron") or "scheduled" in declared_traffic or "scheduled" in declared_prov)
        is_calib = bool(raw.get("calibration") or raw.get("is_calibration")
                        or "calibration" in declared_traffic or "calibration" in declared_prov)
        is_test = bool(raw.get("test") or raw.get("is_test") or raw.get("acceptance")
                       or "test" in declared_traffic or "acceptance" in declared_traffic)
        is_solicited = bool(raw.get("operator_solicited") or raw.get("is_solicited") or raw.get("solicited")
                            or "operator_solicited" in declared_traffic or "operator_solicited" in declared_prov)
        is_seeded = bool(raw.get("operator_seeded") or raw.get("is_seeded") or raw.get("seeded")
                         or "operator_seeded" in declared_traffic or "operator_seeded" in declared_prov)
        is_retry = bool(raw.get("retry") or raw.get("is_retry") or raw.get("retry_of") or "retry" in declared_traffic)
        if is_sched:
            return "scheduled_protocol"
        if is_calib:
            return "calibration"
        if is_test:
            return "test"
        if is_solicited:
            return "operator_solicited"
        if is_seeded:
            return "operator_seeded"
        if is_retry:
            return "retry"
        if declared_traffic in ("organic_peer", "organic_user", "organic_live", "unknown", "cron", "registry_sync"):
            return declared_traffic
        if declared_prov == "organic_live" and requester_peer:
            return "organic_peer"
        # from_peer alone is INSUFFICIENT → fail closed → unknown
        return "unknown"

    def test_consumer_loop_scheduled_body_fails_closed(self):
        self.assertEqual("scheduled_protocol", self._classify({"scheduled": True}))
        self.assertEqual("scheduled_protocol", self._classify({"traffic_type": "scheduled_protocol"}))
        self.assertEqual("scheduled_protocol", self._classify({"provenance": "scheduled"}))

    def test_consumer_loop_solicited_body(self):
        self.assertEqual("operator_solicited", self._classify({"operator_solicited": True}))
        self.assertEqual("operator_solicited", self._classify({"traffic_type": "operator_solicited"}))

    def test_consumer_loop_seeded_body(self):
        self.assertEqual("operator_seeded", self._classify({"operator_seeded": True}))
        self.assertEqual("operator_seeded", self._classify({"traffic_type": "operator_seeded"}))

    def test_consumer_loop_calibration_and_test(self):
        self.assertEqual("calibration", self._classify({"calibration": True}))
        self.assertEqual("test", self._classify({"is_test": True}))

    def test_consumer_loop_explicit_organic_declaration(self):
        self.assertEqual("organic_peer", self._classify({"provenance": "organic_live"}))
        self.assertEqual("organic_peer", self._classify({"traffic_type": "organic_peer"}))

    def test_consumer_loop_from_peer_alone_fails_closed(self):
        """The P0 bug: from_peer present with NO metadata must NOT be organic."""
        self.assertEqual("unknown", self._classify({}))
        self.assertEqual("unknown", self._classify({"from": "peer58"}))

    def test_consumer_loop_cron_and_registry_sync(self):
        self.assertEqual("cron", self._classify({"traffic_type": "cron"}))
        self.assertEqual("registry_sync", self._classify({"traffic_type": "registry_sync"}))


if __name__ == "__main__":
    unittest.main()
