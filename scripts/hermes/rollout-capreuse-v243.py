#!/usr/bin/env python3
"""capability-reuse v2.4.3 rollout to all active peers."""
import json, urllib.request, base64, subprocess, sys, os, time, hashlib

ARTIFACT = "/tmp/capability-reuse-v2.4.3.zip"
LOG = "/home/fausto/.hermes/capreuse-v243-rollout.log"

def log(msg):
    with open(LOG, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    print(msg)

with open(ARTIFACT, 'rb') as f: data = f.read()
b64 = base64.b64encode(data).decode()
sha = hashlib.sha256(data).hexdigest()
log(f"ARTIFACT: {len(data)}b sha256={sha[:16]}")

# PEER70 local install
log("=== peer70 local ===")
import zipfile, shutil
SKILL_DIR = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
PLUGIN_DIR = os.path.expanduser("~/.hermes/plugins/capability-reuse")
with zipfile.ZipFile(ARTIFACT) as z: z.extractall(SKILL_DIR)
shutil.rmtree(os.path.join(PLUGIN_DIR, "__pycache__"), ignore_errors=True)
psrc = os.path.join(SKILL_DIR, "plugin")
if os.path.isdir(psrc):
    for fn in os.listdir(psrc):
        if fn == "__pycache__": continue
        sf = os.path.join(psrc, fn)
        if os.path.isfile(sf): shutil.copy2(sf, os.path.join(PLUGIN_DIR, fn))
    pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
    if os.path.exists(pyf): os.utime(pyf, None)
sv = pv = "?"
with open(os.path.join(SKILL_DIR,"SKILL.md")) as f:
    for l in f:
        if l.startswith("version:"): sv = l.split(":",1)[1].strip(); break
with open(os.path.join(PLUGIN_DIR,"plugin.yaml")) as f:
    for l in f:
        if l.startswith("version:"): pv = l.split(":",1)[1].strip(); break
log(f"peer70: SKILL={sv} PLUGIN={pv}")
import pathlib; pathlib.Path(os.path.expanduser("~/.hermes/capreuse-v243-peer70.done")).write_text("done")

# Remote peers via SCP/SSH
PEERS_SSH = {
    "peer84":  {"host":"192.168.178.84",  "user":"fausto",     "pw":"ccll4372", "home":"/home/fausto"},
    "peer106": {"host":"192.168.178.106", "user":"root",       "pw":"ccll4372", "home":"/root"},
    "peer138": {"host":"192.168.178.138", "user":"root",       "pw":"ccll4372", "home":"/root"},
}
PEERS_API = {
    "peer58":  {"host":"192.168.178.58",  "key":"AJAxMy0K_FGSuD2SgA_dzaGHz-6at_xWvGOkvHjduEU"},
}

for name, info in PEERS_SSH.items():
    log(f"=== {name} via SSH ===")
    try:
        r = subprocess.run(["sshpass", "-p", info["pw"], "ssh", "-o", "StrictHostKeyChecking=no",
            f"{info['user']}@{info['host']}", f"mkdir -p {info['home']}/.hermes/plugins/capability-reuse/"],
            capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            log(f"{name}: SSH mkdir FAIL - {r.stderr[:100]}"); continue
        r = subprocess.run(["sshpass", "-p", info["pw"], "scp", "-o", "StrictHostKeyChecking=no",
            ARTIFACT, f"{info['user']}@{info['host']}:/tmp/"],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log(f"{name}: SCP FAIL - {r.stderr[:100]}"); continue
        r = subprocess.run(["sshpass", "-p", info["pw"], "ssh", "-o", "StrictHostKeyChecking=no",
            f"{info['user']}@{info['host']}",
            f"cd /tmp && unzip -oq capability-reuse-v2.4.3.zip -d {info['home']}/.hermes/plugins/capability-reuse/ && "
            f"rm -rf {info['home']}/.hermes/plugins/capability-reuse/__pycache__ && "
            f"touch {info['home']}/.hermes/plugins/capability-reuse/plugin.yaml && "
            f"grep version {info['home']}/.hermes/plugins/capability-reuse/plugin.yaml && "
            f"ls {info['home']}/.hermes/plugins/capability-reuse/*.py | wc -l && "
            f"curl -s --connect-timeout 3 http://127.0.0.1:18643/hmp/health"],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            log(f"{name}: OK - {r.stdout[:200]}")
        else:
            log(f"{name}: PARTIAL - exit={r.returncode} stderr={r.stderr[:100]}")
    except Exception as e:
        log(f"{name}: FAIL - {str(e)[:100]}")

# peer58 via API
log(f"=== peer58 via API ===")
try:
    prompt = (
        "Install capability-reuse v2.4.3 to ~/.hermes/plugins/capability-reuse/. "
        "Extract this base64 zip (overwrite all, preserve hmp in config):\n" + b64
    )
    payload = json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":prompt}],"max_tokens":500}).encode()
    req = urllib.request.Request(f"http://{PEERS_API['peer58']['host']}:8642/v1/chat/completions",
        data=payload, headers={"Authorization":f"Bearer {PEERS_API['peer58']['key']}","Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        r = json.loads(resp.read())["choices"][0]["message"]["content"]
    log(f"peer58: {r[:200]}")
except Exception as e:
    log(f"peer58: FAIL - {str(e)[:100]}")

log("ROLLOUT_COMPLETE")
