"""v2.5.0 spec points 13 & 14 — analyzer integration tests (peer70).

- P13: consumers reject stale analyzer reports automatically (fingerprint
       hash mismatch, time range excluding the latest event).
- P14: cohort-specific analyzer filtering (--plugin-version / --deployment-id
       / --exclude-traffic) with included/excluded breakdowns, without
       deleting legacy data.
"""
from __future__ import annotations
import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "batch-reuse-analyzer.py"
spec = importlib.util.spec_from_file_location("batch_reuse_analyzer", str(SCRIPT))
analyzer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(analyzer)

ARTIFACT_HASH = "c861593ebcc3bcf68d11415d45b5075df0cf1f399f0092fd5b635c9572c7e36b"


def row(dep="dep-v2418-1", ver="2.5.0", schema="1.3", traffic="organic_peer", ts="2026-08-14T10:00:00Z"):
    payload = {
        "deployment_id": dep, "plugin_version": ver, "plugin_artifact_hash": ARTIFACT_HASH,
        "schema_version": schema, "traffic_type": traffic,
        "producer": {"component": "capability_reuse_plugin", "version": "2.5.0", "surface": "hmp_ingress"},
    }
    event = {"event_id": "evt-%s" % (dep + ver + traffic), "event_type": "retrieval_event",
             "schema_version": schema, "timestamp": ts, "data": payload}
    return event, payload, "retrieval_event", __import__("datetime").datetime.fromisoformat(ts.replace("Z", "+00:00"))


class V2418AnalyzerCohortFilterTests(unittest.TestCase):
    def test_real_emit_enters_v2418_cohort_schema_13(self):
        """B2 regression: a REAL emitted retrieval event (through
        event_store.emit + v244_metadata enrichment) must carry inner
        schema_version == outer == 1.3 and pass cohort_filter(schema=1.3).

        This reproduces the reviewer blocker: v244_metadata.SCHEMA_VERSION
        was 1.2, so real events had outer 1.3 / inner 1.2 and the analyzer
        classified genuine v2.5.0 events as legacy.
        """
        import importlib.util as _ilu
        plugin_dir = SKILL_DIR / "plugin"
        es_spec = _ilu.spec_from_file_location("event_store", str(plugin_dir / "event_store.py"))
        es = _ilu.module_from_spec(es_spec)
        assert es_spec.loader is not None
        es_spec.loader.exec_module(es)

        with tempfile.TemporaryDirectory() as td:
            es._ensure_dir = lambda: None
            es.EVENT_LOG = str(Path(td) / "events.jsonl")
            es._CHAIN_CONTEXT_BY_INTERVENTION.clear()

            # The enrichment reads cohort.json for deployment/artifact fields;
            # a REAL deployment has it, so create one to reproduce the live
            # path (without it events are correctly "uncohortable").
            cohort_dir = Path.home() / ".hermes" / "data" / "reuse-observer"
            cohort_dir.mkdir(parents=True, exist_ok=True)
            cohort_path = cohort_dir / "cohort.json"
            cohort_backup = cohort_path.read_text() if cohort_path.exists() else None
            cohort_path.write_text(json.dumps({
                "deployment_id": "dep-v2418-b2",
                "deployment_timestamp": "2026-08-14T10:00:00Z",
                "plugin_version": "2.5.0",
                "plugin_artifact_hash": ARTIFACT_HASH,
                "schema_version": "1.3",
                "cohort_label": "v2.5.0_live",
            }))
            try:
                eid = es.emit("retrieval_event", {
                    "session_id": "sess-b2", "trace_id": "trace-b2",
                    "plugin_version": "2.5.0",
                    "deployment_id": "dep-v2418-b2",
                    "cohort_label": "v2.5.0_live",
                    "traffic_type": "organic_peer",
                    "requester_peer_id": "peer106",
                    "processing_peer_id": "peer70",
                }, context={"trace_id": "trace-b2"})
            finally:
                if cohort_backup is None:
                    cohort_path.unlink(missing_ok=True)
                else:
                    cohort_path.write_text(cohort_backup)
            self.assertIsNotNone(eid)

            raw = Path(es.EVENT_LOG).read_text()
            ev = json.loads(raw.splitlines()[-1])
            # outer schema from event_store
            self.assertEqual("1.3", ev.get("schema_version"))
            # inner schema from v244_metadata enrichment (the B2 fix)
            self.assertEqual("1.3", ev["data"].get("schema_version"),
                             "inner schema_version must be 1.3 (v244_metadata)")

            rows = [(
                ev, ev["data"], ev["event_type"],
                __import__("datetime").datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")),
            )]
            clean, legacy, _, _, _ = analyzer.cohort_filter(
                rows, "2.5.0", "dep-v2418-b2", ARTIFACT_HASH, "1.3")
            self.assertEqual(1, len(clean), "real v2.5.0 event must be clean")
            self.assertEqual(0, len(legacy))

    def test_cohort_filter_partitions_and_breakdowns(self):
        rows = [
            row(dep="dep-v2418-1"),
            row(dep="dep-v2418-1", ver="2.4.6"),        # legacy version
            row(dep="dep-v2414-x", ver="2.5.0"),       # legacy deployment
            row(dep="dep-v2418-1", schema="1.2"),       # legacy schema
            row(dep="dep-v2418-1", traffic="registry_sync"),  # traffic legacy
        ]
        clean, legacy, by_ver, by_traffic, by_producer = analyzer.cohort_filter(
            rows, "2.5.0", "dep-v2418-1", ARTIFACT_HASH, "1.3")
        # clean = base + registry_sync (no traffic exclusion here); legacy =
        # wrong version + wrong deployment + wrong schema.
        self.assertEqual(2, len(clean))
        self.assertEqual(3, len(legacy))
        self.assertEqual(1, by_ver.get("2.4.6"))
        self.assertIsNone(by_traffic.get("registry_sync"))
        self.assertIn("hmp_ingress", by_producer)

    def test_exclude_traffic_moves_clean_event_to_legacy(self):
        rows = [row(traffic="registry_sync"), row()]
        clean, legacy, _, by_traffic, _ = analyzer.cohort_filter(
            rows, "2.5.0", "dep-v2418-1", ARTIFACT_HASH, "1.3",
            excluded_traffic=["registry_sync"])
        self.assertEqual(1, len(clean))
        self.assertEqual(1, len(legacy))
        self.assertEqual(1, by_traffic.get("registry_sync"))

    def test_plugin_version_and_deployment_filters_default_to_cohort(self):
        rows = [row(dep="dep-v2418-1"), row(dep="dep-v2418-2", ver="2.4.16")]
        clean, legacy, _, _, _ = analyzer.cohort_filter(
            rows, "2.5.0", "dep-v2418-1", ARTIFACT_HASH, "1.3")
        self.assertEqual(1, len(clean))
        self.assertEqual("dep-v2418-1", clean[0][1]["deployment_id"])


