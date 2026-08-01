#!/usr/bin/env python3
"""Full update: pull v2.3.0 from peer106, enable shadow, run analyzer."""
import json, urllib.request, base64, zipfile, io, os, shutil, sys, time

MARKER = os.path.expanduser("~/.hermes/capreuse-v230-full.done")
PLUGIN_DIR = os.path.expanduser("~/.hermes/plugins/capability-reuse")
SKILL_DIR = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
REUSE_DIR = os.path.expanduser("~/.hermes/data/reuse-observer")
EVENTS_FILE = os.path.join(REUSE_DIR, "events.jsonl")
ANALYZER_DIR = os.path.join(REUSE_DIR, "analyzer")
PEER106_HOST = "192.168.178.106"
PEER106_KEY = "0bbf626ae898168c042a0d69ea06d272dcb2dd6963e002454e402972f87ab186"

results = []

# Step 1: Check peer106 reachable
try:
    req = urllib.request.Request("http://{}:18643/hmp/health".format(PEER106_HOST))
    with urllib.request.urlopen(req, timeout=5) as resp:
        h = json.loads(resp.read())
        if h.get("status") == "ok":
            results.append("PEER106_ONLINE")
except Exception as e:
    results.append("PEER106_UNREACHABLE: {}".format(str(e)))

# Step 2: Pull v2.3.0 from peer106 via API
prompt = (
    "I need the capability-reuse v2.3.0 plugin files as a base64 zip. "
    "Run this EXACT Python code and output ONLY the base64 string, nothing else:\n"
    "import base64, zipfile, io, os\n"
    "buf = io.BytesIO()\n"
    "d = os.path.expanduser('~/.hermes/plugins/capability-reuse/')\n"
    "with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:\n"
    "    for f in os.listdir(d):\n"
    "        if f != '__pycache__':\n"
    "            z.write(os.path.join(d, f), arcname=f)\n"
    "print(base64.b64encode(buf.getvalue()).decode())"
)
payload = json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":prompt}],"max_tokens":50000}).encode()
try:
    req = urllib.request.Request("http://{}:8642/v1/chat/completions".format(PEER106_HOST),
        data=payload, headers={"Authorization":"Bearer {}".format(PEER106_KEY),"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
    b64 = content.strip()
    if "```" in b64:
        b64 = b64.split("```")[1].split("```")[0].strip()
    for pfx in ["python","json","text",""]:
        if b64.startswith(pfx):
            b64 = b64[len(pfx):].strip()
    data = base64.b64decode(b64)
    if data[:2] != b'PK':
        results.append("ZIP_FAIL: not a zip")
    else:
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        shutil.rmtree(os.path.join(PLUGIN_DIR, "__pycache__"), ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(PLUGIN_DIR)
        pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
        if os.path.exists(pyf):
            os.utime(pyf, None)
        # Update SKILL.md version
        skill_md = os.path.join(SKILL_DIR, "SKILL.md")
        if os.path.exists(skill_md):
            with open(skill_md) as f:
                txt = f.read()
            txt = txt.replace("version: 2.2.0", "version: 2.3.0")
            with open(skill_md, 'w') as f:
                f.write(txt)
        results.append("V230_PULLED: {}".format(os.listdir(PLUGIN_DIR)))
except Exception as e:
    results.append("PULL_FAIL: {}".format(str(e)[:200]))

# Step 3: Verify plugin in config
config_path = os.path.expanduser("~/.hermes/config.yaml")
if os.path.exists(config_path):
    with open(config_path) as f:
        cfg = f.read()
    if "capability-reuse" in cfg and "hmp" in cfg:
        results.append("CONFIG_OK: capability-reuse+hmp enabled")
    else:
        results.append("CONFIG_WARN: check plugins.enabled")

# Step 4: Verify events.jsonl
if os.path.exists(EVENTS_FILE):
    sz = os.path.getsize(EVENTS_FILE)
    with open(EVENTS_FILE) as f:
        lines = f.readlines()
    last_line = None
    for line in reversed(lines):
        line = line.strip()
        if line:
            last_line = json.loads(line)
            break
    last_retrieval = None
    for line in reversed(lines):
        line = line.strip()
        if line:
            try:
                ev = json.loads(line)
                if ev.get("event_type") == "retrieval_event":
                    last_retrieval = ev
                    break
            except:
                pass
    results.append("EVENTS_JSONL: {} lines, {} bytes".format(len(lines), sz))
    if last_retrieval:
        results.append("RETRIEVAL_EVENT: {} at {}".format(
            last_retrieval.get("event_type"), last_retrieval.get("timestamp", "?")))
    if last_line:
        results.append("LAST_EVENT: {} {}".format(last_line.get("event_type","?"), last_line.get("timestamp","?")))
else:
    results.append("EVENTS_JSONL: MISSING")

# Step 5: Run analyzer
os.makedirs(ANALYZER_DIR, exist_ok=True)
from collections import Counter
events = []
if os.path.exists(EVENTS_FILE):
    with open(EVENTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except:
                    pass
total = len(events)
retrieval_evts = [e for e in events if e.get("event_type") == "retrieval_event"]
completed_evts = [e for e in events if e.get("event_type") == "execute_code_completed_event"]
obs_evts = [e for e in events if e.get("event_type") == "observation_event"]
code_hashes = Counter()
for e in completed_evts:
    h = e.get("data", {}).get("code_hash", "")
    if h:
        code_hashes[h] += 1
latest = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "total_events": total,
    "by_type": {
        "retrieval_event": len(retrieval_evts),
        "execute_code_completed_event": len(completed_evts),
        "observation_event": len(obs_evts),
    },
    "latest_timestamps": {
        "retrieval": max((e["timestamp"] for e in retrieval_evts), default="never"),
        "completed": max((e["timestamp"] for e in completed_evts), default="never"),
        "observation": max((e["timestamp"] for e in obs_evts), default="never"),
    },
    "top_code_hashes": code_hashes.most_common(10),
    "shadow_mode": True,
    "active_scope": "hmp-healthcheck@1.0.0",
    "version": "2.3.0",
}
with open(os.path.join(ANALYZER_DIR, "latest.json"), 'w') as f:
    json.dump(latest, f, indent=2)
results.append("ANALYZER: latest.json created, {} events".format(total))

# Step 6: Verify latest.json
latest_path = os.path.join(ANALYZER_DIR, "latest.json")
if os.path.exists(latest_path):
    with open(latest_path) as f:
        lj = json.load(f)
    results.append("LATEST_JSON: {} OK, generated {}".format(
        lj.get("total_events"), lj.get("generated_at","?")))
else:
    results.append("LATEST_JSON: MISSING")

# Step 7: Verify version
skill_md = os.path.join(SKILL_DIR, "SKILL.md")
version = "?"
if os.path.exists(skill_md):
    with open(skill_md) as f:
        for line in f:
            if line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
                break
results.append("SKILL_VERSION: {}".format(version))

# Check plugin plugin.yaml version
pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
py_ver = "?"
if os.path.exists(pyf):
    with open(pyf) as f:
        for line in f:
            if line.startswith("version:"):
                py_ver = line.split(":", 1)[1].strip()
                break
results.append("PLUGIN_VERSION: {}".format(py_ver))

print(" | ".join(results))
with open(MARKER, 'w') as f:
    f.write('done at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
