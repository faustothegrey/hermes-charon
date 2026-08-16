#!/usr/bin/env python3
from __future__ import annotations
"""Validate a packaged capability-reuse release archive.

Checks release-assembly and provenance invariants:
- archive contains exactly one top-level capability-reuse skill tree;
- no nested capability-reuse/capability-reuse duplicate tree;
- SKILL.md, plugin/plugin.yaml and plugin/protocol.py versions match expected;
- plugin/__init__.py routes through the controller entrypoint;
- evidence/deployment-manifest.json identifies the expected version;
- optional/required archive SHA256 or sidecar matches the actual ZIP;
- internal evidence/SHA256SUMS validates files inside the ZIP;
- plugin tree hash matches manifest when declared;
- test/conformance reports referenced by the manifest are present and passing.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile


def read_text(zf, name):
    try:
        return zf.read(name).decode("utf-8")
    except KeyError:
        raise AssertionError("missing %s" % name)


def yaml_version(text):
    m = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", text)
    if not m:
        raise AssertionError("version field not found")
    return m.group(1)


def assert_contains(text, needle, label):
    if needle not in text:
        raise AssertionError("%s missing %r" % (label, needle))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_from_sidecar(path):
    text = open(path, "r", encoding="utf-8").read().strip()
    if not text:
        raise AssertionError("empty sha256 sidecar")
    return text.split()[0]


def verify_internal_checksums(zf):
    sums_text = read_text(zf, "capability-reuse/evidence/SHA256SUMS")
    checked = 0
    for raw in sums_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise AssertionError("malformed SHA256SUMS line: %r" % raw)
        expected, rel = parts[0], parts[-1].lstrip("*")
        candidates = [
            "capability-reuse/evidence/" + rel,
            "capability-reuse/" + rel,
            rel,
        ]
        name = next((c for c in candidates if c in zf.namelist()), None)
        if not name:
            raise AssertionError("SHA256SUMS references missing file %s" % rel)
        actual = sha256_bytes(zf.read(name))
        if actual != expected:
            raise AssertionError("internal checksum mismatch for %s" % rel)
        checked += 1
    if checked == 0:
        raise AssertionError("evidence/SHA256SUMS contained no checks")
    return checked


def plugin_tree_hash(zf):
    h = hashlib.sha256()
    plugin_files = [n for n in zf.namelist() if n.startswith("capability-reuse/plugin/") and not n.endswith("/")]
    for name in sorted(plugin_files):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(zf.read(name))
        h.update(b"\0")
    return h.hexdigest()


def verify_report(zf, report_path, label):
    if not report_path:
        raise AssertionError("manifest missing %s report path" % label)
    name = report_path if report_path.startswith("capability-reuse/") else "capability-reuse/" + report_path
    data = json.loads(read_text(zf, name))
    if data.get("failed", 0) not in (0, None):
        raise AssertionError("%s report has failures" % label)
    if label == "conformance" and data.get("evidence_scope") != "local-controller":
        raise AssertionError("conformance report must declare evidence_scope=local-controller")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--version", required=True)
    ap.add_argument("--expected-sha256", help="Expected SHA256 for the ZIP archive")
    ap.add_argument("--sha256-file", help="Sidecar file containing expected archive SHA256")
    args = ap.parse_args(argv)

    actual_archive_sha = sha256_file(args.archive)
    expected_sha = args.expected_sha256 or (expected_from_sidecar(args.sha256_file) if args.sha256_file else None)
    if expected_sha and actual_archive_sha.lower() != expected_sha.lower():
        raise AssertionError("archive SHA256 mismatch: expected %s actual %s" % (expected_sha, actual_archive_sha))

    with zipfile.ZipFile(args.archive) as zf:
        names = zf.namelist()
        if not any(n.startswith("capability-reuse/") for n in names):
            raise AssertionError("archive lacks capability-reuse/ top-level tree")
        nested = [n for n in names if n.startswith("capability-reuse/capability-reuse/")]
        if nested:
            raise AssertionError("nested duplicate skill entries found: %d" % len(nested))

        # HARD SAFETY RULE (2026-08-15): core patches MUST NOT ship inside
        # the skill archive. A general skill sync (zip/rsync/scp) that
        # carries patches/ risks applying the wrong core patch (or copying
        # it over core files) and corrupting the Hermes agent itself.
        # Core patches travel ONLY via apply-core-patch.sh (sha256 +
        # reverse-check + version match) or a pointed scp to a staging dir.
        core_patch_entries = [
            n for n in names
            if n.startswith("capability-reuse/patches/") and not n.endswith("/")
        ]
        if core_patch_entries:
            raise AssertionError(
                "core patches must NOT be inside the skill archive (%d entries, "
                "e.g. %s) — ship patches/ separately via apply-core-patch.sh"
                % (len(core_patch_entries), core_patch_entries[0])
            )

        skill = read_text(zf, "capability-reuse/SKILL.md")
        plugin_yaml = read_text(zf, "capability-reuse/plugin/plugin.yaml")
        protocol = read_text(zf, "capability-reuse/plugin/protocol.py")
        init = read_text(zf, "capability-reuse/plugin/__init__.py")
        manifest = json.loads(read_text(zf, "capability-reuse/evidence/deployment-manifest.json"))

        if yaml_version(skill) != args.version:
            raise AssertionError("SKILL.md version mismatch")
        if yaml_version(plugin_yaml) != args.version:
            raise AssertionError("plugin.yaml version mismatch")
        assert_contains(protocol, 'VERSION = "%s"' % args.version, "protocol.VERSION")
        if manifest.get("version") != args.version or manifest.get("skill_version") != args.version:
            raise AssertionError("deployment manifest version mismatch")
        if manifest.get("plugin_version") and manifest.get("plugin_version") != args.version:
            raise AssertionError("deployment manifest plugin_version mismatch")
        if manifest.get("protocol_VERSION") and manifest.get("protocol_VERSION") != args.version:
            raise AssertionError("deployment manifest protocol_VERSION mismatch")

        assert_contains(init, "def _mode()", "dynamic mode")
        assert_contains(init, "ctrl.retrieve(", "pre_llm controller path")
        assert_contains(init, "ctrl.authorize_execute_code(", "pre_tool controller path")
        assert_contains(init, "ctrl.record_tool_outcome(", "post_tool controller path")
        if "ret.retrieve(" in init:
            raise AssertionError("entrypoint bypasses controller via ret.retrieve(")

        checked = verify_internal_checksums(zf)
        actual_plugin_hash = plugin_tree_hash(zf)
        declared_plugin_hash = manifest.get("source_plugin_tree_sha256") or manifest.get("plugin_hash")
        if declared_plugin_hash and declared_plugin_hash != actual_plugin_hash:
            raise AssertionError("plugin hash mismatch: expected %s actual %s" % (declared_plugin_hash, actual_plugin_hash))
        validation = manifest.get("validation", {}) if isinstance(manifest.get("validation"), dict) else {}
        verify_report(zf, validation.get("unit_test_report") or manifest.get("test_report"), "unit")
        verify_report(zf, validation.get("conformance_report") or manifest.get("conformance_report"), "conformance")
        # review-2 hardening: OGNI evidence path dichiarato sotto validation
        # (driver, log, evidence file) deve esistere nell'archivio — il
        # manifest non puo' dichiarare evidence inclusa se l'artifact non la
        # contiene (blocker di release emerso in review-2 su e2e_mesh_evidence).
        for vkey, vpath in validation.items():
            if vkey in ("unit_test_report", "conformance_report"):
                continue  # gia' verificati sopra (contenuto e failed=0)
            if not isinstance(vpath, str) or not vpath:
                continue
            cand = vpath if vpath.startswith("capability-reuse/") else "capability-reuse/" + vpath
            if cand not in zf.namelist():
                raise AssertionError(
                    "manifest validation.%s declares missing evidence: %s" % (vkey, vpath))
        if not (expected_sha or manifest.get("artifact_sha256") == actual_archive_sha):
            raise AssertionError("canonical archive hash not supplied by sidecar/argument or embedded manifest")

    print("PASS release archive %s version %s sha256 %s internal_checks %d" % (args.archive, args.version, actual_archive_sha, checked))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAIL: %s" % e)
        raise SystemExit(1)
