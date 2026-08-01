#!/bin/bash
# Read the Research Queue from peer84 (N56VV)
curl -s -w "\n---HTTP_CODE:%{http_code}" \
  http://192.168.178.84:8642/v1/chat/completions \
  -H "Authorization: Bearer 6j-h7Q5pR70Y2OXPVwtn-Mlv5DZItxu8d_tbwUYPD5uo5rf6G5E5aqQKdraydn2a" \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
