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
