#!/usr/bin/env python3
"""Deploy capability-reuse plugin from peer70 to peer128 via API delegation.
Runs every 1m but exits early if marker file exists."""
import json, urllib.request, base64, tarfile, io, os, sys

MARKER = os.path.expanduser("~/.hermes/deploy-cap-reuse-to-peer128.done")
if os.path.exists(MARKER):
    sys.exit(0)

PEER128_HOST = "192.168.178.112"
PEER128_API_KEY = "05d08de2c480511c1b6c775d5bbfac7063157b9bfccc07791da017f621975263"
PLUGIN_SRC = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse/plugin")

# 1. Tar + base64 the plugin files
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for fname in os.listdir(PLUGIN_SRC):
        if fname == "__pycache__":
            continue
        fpath = os.path.join(PLUGIN_SRC, fname)
        if os.path.isfile(fpath):
            tar.add(fpath, arcname=fname)
tar_data_b64 = base64.b64encode(buf.getvalue()).decode()

prompt_lines = [
    'Deploy the capability-reuse Hermes plugin to this machine.',
    '',
    '1. Extract this base64 tar.gz to ~/.hermes/plugins/capability-reuse/:',
    tar_data_b64,
    '',
    '2. Use Python: import base64, tarfile, io, os',
    '   data = base64.b64decode(THE_BASE64_ABOVE)',
    '   with tarfile.open(fileobj=io.BytesIO(data)) as tar:',
    '       tar.extractall(path=os.path.expanduser("~/.hermes/plugins/capability-reuse/"))',
    '',
    '3. Verify files are there: list ~/.hermes/plugins/capability-reuse/',
    '',
    '4. Check ~/.hermes/config.yaml. If capability-reuse is not in plugins.enabled, add it.',
    '   IMPORTANT: Do NOT modify or remove the hmp plugin. Only add capability-reuse.',
    '',
    '5. Restart the gateway:',
    '   On macOS: launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.hermes-gateway 2>/dev/null',
    '   Fallback: systemctl --user restart hermes-gateway 2>/dev/null',
    '',
    '6. Wait 5 seconds, then verify: curl -s http://127.0.0.1:18643/hmp/health',
    '',
    'Report the exact output of the /hmp/health verification and the file listing of ~/.hermes/plugins/capability-reuse/',
]
prompt = '\n'.join(prompt_lines)

payload = json.dumps({
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 2000,
}).encode()

req = urllib.request.Request(
    "http://{}:8642/v1/chat/completions".format(PEER128_HOST),
    data=payload,
    headers={
        "Authorization": "Bearer {}".format(PEER128_API_KEY),
        "Content-Type": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
        print("PEER128_RESPONSE:", content[:2000])
        # Create marker so this only runs once
        with open(MARKER, 'w') as f:
            f.write('done at ' + __import__('time').strftime('%Y-%m-%d %H:%M:%S'))
        print("DEPLOY_STATUS: COMPLETED")
except Exception as e:
    print("DEPLOY_ERROR:", str(e))
    sys.exit(1)
