#!/usr/bin/env python3
"""Import validated capability-reuse v2.2.0 artifact, update registry, prepare deploy."""
import zipfile, os, sys, json, shutil, hashlib
from pathlib import Path

ARTIFACT = "/tmp/capability-reuse-validated-20260728-022630.zip"
SKILL_DIR = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
PLUGIN_DIR = os.path.expanduser("~/.hermes/plugins/capability-reuse")
REGISTRY_DIR = os.path.expanduser("~/.hermes/data/capability-registry")
EVIDENCE_DIR = os.path.join(SKILL_DIR, "evidence")
RELEASE_ARTIFACT_DIR = os.path.expanduser("~/.hermes/releases/capability-reuse/v2.2.0")

errors = []

# 1. Verify artifact
if not os.path.exists(ARTIFACT):
    errors.append("Artifact not found")
else:
    sz = os.path.getsize(ARTIFACT)
    with open(ARTIFACT, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f"ARTIFACT: size={sz}, sha256={sha}")
    assert sha == "2f7f968d518d01fc1eac7691088951b4a0957b5edc511f79a23084c72d0cb29d", "SHA mismatch"
    assert sz == 159920, "Size mismatch"
    print("ARTIFACT_VERIFIED: PASS")

# 2. Copy to releases/
os.makedirs(RELEASE_ARTIFACT_DIR, exist_ok=True)
shutil.copy2(ARTIFACT, os.path.join(RELEASE_ARTIFACT_DIR, "capability-reuse-v2.2.0.zip"))
print("RELEASE_COPIED: v2.2.0")

# 3. List contents
with zipfile.ZipFile(ARTIFACT) as z:
    names = z.namelist()
    print(f"ZIP_CONTENTS ({len(names)} files):")
    for n in names:
        print(f"  {n}")

# 4. Update skill dir from zip
with zipfile.ZipFile(ARTIFACT) as z:
    z.extractall(SKILL_DIR)
print("SKILL_EXTRACTED")

# 5. Copy plugin files to runtime plugin dir
plugin_src = os.path.join(SKILL_DIR, "plugin")
if os.path.isdir(plugin_src):
    # Remove old __pycache__
    pycache = os.path.join(PLUGIN_DIR, "__pycache__")
    if os.path.isdir(pycache):
        shutil.rmtree(pycache)
    for fname in os.listdir(plugin_src):
        if fname == "__pycache__":
            continue
        sf = os.path.join(plugin_src, fname)
        if os.path.isfile(sf):
            df = os.path.join(PLUGIN_DIR, fname)
            shutil.copy2(sf, df)
            print(f"  plugin: {fname} -> runtime")
    # Touch plugin.yaml
    pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
    if os.path.exists(pyf):
        os.utime(pyf, None)
    print("PLUGIN_RUNTIME_SYNCED")

# 6. Update registry
# Read current registry
reg_path = os.path.join(REGISTRY_DIR, "registry.json")
if os.path.exists(reg_path):
    with open(reg_path) as f:
        reg = json.load(f)
    # Update version in capability entries
    for cap in reg.get("capabilities", []):
        meta = cap.get("retrieval_metadata", {})
        if meta.get("capability_id") == "hmp-healthcheck":
            meta["version"] = "2.2.0"
        inv = cap.get("invocation_contract", {})
        if inv.get("capability_id") == "hmp-healthcheck":
            inv["version"] = "2.2.0"
    with open(reg_path, 'w') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    print("REGISTRY_UPDATED: v2.2.0")

# 7. Update deployment-manifest.json
manifest_path = os.path.join(EVIDENCE_DIR, "deployment-manifest.json")
if os.path.exists(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    manifest["version"] = "2.2.0"
    manifest["skill_version"] = "2.2.0"
    manifest["artifact"] = "capability-reuse-v2.2.0.zip"
    manifest["artifact_sha256"] = sha
    manifest["validation"] = "compile PASS, unittest 45/45, conformance 15/15, overhead p99 14.951ms, active canary 5/5"
    manifest["updated_at"] = __import__('time').strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print("MANIFEST_UPDATED")

print(f"\n{'ERRORS:' + str(errors) if errors else 'IMPORT_COMPLETE'}")
