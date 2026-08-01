#!/usr/bin/env python3
"""Script run by quest-advancement cron job on peer70. API calls to N56VV."""
import json, urllib.request, sys, os

# Read peers config
config_dir = "/home/fausto/.hermes/scripts"
config = json.load(open(os.path.join(config_dir, "peers_config.json")))
api_key = config["peer84"]["api_key"]
host = config["peer84"]["host"]
port = config["peer84"]["port"]

url = f"http://{host}:{port}/v1/chat/completions"

def ask_n56vv(system_prompt, user_message, max_tokens=8000):
    payload = {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": max_tokens
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]

# Step 1: Get quest files
print("=== STEP 1: Fetching quest files from N56VV ===")
quest_info = ask_n56vv(
    "You are a helpful assistant on N56VV.",
    "Run: ls -la ~/Documents/Obsidian\\ Vault/Hermes/Quests/*.md and then cat each file. I need the title, status, and progress of every quest. Return all file contents."
)
print(quest_info)
print("\n\n")

# Save for later processing
with open("/tmp/quests_raw_response.txt", "w") as f:
    f.write(quest_info)
print("Response saved to /tmp/quests_raw_response.txt")