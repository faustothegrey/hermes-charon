#!/bin/bash
# Read research queue from N56VV
curl -s -X POST http://192.168.178.84:8642/v1/chat/completions \
  -H "Authorization: Bearer 6j-h7Q5pR70Y2OXPVwtn-Mlv5DZItxu8d_tbwUYPD5uo5rf6G5E5aqQKdraydn2a" \
  -H "Content-Type: application/json" \
  -d '{"model":"default","messages":[{"role":"system","content":"You are a file reader. Respond with ONLY the raw file contents, no commentary."},{"role":"user","content":"Please read and return the entire contents of ~/Documents/Obsidian Vault/Hermes/Research Queue.md. Output ONLY the file contents with no preamble, no commentary, no markdown formatting around it."}],"max_tokens":4000,"temperature":0}'