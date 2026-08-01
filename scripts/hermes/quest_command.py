#!/usr/bin/env python3
"""quest_command.py - standalone script that reads config at runtime.
No inline secrets. Called directly from terminal."""
import json, os, sys, urllib.request
CFG = json.load(open(os.path.join(os.path.dirname(__file__), "peers_config.json")))
C = CFG["peer84"]
U = f"http://{C['host']}:{C['port']}/v1/chat/completions"
P = json.dumps({"model":"deepseek/deepseek-v4-flash","messages":[{"role":"system","content":"You are on N56VV. Use terminal to find and read all .md files in ~/Documents/Obsidian Vault/Hermes/Quests/."},{"role":"user","content":"List all quest files, cat each one. Return ALL titles, status, and progress."}],"max_tokens":8000}).encode()
R = urllib.request.Request(U, data=P, headers={"Content-Type":"application/json","Authorization":f"Bearer {C['api_key']}"})
with urllib.request.urlopen(R, timeout=120) as R2:
    O = json.loads(R2.read())["choices"][0]["message"]["content"]
    open("/tmp/quests_result_raw.txt","w").write(O)
    print(O)
