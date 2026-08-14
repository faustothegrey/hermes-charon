import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConformanceIntegrationGateTests(unittest.TestCase):
    def test_full_required_conformance_has_no_skips(self):
        # Isolate the event log: the conformance suite registers hooks and
        # emits events — never into the live reuse-observer/events.jsonl.
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["CAPABILITY_REUSE_EVENT_DIR"] = tmp
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "conformance-suite.py"), "--profile", "full-required"],
                cwd=str(ROOT),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Results: 15 passed, 0 failed, 0 skipped / 15 total", proc.stdout)


if __name__ == "__main__":
    unittest.main()
