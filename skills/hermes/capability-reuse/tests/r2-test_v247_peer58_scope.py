from __future__ import annotations
import importlib.util
import importlib
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PLUGIN_DIR = SKILL_DIR / "plugin"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

execution_plan = load_module("execution_plan", PLUGIN_DIR / "execution_plan.py")
v244_metadata = load_module("v244_metadata_v249", PLUGIN_DIR / "v244_metadata.py")
review_queue = load_module("review_queue", PLUGIN_DIR / "review_queue.py")
retriever = importlib.import_module("plugin.retriever")

class V249Peer58ScopeTests(unittest.TestCase):
    def test_peer58_is_supported_in_preview_and_dispatch_targeting(self):
        plan = execution_plan.build_execution_plan("hmp-healthcheck", "1.0.0", {"peer_list": ["peer58"], "timeout_seconds": 5})
        self.assertEqual(plan["preview_status"], "exact")
        self.assertEqual(plan["target_peer_id"], "peer58")
        self.assertEqual(plan["endpoint"], "http://192.168.178.58:18643/hmp/health")
        self.assertIn("GET http://192.168.178.58:18643/hmp/health", plan["command_preview"])

    def test_version_surfaces_are_v2418_and_formal_eligibility_uses_v2418(self):
        self.assertEqual(v244_metadata.PLUGIN_VERSION, "2.6.0")
        event = {"schema_version": "1.3", "timestamp": "2026-08-16T11:00:00Z"}
        data = {
            "plugin_version": "2.6.0",
            "deployment_id": "dep-v2418-live",
            "deployment_timestamp": "2026-08-16T10:08:44Z",
            "plugin_artifact_hash": "sha256:abc",
            "cohort_label": "v2.5.0_live",
            "provenance": {"stream": "organic_live", "valid": True, "source": "hook_context.capability_reuse_provenance"},
            "traffic_type": "organic_peer",
            "requester_peer_id": "peer58",
            "trace_id": "trace-v2418-peer58",
            "producer_surface": "hmp_ingress",
        }
        requester = {"requester_type": "hmp_peer", "processing_peer_id": "peer106"}
        ok, reasons = review_queue.formal_holdout_validation(event, data, requester)
        self.assertTrue(ok, reasons)

    def test_hmp_platform_hook_context_derives_organic_peer_metadata(self):
        ctx = {"platform": "hmp", "sender_id": "peer106"}
        # traffic_type from channel inference still yields organic_peer
        self.assertEqual(retriever._extract_traffic_type(ctx), "organic_peer")
        self.assertEqual(retriever._extract_requester(ctx)["requester_peer_id"], "peer106")
        self.assertEqual(retriever._extract_requester(ctx)["request_channel"], "hmp")
        # P0-2 (2026-08-16): platform identity alone NEVER yields organic_live;
        # provenance requires an explicit declaration. Missing → None.
        self.assertEqual(retriever._request_provenance(ctx), (None, "", "hook_context.capability_reuse_provenance"))

if __name__ == "__main__":
    unittest.main()
