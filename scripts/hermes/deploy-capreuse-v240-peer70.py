#!/usr/bin/env python3
"""Deploy capability-reuse v2.4.0 to peer70 only. Remote peers via separate job."""
import os, sys, json, zipfile, shutil, hashlib, time

MARKER = os.path.expanduser("~/.hermes/capreuse-v240-peer70.done")
if os.path.exists(MARKER):
    print("ALREADY_DONE_PEER70")
    sys.exit(0)

ARTIFACT = "/tmp/capability-reuse-v2.4.0.zip"
SKILL_DIR = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
PLUGIN_DIR = os.path.expanduser("~/.hermes/plugins/capability-reuse")
RELEASE_DIR = os.path.expanduser("~/.hermes/releases/capability-reuse/v2.4.0")
EVIDENCE_DIR = os.path.join(SKILL_DIR, "evidence")

if not os.path.exists(ARTIFACT):
    print("ERROR: artifact not found")
    sys.exit(1)

with open(ARTIFACT,'rb') as f:
    sha = hashlib.sha256(f.read()).hexdigest()
results = [f"ARTIFACT: {os.path.getsize(ARTIFACT)}b sha256={sha[:16]}"]

# Copy to releases
os.makedirs(RELEASE_DIR, exist_ok=True)
shutil.copy2(ARTIFACT, os.path.join(RELEASE_DIR, "capability-reuse-v2.4.0.zip"))

# Extract to skill dir
with zipfile.ZipFile(ARTIFACT) as z:
    z.extractall(SKILL_DIR)
results.append("SKILL_EXTRACTED")

# Sync plugin files
shutil.rmtree(os.path.join(PLUGIN_DIR, "__pycache__"), ignore_errors=True)
psrc = os.path.join(SKILL_DIR, "plugin")
if os.path.isdir(psrc):
    for fn in os.listdir(psrc):
        if fn == "__pycache__": continue
        sf = os.path.join(psrc, fn)
        if os.path.isfile(sf):
            shutil.copy2(sf, os.path.join(PLUGIN_DIR, fn))
    pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
    if os.path.exists(pyf): os.utime(pyf, None)
    results.append("PLUGIN_SYNCED")

# Read versions
sv = pv = "?"
with open(os.path.join(SKILL_DIR,"SKILL.md")) as f:
    for l in f:
        if l.startswith("version:"): sv = l.split(":",1)[1].strip(); break
with open(os.path.join(PLUGIN_DIR,"plugin.yaml")) as f:
    for l in f:
        if l.startswith("version:"): pv = l.split(":",1)[1].strip(); break
results.append(f"SKILL={sv} PLUGIN={pv}")

# Check config
with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
    cfg = f.read()
results.append(f"CONFIG: cr={'capability-reuse' in cfg} hmp={'hmp' in cfg}")

# Generate SHA256SUMS
os.makedirs(EVIDENCE_DIR, exist_ok=True)
sums = {}
for root, dirs, files in os.walk(SKILL_DIR):
    for f in files:
        fp = os.path.join(root, f)
        rp = os.path.relpath(fp, SKILL_DIR)
        with open(fp, 'rb') as fh:
            sums[rp] = hashlib.sha256(fh.read()).hexdigest()
with open(os.path.join(EVIDENCE_DIR, "SHA256SUMS"), 'w') as f:
    for rp, h in sorted(sums.items()):
        f.write(f"{h}  {rp}\n")
results.append(f"SHA256SUMS: {len(sums)} files")

with open(MARKER, 'w') as f:
    f.write('done at ' + time.strftime('%Y-%m-%d %H:%M:%S'))

print(" | ".join(results))
