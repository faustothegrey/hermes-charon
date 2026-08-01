#!/usr/bin/env python3
"""Pull capability-reuse v2.3.0 from peer106 and apply to peer70."""
import json, urllib.request, base64, zipfile, io, os, shutil, hashlib, sys

MARKER = os.path.expanduser("~/.hermes/capreuse-v230-updated.done")
if os.path.exists(MARKER):
    print("ALREADY_DONE")
    sys.exit(0)

PEER106_HOST = "192.168.178.106"
PEER106_KEY = "0bbf626ae898168c042a0d69ea06d272dcb2dd6963e002454e402972f87ab186"
SKILL_DIR = os.path.expanduser("~/.hermes/skills/hermes/capability-reuse")
PLUGIN_DIR = os.path.expanduser("~/.hermes/plugins/capability-reuse")
REGISTRY_DIR = os.path.expanduser("~/.hermes/data/capability-registry")
REUSE_DIR = os.path.expanduser("~/.hermes/data/reuse-observer")

prompt = (
    "Send the COMPLETE content of your capability-reuse v2.3.0 plugin files as a base64 zip. "
    "The plugin is at ~/.hermes/skills/hermes/capability-reuse/plugin/ (or ~/.hermes/plugins/capability-reuse/). "
    "Use Python: import base64, zipfile, io\n"
    "buf = io.BytesIO()\n"
    "with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:\n"
    "    import os\n"
    "    plugin_dir = os.path.expanduser('~/.hermes/plugins/capability-reuse/')\n"
    "    for f in os.listdir(plugin_dir):\n"
    "        if f != '__pycache__':\n"
    "            z.write(os.path.join(plugin_dir, f), arcname=f)\n"
    "encoded = base64.b64encode(buf.getvalue()).decode()\n"
    "print(encoded)\n\n"
    "Run that code and output ONLY the base64 string, nothing else."
)

payload = json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":prompt}],"max_tokens":50000}).encode()
req = urllib.request.Request(
    "http://{}:8642/v1/chat/completions".format(PEER106_HOST),
    data=payload,
    headers={"Authorization":"Bearer {}".format(PEER106_KEY),"Content-Type":"application/json"}
)
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
    # Extract base64 from possible markdown fences
    b64 = content.strip()
    if "```" in b64:
        b64 = b64.split("```")[1].split("```")[0].strip()
        for prefix in ["python","json","text",""]:
            if b64.startswith(prefix):
                b64 = b64[len(prefix):].strip()
    # Decode and extract
    data = base64.b64decode(b64)
    # Verify it's a zip
    if data[:2] != b'PK':
        print("ERROR: not a zip file (first 2 bytes:", data[:4].hex(), ")")
        print("Content preview:", content[:200])
        sys.exit(1)
    # Extract to plugin dir
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    # Remove old __pycache__
    shutil.rmtree(os.path.join(PLUGIN_DIR, "__pycache__"), ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(PLUGIN_DIR)
    # Touch plugin.yaml
    pyf = os.path.join(PLUGIN_DIR, "plugin.yaml")
    if os.path.exists(pyf):
        os.utime(pyf, None)
    print("PLUGIN_EXTRACTED:", os.listdir(PLUGIN_DIR))
    # Update SKILL.md version
    skill_md = os.path.join(SKILL_DIR, "SKILL.md")
    if os.path.exists(skill_md):
        with open(skill_md) as f:
            old = f.read()
        new = old.replace("version: 2.2.0", "version: 2.3.0")
        if old != new:
            with open(skill_md, 'w') as f:
                f.write(new)
            print("SKILL_VERSION: 2.3.0")
except Exception as e:
    print("ERROR:", str(e))
    sys.exit(1)

# Create marker
with open(MARKER, 'w') as f:
    f.write('done at ' + __import__('time').strftime('%Y-%m-%d %H:%M:%S'))
print("DONE")
