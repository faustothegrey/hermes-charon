#!/usr/bin/env python3
import json, urllib.request, sys

config = json.load(open("/home/fausto/.hermes/scripts/peers_config.json"))
api_key = config["peer84"]["api_key"]
host = config["peer84"]["host"]
port = config["peer84"]["port"]

url = f"http://{host}:{port}/v1/chat/completions"

payload = {
    "model": "deepseek/deepseek-v4-flash",
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant on N56VV. Use the terminal to find and read all .md files in ~/Documents/Obsidian Vault/Hermes/Quests/. List all files found, then read each one in full. Return the complete file listing and contents."
        },
        {
            "role": "user",
            "content": "Please run: ls -la ~/Documents/Obsidian\\ Vault/Hermes/Quests/*.md and then cat each file, showing me the complete contents. I need to see the title, status, and progress of every quest."
        }
    ],
    "max_tokens": 8000
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        # Save to file for inspection
        with open("/tmp/quests_response.json", "w") as f:
            json.dump(data, f, indent=2)
        print(content)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    if hasattr(e, 'read'):
        body = e.read().decode()
        print(f"Response: {body}", file=sys.stderr)
    sys.exit(1)
