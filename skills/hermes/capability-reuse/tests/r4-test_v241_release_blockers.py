import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class V241ReleaseBlockerTests(unittest.TestCase):
    def setUp(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
        os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
        os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
        os.environ["CAPABILITY_REUSE_INTERVENTION_THRESHOLD"] = "0.65"
        os.environ["CAPABILITY_REUSE_MINIMUM_MARGIN"] = "0.10"
        self.protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        self.retriever = importlib.reload(importlib.import_module("plugin.retriever"))
        self.dispatcher = importlib.reload(importlib.import_module("plugin.dispatcher"))
        self.protocol._store = self.protocol.InterventionStore()

    def tearDown(self):
        for key in [
            "CAPABILITY_REUSE_MODE",
            "CAPABILITY_REUSE_ACTIVE_CAPABILITIES",
            "CAPABILITY_REUSE_PERMISSIONS",
            "CAPABILITY_REUSE_AVAILABLE_CAPABILITIES",
            "CAPABILITY_REUSE_INTERVENTION_THRESHOLD",
            "CAPABILITY_REUSE_MINIMUM_MARGIN",
        ]:
            os.environ.pop(key, None)

    def test_composite_mutation_prompts_do_not_intervene(self):
        prompts = [
            "check HMP health, then reboot peer128",
            "check HMP health and shutdown peer128",
            "check HMP health then kill peer128 gateway",
            "check HMP health then terminate peer128 process",
            "check HMP health then reset peer128",
            "check HMP health then power cycle peer128",
            "check HMP health and patch peer128",
            "check HMP health then upgrade peer128",
            "check HMP health and then do the next maintenance action on peer128",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                decision = self.protocol.retrieve(
                    session_id="v241-composite",
                    user_message=prompt,
                    hook_context={"episode_id": "v241-composite", "turn_id": prompt[:12]},
                )
                self.assertIsNone(decision)

    def test_unsupported_peer_target_is_rejected_before_intervention(self):
        decision = self.protocol.retrieve(
            session_id="v241-peer999",
            user_message="check HMP health for peer999",
            hook_context={"episode_id": "v241-peer999", "turn_id": "t1"},
        )
        self.assertIsNone(decision)

    def test_unsupported_target_is_clean_if_dispatcher_called_directly(self):
        self.protocol._store.create_intervention("int_unsupported", "episode_unsupported", "hmp-healthcheck", "1.0.0")
        result = self.protocol.invoke_capability({
            "intervention_id": "int_unsupported",
            "capability_id": "hmp-healthcheck",
            "capability_version": "1.0.0",
            "inputs": {"peer_list": ["peer999"], "timeout_seconds": 1},
        })
        self.assertFalse(result["success"])
        self.assertEqual("unsupported_target", result["error"])
        self.assertEqual("fallback_authorized", result["state"])
        self.assertTrue(result.get("fallback_authorization_id"))

    def test_conformance_report_labels_local_controller_not_live_runtime(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "conformance-suite.py"), "--only", "6"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        self.assertNotIn("Requires live Hermes: 0", proc.stdout)
        self.assertIn("Evidence scope: local-controller", proc.stdout)
        report = json.loads((Path.home() / ".hermes" / "data" / "capability-registry" / "conformance-report.json").read_text())
        self.assertEqual("local-controller", report.get("evidence_scope"))
        self.assertFalse(report.get("pinned_hermes_cli_conformance"))
        self.assertFalse(report.get("gateway_conformance"))
        self.assertFalse(report.get("delegated_agent_conformance"))

    def _write_minimal_archive(self, archive_path, version="2.4.1", conf_tree_hash=None, conf_identity_present=True):
        conf_identity = {}
        if conf_identity_present:
            conf_identity = {"plugin_tree_hash": conf_tree_hash or ("0" * 64)}
        files = {
            "capability-reuse/SKILL.md": "---\nname: capability-reuse\nversion: %s\n---\n" % version,
            "capability-reuse/plugin/plugin.yaml": "name: capability-reuse\nversion: %s\nhooks: []\ntools: []\n" % version,
            "capability-reuse/plugin/protocol.py": 'VERSION = "%s"\n' % version,
            "capability-reuse/plugin/__init__.py": "def _mode():\n    return 'shadow'\nctrl.retrieve(\nctrl.authorize_execute_code(\nctrl.record_tool_outcome(\n",
            "capability-reuse/evidence/deployment-manifest.json": json.dumps({
                "version": version,
                "skill_version": version,
                "plugin_version": version,
                "protocol_VERSION": version,
                "test_report": "evidence/unit-test-report-v%s.json" % version,
                "conformance_report": "evidence/conformance-report-v%s.json" % version,
            }),
            "capability-reuse/evidence/unit-test-report-v%s.json" % version: json.dumps({"passed": 1, "failed": 0, "status": "PASS"}),
            "capability-reuse/evidence/conformance-report-v%s.json" % version: json.dumps({
                "evidence_scope": "local-controller", "passed": 15, "failed": 0,
                "status": "PASS",
                "artifact_identity": conf_identity,
            }),
        }
        checks = []
        for name, content in files.items():
            if name.endswith("evidence/SHA256SUMS"):
                continue
            checks.append("%s  %s" % (hashlib.sha256(content.encode()).hexdigest(), name.split("capability-reuse/evidence/", 1)[-1] if "/evidence/" in name else name))
        files["capability-reuse/evidence/SHA256SUMS"] = "\n".join(checks) + "\n"
        with zipfile.ZipFile(str(archive_path), "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)

    def _archive_plugin_hash(self, archive):
        import zipfile as _zf
        with _zf.ZipFile(str(archive)) as zf:
            h = hashlib.sha256()
            plugin_files = [n for n in zf.namelist() if n.startswith("capability-reuse/plugin/") and not n.endswith("/")]
            for name in sorted(plugin_files):
                h.update(name.encode("utf-8")); h.update(b"\0"); h.update(zf.read(name)); h.update(b"\0")
            return h.hexdigest()

    def test_release_validator_rejects_archive_hash_mismatch_and_accepts_expected_hash(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "capability-reuse-v2.4.1.zip"
            # first pass: write archive to learn the real plugin tree hash,
            # then rebuild with the correct conformance identity
            self._write_minimal_archive(archive)
            tree_hash = self._archive_plugin_hash(archive)
            self._write_minimal_archive(archive, conf_tree_hash=tree_hash)
            real_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            bad = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate-release-archive.py"), str(archive), "--version", "2.4.1", "--expected-sha256", "0" * 64],
                cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120,
            )
            self.assertNotEqual(0, bad.returncode, bad.stdout)
            self.assertIn("archive SHA256 mismatch", bad.stdout)
            good = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate-release-archive.py"), str(archive), "--version", "2.4.1", "--expected-sha256", real_hash],
                cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120,
            )
            self.assertEqual(0, good.returncode, good.stdout)
            self.assertIn(real_hash, good.stdout)

    def test_release_validator_rejects_wrong_conformance_identity(self):
        """P0 round-3 (reviewer 2026-08-16): a conformance report bound to a
        DIFFERENT plugin tree must be rejected (fail-closed), even when
        SHA256SUMS is updated consistently."""
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "capability-reuse-v2.4.1.zip"
            self._write_minimal_archive(archive, conf_tree_hash="0" * 64)  # wrong identity
            real_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate-release-archive.py"), str(archive), "--version", "2.4.1", "--expected-sha256", real_hash],
                cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120,
            )
            self.assertNotEqual(0, proc.returncode, "validator must reject wrong conformance identity\n" + proc.stdout)
            self.assertIn("conformance artifact identity mismatch", proc.stdout)

    def test_release_validator_requires_conformance_identity(self):
        """P0 round-3: missing artifact_identity.plugin_tree_hash in the
        conformance report is a release blocker."""
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "capability-reuse-v2.4.1.zip"
            self._write_minimal_archive(archive, conf_identity_present=False)
            real_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validate-release-archive.py"), str(archive), "--version", "2.4.1", "--expected-sha256", real_hash],
                cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120,
            )
            self.assertNotEqual(0, proc.returncode, "validator must require conformance identity\n" + proc.stdout)
            self.assertIn("missing artifact_identity.plugin_tree_hash", proc.stdout)


if __name__ == "__main__":
    unittest.main()
