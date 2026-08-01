#!/usr/bin/env python3
"""Deploy capability-reuse v2.1.0 from peer70 to peer128 (API) and peer138 (SCP)."""
import json, urllib.request, base64, tarfile, io, os, sys, subprocess

MARKER = os.path.expanduser("~/.hermes/deploy-capreuse-v210.done")
if os.path.exists(MARKER):
    print("ALREADY_DONE")
    sys.exit(0)

PLUGIN_SRC = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse/plugin")
SKILL_SRC = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
REGISTRY_SRC = os.path.expanduser("~/.hermes/data/capability-registry")
PLUGIN_FILES = ["__init__.py","plugin.yaml","protocol.py","event_store.py",
                "registry.py","compatibility.py","retriever.py","dispatcher.py"]

def tar_base64(paths):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in paths:
            if os.path.isfile(p):
                tar.add(p, arcname=os.path.basename(p))
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    for f in files:
                        fpath = os.path.join(root, f)
                        arc = os.path.relpath(fpath, os.path.dirname(p))
                        tar.add(fpath, arcname=arc)
    return base64.b64encode(buf.getvalue()).decode()

def deploy_to_peer128():
    """Send plugin+skill+registry to peer128 via API chat."""
    key = "05d08de2c480511c1b6c775d5bbfac7063157b9bfccc07791da017f621975263"
    host = "192.168.178.112"

    plugin_tar = tar_base64([os.path.join(PLUGIN_SRC, f) for f in PLUGIN_FILES])

    prompt = (
        "Deploy capability-reuse v2.1.0 to this peer. Steps:\n\n"
        "1. Extract this base64 tar.gz to ~/.hermes/plugins/capability-reuse/ (OVERWRITE all):\n"
        + plugin_tar + "\n\n"
        "2. import base64, tarfile, io, os\n"
        "   data = base64.b64decode(THE_BASE64)\n"
        "   with tarfile.open(fileobj=io.BytesIO(data)) as tar:\n"
        "       tar.extractall(path=os.path.expanduser('~/.hermes/plugins/capability-reuse/'))\n\n"
        "3. Remove __pycache__: import shutil; shutil.rmtree(os.path.expanduser('~/.hermes/plugins/capability-reuse/__pycache__'), ignore_errors=True)\n\n"
        "4. Touch plugin.yaml: import pathlib; pathlib.Path(os.path.expanduser('~/.hermes/plugins/capability-reuse/plugin.yaml')).touch()\n\n"
        "5. Restart gateway: launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.hermes-gateway 2>/dev/null || systemctl --user restart hermes-gateway 2>/dev/null\n\n"
        "6. Wait 5s, then verify: curl -s http://127.0.0.1:18643/hmp/health\n\n"
        "7. List: ls -la ~/.hermes/plugins/capability-reuse/\n\n"
        "Report health check output and file listing."
    )

    payload = json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":prompt}],"max_tokens":2000}).encode()
    req = urllib.request.Request("http://{}:8642/v1/chat/completions".format(host), data=payload,
        headers={"Authorization":"Bearer {}".format(key),"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
    print("PEER128:", content[:500])

def deploy_to_peer138():
    """SCP plugin files to peer138 via SSH (root password auth)."""
    pw = "ccll4372"
    remote_dir = "/root/.hermes/plugins/capability-reuse"
    # Build plugin files list
    plugin_dir = PLUGIN_SRC
    cmds = []
    # Create remote dir
    cmds.append("sshpass -p '{}' ssh -o StrictHostKeyChecking=no root@192.168.178.138 'mkdir -p {}'".format(pw, remote_dir))
    # SCP each file
    for fname in PLUGIN_FILES:
        local = os.path.join(plugin_dir, fname)
        cmds.append("sshpass -p '{}' scp -o StrictHostKeyChecking=no {} root@192.168.178.138:{}/".format(pw, local, remote_dir))
    # Remove __pycache__
    cmds.append("sshpass -p '{}' ssh -o StrictHostKeyChecking=no root@192.168.178.138 'rm -rf {}/__pycache__ && touch {}/plugin.yaml'".format(pw, remote_dir, remote_dir))
    # Restart gateway
    cmds.append("sshpass -p '{}' ssh -o StrictHostKeyChecking=no root@192.168.178.138 'systemctl --user restart hermes-gateway 2>/dev/null || systemctl restart hermes-gateway 2>/dev/null'".format(pw))
    # Verify health
    cmds.append("sleep 5")
    cmds.append("curl -s --connect-timeout 5 http://192.168.178.138:18643/hmp/health")
    # List files
    cmds.append("sshpass -p '{}' ssh -o StrictHostKeyChecking=no root@192.168.178.138 'ls -la {}'".format(pw, remote_dir))

    for cmd in cmds:
        print("CMD:", cmd[:120])
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = (result.stdout or "")[:300] + (result.stderr or "")[:100]
            print("  ->", out.strip()[:200])
        except Exception as e:
            print("  -> ERROR:", str(e)[:200])

# Run
print("=== Deploying to peer128 ===")
deploy_to_peer128()
print("\n=== Deploying to peer138 ===")
deploy_to_peer138()

# Create marker
with open(MARKER, 'w') as f:
    f.write('done at ' + __import__('time').strftime('%Y-%m-%d %H:%M:%S'))
print("\nDONE")
