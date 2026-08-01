#!/usr/bin/env python3
"""Fetch the Research Queue from peer84 (N56VV)."""
import json
import urllib.request

api_key = "6j-h7Q5pR70Y2OXPVwtn-Mlv5DZItxu8d_tbwUYPD5uo5rf6G5E5aqQKdraydn2a"
url = "http://192.168.178.84:8642/v1/chat/completions"

payload = {
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": "You are a file reader assistant. Execute shell commands when instructed."},
        {"role": "user", "content": "Please read the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md and return ONLY the raw file contents, with no additional commentary or markdown formatting. Just the raw file text."}
    ],
    "tools": [{
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a shell command and return its output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    }],
    "tool_choice": {"type": "function", "function": {"name": "execute_command"}}
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, method="POST")
req.add_header("Authorization", f"Bearer {api_key}")
req.add_header("Content-Type", "application/json")

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        print(body)
except Exception as e:
    print(f"ERROR: {e}")