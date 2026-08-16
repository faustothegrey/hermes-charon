"""v2.5.0 spec points 5, 6, 8, 9 — unit tests (peer70).

- P5: explicit retrieval semantics (retrieval/coverage/eligibility stages;
      never default booleans that imply a successful evaluation).
- P6: prove the retriever ran (retriever_executed + version + threshold +
      margin + candidates); observer-only never fakes a zero-score retrieval.
- P8: full traffic taxonomy (organic_user, organic_peer, scheduled_protocol,
      registry_sync, cron, retry, test, acceptance, calibration, unknown).
- P9: requester/processor/target/collector separation (no overloading of
      processing_peer_id with the telemetry collector).
"""
from __future__ import annotations
import importlib, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plugin.event_store as events
import plugin.retriever as retriever


class V2418Points5689Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_log = events.EVENT_LOG
        events.EVENT_LOG = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self):
        events.EVENT_LOG = self._orig_log
        self._tmp.cleanup()

    def _events(self):
        if not events.EVENT_LOG.exists():
            return []
        return [json.loads(l) for l in events.EVENT_LOG.read_text().splitlines() if l.strip()]

    def _retrieval_event(self):
        evs = [e for e in self._events() if e["event_type"] == "retrieval_event"]
        self.assertTrue(evs, "no retrieval_event emitted")
        return evs[-1]

    # ── P5: explicit retrieval semantics ──────────────────────────────

    def test_real_retrieval_emits_evaluated_stages(self):
        result = retriever.retrieve(
            session_id="p5-session",
            user_message="check HMP health for peer128",
            hook_context={"platform": "hmp", "sender_id": "peer106",
                          "traffic_type": "organic_peer"},
            shadow_mode=True,
        )
        self.assertIsNotNone(result)
        ev = self._retrieval_event()
        d = ev["data"]
        stages = d["retrieval_stages"]
        self.assertIs(True, stages["retrieval"]["executed"])
        self.assertGreaterEqual(stages["retrieval"]["candidate_count"], 1)
        self.assertIs(True, stages["coverage"]["evaluated"])
        self.assertIsInstance(stages["coverage"]["whole_request_covered"], bool)
        self.assertIs(True, stages["eligibility"]["evaluated"])
        # shadow mode → eligible False (not None, not a success claim)
        self.assertIs(False, stages["eligibility"]["eligible"])

    def test_observer_event_never_fakes_evaluation(self):
        # Observer path (e.g. HMP adapter): retriever did NOT run, zero
        # candidates. Must NOT produce the v2.4.16 "impossible" combo
        # (candidate_count=0, top_score=0, whole_request_covered=true).
        events.emit_retrieval(
            session_id="obs-session", user_message_preview="REGISTRY_PUBLISH ...",
            candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
            traffic_type="registry_sync", retriever_executed=False,
            whole_request_covered=None, eligibility="",
        )
        ev = self._retrieval_event()
        d = ev["data"]
        self.assertIsNone(d["whole_request_covered"])
        self.assertIs(False, d["retriever_executed"])
        stages = d["retrieval_stages"]
        self.assertIs(False, stages["retrieval"]["executed"])
        self.assertEqual(0, stages["retrieval"]["candidate_count"])
        self.assertIs(False, stages["coverage"]["evaluated"])
        self.assertIsNone(stages["coverage"]["whole_request_covered"])
        self.assertIs(False, stages["eligibility"]["evaluated"])
        self.assertIsNone(stages["eligibility"]["eligible"])

    def test_zero_candidates_after_real_retrieval_is_not_applicable(self):
        events.emit_retrieval(
            session_id="nc-session", user_message_preview="no match",
            candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
            retriever_executed=True, eligibility="rejected",
        )
        ev = self._retrieval_event()
        self.assertEqual("not_applicable", ev["data"]["retrieval_stages"]["eligibility"]["eligible"])

    def test_no_fake_event_when_retrieval_finds_nothing(self):
        with mock.patch.object(retriever.reg, "list_capabilities", return_value=[]):
            result = retriever.retrieve(
                session_id="empty-reg", user_message="check HMP health for peer128",
                hook_context={}, shadow_mode=True,
            )
        self.assertIsNone(result)
        self.assertEqual([], self._events(), "no event may be emitted when the retriever did not run")

    # ── P6: prove the retriever ran ───────────────────────────────────

    def test_retrieval_event_carries_retriever_proof(self):
        retriever.retrieve(
            session_id="p6-session",
            user_message="check HMP health for peer128",
            hook_context={"platform": "hmp", "sender_id": "peer106"},
            shadow_mode=True,
        )
        d = self._retrieval_event()["data"]
        self.assertIs(True, d["retriever_executed"])
        self.assertEqual("2.6.0", d["retriever_version"])
        self.assertTrue(d["registry_version"], "registry_version must be present")
        self.assertIsInstance(d["retrieval_threshold"], (int, float))
        self.assertGreaterEqual(d["candidate_count"], 1)
        self.assertEqual(d["candidate_count"], len(d["candidates"]))
        self.assertIsInstance(d["score_margin"], (int, float))
        self.assertIsInstance(d["filter_rejection_reasons"], list)
        top = d["candidates"][0]
        for key in ("capability_id", "capability_version", "score", "eligible_for_intervention"):
            self.assertIn(key, top, f"candidate missing {key}")

    # ── P8: traffic taxonomy ──────────────────────────────────────────

    def test_taxonomy_all_ten_categories(self):
        cases = [
            # P0-3 fail-closed: organic_user declared without a supporting
            # channel/identity is NOT classifiable as organic.
            ({"traffic_type": "organic_user", "platform": "telegram", "user_id": "u1"}, "", "organic_user"),
            ({"platform": "hmp", "sender_id": "peer106"}, "", "organic_peer"),
            ({"platform": "telegram", "user_id": "u1"}, "", "organic_user"),
            ({"is_scheduled": True}, "", "scheduled_protocol"),
            ({"is_registry_sync": True}, "", "registry_sync"),
            ({"protocol_type": "REGISTRY_PUBLISH"}, "", "registry_sync"),
            ({}, "REGISTRY_PUBLISH {\"peer\": \"peer141\"}", "registry_sync"),
            ({}, "registry sync?", "registry_sync"),
            ({"is_cron": True}, "", "cron"),
            ({"retry_of": "task-1"}, "", "retry"),
            ({"is_test": True}, "", "test"),
            ({"acceptance_test": True}, "", "acceptance"),
            ({"is_calibration": True}, "", "calibration"),
            ({}, "", "unknown"),
        ]
        for ctx, msg, expected in cases:
            with self.subTest(ctx=ctx, msg=msg[:30]):
                self.assertEqual(expected, retriever._extract_traffic_type(ctx, msg))

    def test_registry_sync_is_not_organic(self):
        self.assertEqual("registry_sync", retriever._extract_traffic_type(
            {"platform": "hmp", "sender_id": "peer141"}, "REGISTRY_PUBLISH {...}"))

    # ── P9: requester/processor/target/collector separation ───────────

    def test_collector_peer_never_overloads_processing_peer(self):
        events.emit_retrieval(
            session_id="p9-session", user_message_preview="check health peer58",
            candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
            requester={"actor_type": "agent", "actor_id": "hmp:peer58",
                       "request_channel": "hmp", "requester_peer_id": "peer58",
                       "processing_peer_id": "peer106"},
            requester_peer_id="peer58", processing_peer_id="peer106",
            target_peer_id="peer58", collector_peer_id="peer70",
            trace_id="trace-p9", traffic_type="organic_peer",
            retriever_executed=False, whole_request_covered=None,
        )
        d = self._retrieval_event()["data"]
        self.assertEqual("peer58", d["requester_peer_id"])
        self.assertEqual("peer106", d["processing_peer_id"])
        self.assertEqual("peer58", d["target_peer_id"])
        self.assertEqual("peer70", d["collector_peer_id"])
        self.assertNotEqual(d["processing_peer_id"], d["collector_peer_id"],
                            "collector must not overload processing_peer_id")
        self.assertEqual("trace-p9", d["trace_id"])
        # envelope keys propagated
        for k in ("trace_id", "session_id", "requester_peer_id", "processing_peer_id",
                  "target_peer_id", "collector_peer_id", "traffic_type"):
            self.assertIn(k, d)

    # ── P9 propagation from real call sites (peer141, 2026-08-16) ─────

    def test_retriever_call_site_propagates_collector_from_context(self):
        """retriever.retrieve() must pass collector_peer_id through to the
        emitted event when the hook context provides it (was dropped)."""
        result = retriever.retrieve(
            session_id="p9-prop-session",
            user_message="check HMP health for peer70",
            hook_context={
                "session_id": "p9-prop-session",
                "requester_peer_id": "peer141",
                "processing_peer_id": "peer70",
                "collector_peer_id": "peer70",
                "request_channel": "hmp",
            },
        )
        d = self._retrieval_event()["data"]
        self.assertEqual("peer70", d["collector_peer_id"])
        self.assertEqual("peer70", d["processing_peer_id"])
        self.assertEqual("peer141", d["requester_peer_id"])
        self.assertEqual("peer70", d["target_peer_id"],
                         "health target is the processed peer")

    def test_retriever_call_site_collector_from_env(self):
        """When hook context has no collector, env
        CAPABILITY_REUSE_COLLECTOR_PEER_ID is used (was empty)."""
        with mock.patch.dict(os.environ,
                             {"CAPABILITY_REUSE_COLLECTOR_PEER_ID": "peer70"},
                             clear=False):
            retriever.retrieve(
                session_id="p9-env-session",
                user_message="check HMP health for peer141",
                hook_context={
                    "session_id": "p9-env-session",
                    "requester_peer_id": "peer58",
                    "processing_peer_id": "peer141",
                    "request_channel": "hmp",
                },
            )
        d = self._retrieval_event()["data"]
        self.assertEqual("peer70", d["collector_peer_id"])
        self.assertEqual("peer141", d["processing_peer_id"])
        self.assertNotEqual(d["processing_peer_id"], d["collector_peer_id"],
                            "collector must not overload processing_peer_id")

    def test_retriever_call_site_collector_unknown_when_absent(self):
        """No collector anywhere → empty string, never invented (fail-open)."""
        with mock.patch.dict(os.environ, {}, clear=True):
            retriever.retrieve(
                session_id="p9-none-session",
                user_message="check HMP health for peer141",
                hook_context={
                    "session_id": "p9-none-session",
                    "request_channel": "hmp",
                },
            )
        d = self._retrieval_event()["data"]
        self.assertEqual("", d["collector_peer_id"])
        self.assertIn("collector_peer_id", d,
                      "envelope key must always be present")

    # ── P2/P4 (aligned with 5-9): surface identity + top-level trace_id ─

    def test_trace_id_is_top_level_in_event_envelope(self):
        events.emit_retrieval(
            session_id="p4-session", user_message_preview="check health peer128",
            candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
            trace_id="trace-p4", retriever_executed=False,
        )
        ev = self._retrieval_event()
        self.assertEqual("trace-p4", ev["trace_id"], "spec 4: top-level trace_id")
        self.assertEqual("trace-p4", ev["data"]["trace_id"])

    def test_hook_surface_stamped_via_thread_local(self):
        events.push_surface("gateway")
        try:
            events.emit_retrieval(
                session_id="p2-session", user_message_preview="check health peer128",
                candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
                retriever_executed=False,
            )
        finally:
            events.pop_surface()
        self.assertEqual("gateway", self._retrieval_event()["data"]["producer"]["surface"])

    def test_execute_code_hook_surface(self):
        events.push_surface("execute_code_hook")
        try:
            events.emit_retrieval(
                session_id="p2-ec-session", user_message_preview="run",
                candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
                retriever_executed=False,
            )
        finally:
            events.pop_surface()
        self.assertEqual("execute_code_hook", self._retrieval_event()["data"]["producer"]["surface"])

    def test_explicit_surface_beats_thread_local(self):
        events.push_surface("gateway")
        try:
            events.emit_retrieval(
                session_id="p2-exp-session", user_message_preview="x",
                candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
                producer_surface="hmp_ingress", retriever_executed=False,
            )
        finally:
            events.pop_surface()
        self.assertEqual("hmp_ingress", self._retrieval_event()["data"]["producer"]["surface"])


if __name__ == "__main__":
    unittest.main()
