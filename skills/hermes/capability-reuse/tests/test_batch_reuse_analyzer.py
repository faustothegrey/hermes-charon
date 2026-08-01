import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / 'scripts' / 'batch-reuse-analyzer.py'
spec = importlib.util.spec_from_file_location('batch_reuse_analyzer', str(SCRIPT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BatchReuseAnalyzerTests(unittest.TestCase):
    def test_partial_trailing_jsonl_does_not_advance_cursor_past_bad_tail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / 'events.jsonl'
            cursor = root / 'cursor.json'
            good = {"event_type": "retrieval_event", "data": {"candidates": [], "shadow_mode": True}}
            events.write_bytes((json.dumps(good) + '\n{"event_type": ').encode('utf-8'))
            parsed, bad, new_cursor, size = mod.read_delta(events, cursor)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(bad, 1)
            self.assertEqual(new_cursor['offset'], len(json.dumps(good).encode('utf-8')) + 1)
            self.assertEqual(size, events.stat().st_size)

    def test_mixed_read_only_mutating_candidates_trigger_zero_tolerance_gate(self):
        stats = mod.initial_stats('peer-test', '2026-07-27T00:00:00Z')
        event = {
            "event_type": "retrieval_event",
            "data": {
                "shadow_mode": True,
                "top_score": 0.9,
                "candidates": [
                    {"capability_id": "readcap", "capability_version": "1.0.0", "score": 0.9, "effect_class": "read_only"},
                    {"capability_id": "writecap", "capability_version": "1.0.0", "score": 0.8, "effect_class": "mutating"},
                ],
            },
        }
        mod.add_event(stats, event, {})
        mod.finalize_stats(stats)
        self.assertEqual(stats['safety']['read_only_mutating_candidate_sets'], 1)
        self.assertIn('read_only_mutating_candidates_seen_together', stats['anomalies'])

    def test_hyphenated_read_only_variant_is_equivalent_for_gate(self):
        stats = mod.initial_stats('peer-test', '2026-07-27T00:00:00Z')
        event = {
            "event_type": "retrieval_event",
            "data": {
                "candidates": [
                    {"capability_id": "readcap", "effect_class": "read-only"},
                    {"capability_id": "writecap", "effect_class": "mutating"},
                ],
            },
        }
        mod.add_event(stats, event, {})
        self.assertEqual(stats['safety']['read_only_mutating_candidate_sets'], 1)

    def test_corrupt_cursor_and_negative_offsets_reset_to_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / 'events.jsonl'
            cursor = root / 'cursor.json'
            events.write_text(json.dumps({"event_type": "observation_event"}) + '\n')
            cursor.write_text('{"offset": "bad", "inode": %d}' % events.stat().st_ino)
            parsed, bad, new_cursor, _size = mod.read_delta(events, cursor)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(bad, 0)
            self.assertGreater(new_cursor['offset'], 0)

            cursor.write_text(json.dumps({"offset": -10, "inode": events.stat().st_ino}))
            parsed, bad, new_cursor, _size = mod.read_delta(events, cursor)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(bad, 0)
            self.assertGreater(new_cursor['offset'], 0)

    def test_peer_id_is_sanitized_before_run_filename(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / 'events.jsonl'
            outdir = root / 'out'
            cursor = outdir / 'cursor.json'
            events.write_text(json.dumps({"event_type": "observation_event"}) + '\n')
            mod.analyze(events, outdir, cursor, peer_id='../evil/peer', now='2026-07-27T00:00:00Z')
            runs = list((outdir / 'runs').glob('*.json'))
            self.assertEqual(len(runs), 1)
            self.assertTrue(str(runs[0]).startswith(str(outdir / 'runs')))
            self.assertIn('evil_peer', runs[0].name)

    def test_stale_lock_is_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / 'lock'
            lock.write_text('old')
            old = 1
            os.utime(str(lock), (old, old))
            fd = mod.acquire_lock(lock, stale_seconds=1)
            self.assertIsNotNone(fd)
            os.close(fd)

    def test_provenance_review_queue_and_rollups_are_written(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / 'events.jsonl'
            outdir = root / 'out'
            cursor = outdir / 'cursor.json'
            event = {
                "event_id": "evt-1",
                "event_type": "retrieval_event",
                "timestamp": "2026-07-30T00:00:00Z",
                "data": {
                    "session_id": "s1",
                    "user_message_preview": "[calibration_probe] check hmp health",
                    "provenance": {"stream": "calibration_probe"},
                    "shadow_mode": True,
                    "top_score": 0.91,
                    "candidates": [
                        {"capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "score": 0.91, "effect_class": "read_only"}
                    ],
                },
            }
            events.write_text(json.dumps(event) + '\n')
            stats = mod.analyze(events, outdir, cursor, peer_id='peer-test', now='2026-07-30T00:01:00Z')
            self.assertEqual(stats['retrieval']['by_provenance']['calibration_probe'], 1)
            self.assertEqual(stats['retrieval']['review_queue'][0]['provenance'], 'calibration_probe')
            self.assertTrue((outdir / 'review' / 'queue-latest.csv').exists())
            self.assertTrue((outdir / 'review' / 'queue-latest.jsonl').exists())
            rollup = json.loads((outdir / 'rollups' / '24h.json').read_text())
            self.assertEqual(rollup['retrieval']['by_provenance']['calibration_probe'], 1)
            self.assertEqual(rollup['retrieval']['review_candidates'][0]['candidate'], 'hmp-healthcheck@1.0.0')

    def test_missing_and_invalid_provenance_do_not_become_organic(self):
        stats = mod.initial_stats('peer-test', '2026-07-30T00:00:00Z')
        base = {
            "event_type": "retrieval_event",
            "timestamp": "2026-07-30T00:00:00Z",
            "data": {
                "shadow_mode": True,
                "top_score": 0.9,
                "candidates": [{"capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "score": 0.9}],
            },
        }
        mod.add_event(stats, base, {})
        invalid = json.loads(json.dumps(base))
        invalid['data']['provenance'] = {'stream': 'banana'}
        mod.add_event(stats, invalid, {})
        mod.finalize_stats(stats)
        self.assertEqual(stats['retrieval']['by_provenance']['legacy_unclassified'], 1)
        self.assertEqual(stats['retrieval']['by_provenance']['unknown'], 1)
        self.assertNotIn('organic_live', stats['retrieval']['by_provenance'])
        self.assertIn('missing_provenance', stats['anomalies'])
        self.assertIn('invalid_provenance', stats['anomalies'])

    def test_csv_export_neutralizes_formula_and_preserves_existing_labels(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / 'events.jsonl'
            outdir = root / 'out'
            review_dir = outdir / 'review'
            review_dir.mkdir(parents=True)
            saved = {
                "timestamp": "2026-07-30T00:00:00Z",
                "event_id": "evt-formula",
                "peer_id": "peer-test",
                "capability": "hmp-healthcheck@1.0.0",
                "label": "true_positive",
                "review_notes": "kept",
            }
            (review_dir / 'queue-latest.jsonl').write_text(json.dumps(saved) + '\n')
            event = {
                "event_id": "evt-formula",
                "event_type": "retrieval_event",
                "timestamp": "2026-07-30T00:00:00Z",
                "data": {
                    "peer_id": "peer-test",
                    "provenance": {"stream": "operator_seeded"},
                    "shadow_mode": True,
                    "top_score": 0.9,
                    "user_message_preview": "=HYPERLINK(\"http://evil\")",
                    "candidates": [{"capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "score": 0.9}],
                },
            }
            events.write_text(json.dumps(event) + '\n')
            export = mod.export_review_queue(events, outdir, {}, limit=10)
            self.assertEqual(export['rows'], 1)
            row = json.loads((review_dir / 'queue-latest.jsonl').read_text().splitlines()[0])
            self.assertEqual(row['label'], 'true_positive')
            self.assertEqual(row['review_notes'], 'kept')
            csv_text = (review_dir / 'queue-latest.csv').read_text()
            self.assertIn("'=HYPERLINK", csv_text)

    def test_rollups_use_event_timestamp_not_run_generated_at(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / 'out'
            runs = outdir / 'runs'
            runs.mkdir(parents=True)
            run = mod.initial_stats('peer-test', '2026-07-30T00:00:00Z')
            run['retrieval']['review_queue'] = [
                {"timestamp": "2026-07-20T00:00:00Z", "peer_id": "peer-test", "provenance": "organic_live", "capability": "old@1.0.0", "score": 0.9, "shadow_mode": True},
                {"timestamp": "2026-07-29T23:30:00Z", "peer_id": "peer-test", "provenance": "organic_live", "capability": "new@1.0.0", "score": 0.8, "shadow_mode": True},
            ]
            mod.atomic_write_json(runs / 'peer-test-20260730-000000Z.json', run)
            rollups = mod.build_rollups(outdir, now_dt=mod.parse_utc('2026-07-30T00:00:00Z'))
            self.assertEqual(rollups['24h']['window_basis'], 'event_timestamp')
            self.assertEqual(rollups['24h']['totals']['retrieval_total'], 1)
            self.assertEqual(rollups['24h']['retrieval']['candidate_counts'], {'new@1.0.0': 1})


if __name__ == '__main__':
    unittest.main()
