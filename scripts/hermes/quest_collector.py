#!/usr/bin/env python3
"""Quest collector script — run by cron pre-script. Makes API calls to N56VV.
Outputs quest file summary to stdout, which the cron agent reads as context."""

import json, os, sys, urllib.request, urllib.error
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "peers_config.json"
OUTPUT_DIR = Path.home() / ".hermes/quest-advancement"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_peer_config():
    return json.loads(CONFIG_PATH.read_text())

def ask_n56vv(system, user, max_tokens=8000):
    cfg = load_peer_config()["peer84"]
    api_key = cfg["api_key"]
    url = f"http://{cfg['host']}:{cfg['port']}/v1/chat/completions"
    payload = json.dumps({
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": max_tokens
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]

def main():
    print("=== QUEST COLLECTOR: Fetching from N56VV ===")
    try:
        result = ask_n56vv(
            "You are a helpful assistant on N56VV. Use terminal to list and read all .md quest files.",
            "Run: ls -la ~/Documents/Obsidian\\ Vault/Hermes/Quests/*.md and cat each file. Return ALL file contents with titles, status, and progress. Be thorough."
        )
        # Save for the agent to read
        (OUTPUT_DIR / "quests_raw.txt").write_text(result)
        print(json.dumps({"status": "ok", "quests_found": True, "output_saved_to": str(OUTPUT_DIR / "quests_raw.txt")}))
        print(result[:3000])  # first 3000 chars as preview
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()