class V2418AnalyzerReportValidationTests(unittest.TestCase):
    def _write_log(self, ts_lines):
        p = Path(self._tmp.name) / "events.jsonl"
        p.write_text("".join(json.dumps({"event_id": "e%d" % i, "event_type": "retrieval_event",
                                         "schema_version": "1.3", "timestamp": t,
                                         "data": {}}) + "\n"
                        for i, t in enumerate(ts_lines)))
        return p

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _report(self, path, min_ts="2026-08-14T10:00:00Z", max_ts="2026-08-14T10:01:00Z",
                hash_override=None):
        fp = hash_override if hash_override is not None else hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "input_event_log_sha256": fp,
            "input_event_count": 2,
            "input_min_timestamp": min_ts,
            "input_max_timestamp": max_ts,
            "analyzer_version": "2.5.0",
            "generated_at": "2026-08-14T10:05:00Z",
        }

    def test_fresh_report_accepted(self):
        path = self._write_log(["2026-08-14T10:00:00Z", "2026-08-14T10:01:00Z"])
        ok, reasons = analyzer.validate_report(self._report(path), path)
        self.assertTrue(ok, reasons)

    def test_stale_hash_rejected(self):
        path = self._write_log(["2026-08-14T10:00:00Z", "2026-08-14T10:01:00Z"])
        ok, reasons = analyzer.validate_report(self._report(path, hash_override="0" * 64), path)
        self.assertFalse(ok)
        self.assertIn("event_log_hash_mismatch", reasons)

    def test_range_excluding_latest_event_rejected(self):
        path = self._write_log(["2026-08-14T10:00:00Z", "2026-08-14T11:00:00Z"])
        ok, reasons = analyzer.validate_report(
            self._report(path, min_ts="2026-08-14T09:59:00Z", max_ts="2026-08-14T10:01:00Z"), path)
        self.assertFalse(ok)
        self.assertIn("range_excludes_latest_event", reasons)

    def test_missing_fingerprint_fields_rejected(self):
        path = self._write_log(["2026-08-14T10:00:00Z"])
        ok, reasons = analyzer.validate_report({}, path)
        self.assertFalse(ok)
        for r in ("missing_input_fingerprint", "missing_input_event_count",
                  "missing_analyzer_version", "missing_generated_at", "missing_input_time_range"):
            self.assertIn(r, reasons)

    def test_inverted_time_range_rejected(self):
        path = self._write_log(["2026-08-14T10:00:00Z"])
        ok, reasons = analyzer.validate_report(
            self._report(path, min_ts="2026-08-14T11:00:00Z", max_ts="2026-08-14T10:00:00Z"), path)
        self.assertFalse(ok)
        self.assertIn("inverted_time_range", reasons)


if __name__ == "__main__":
    unittest.main()
