import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConformanceIntegrationGateTests(unittest.TestCase):
    def test_full_required_conformance_has_no_skips(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "conformance-suite.py"), "--profile", "full-required"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Results: 15 passed, 0 failed, 0 skipped / 15 total", proc.stdout)


if __name__ == "__main__":
    unittest.main()
