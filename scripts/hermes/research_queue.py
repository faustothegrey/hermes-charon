#!/usr/bin/env python3
"""
Research Queue Processor
Fetches the queue from peer84 (N56VV), parses it, dispatches top 2 items.
Uses HTTP to communicate with peers.
"""
import json
import urllib.request
import urllib.error
import sys
import os
import re
import time

# ----- Config -----
CONFIG_PATH = "/home/fausto/.hermes/scripts/peers_config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def make_api_request(host, port, api_key, messages, timeout=60, model="default"):
    """Send a chat completion request to a peer's Hermes API."""
    url = f"http://{host}:{port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "tools": [{
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Execute a shell command and return its output",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"}
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')[:500]}"}
    except Exception as e:
        return {"error": str(e)}

def check_health(host, port):
    """Check if a peer is online via /health endpoint (GET)."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("status") == "ok"
    except:
        return False

def extract_tool_call(response):
    """Extract the tool call result from a chat completion response."""
    if "error" in response:
        return None, response["error"]
    try:
        choice = response["choices"][0]
        if "message" in choice and "tool_calls" in choice["message"]:
            for tc in choice["message"]["tool_calls"]:
                if tc["function"]["name"] == "execute_command":
                    args = json.loads(tc["function"]["arguments"])
                    return args["command"], None
        # Fallback: get content
        if "message" in choice and choice["message"].get("content"):
            return choice["message"]["content"], None
        return None, "No tool call or content in response"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return None, f"Failed to parse response: {e}"

def send_simple_request(host, port, api_key, message_text, timeout=60, model="default"):
    """Send a text-only request (no tools) to get a simple response."""
    url = f"http://{host}:{port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": message_text}
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            content = resp_data["choices"][0]["message"]["content"]
            return content, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8')[:500]}"
    except Exception as e:
        return None, str(e)

# ----- Main Logic -----
config = load_config()
peer84 = config["peer84"]
peer105 = config["peer105"]
peer106 = config["peer106"]

print("=" * 60)
print("RESEARCH QUEUE PROCESSOR")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Step 1: Fetch the queue from peer84
print("\n[1] Fetching queue from peer84 (N56VV)...")
response = make_api_request(
    peer84["host"], peer84["port"], peer84["api_key"],
    messages=[
        {"role": "system", "content": "You are a file reader assistant. Execute shell commands when instructed."},
        {"role": "user", "content": "Please read the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md and return ONLY the raw file contents, with no additional commentary or markdown formatting. Just the raw file text."}
    ]
)

queue_content, error = extract_tool_call(response)
if error:
    print(f"  ERROR: {error}")
    sys.exit(1)

print(f"  Queue content:\n{queue_content}")
print()

# Step 2: Parse the queue - find pending items
lines = queue_content.strip().split('\n')
pending_items = []
current_item = None

for line in lines:
    line_stripped = line.strip()
    # Detect markdown list items or table rows
    if line_stripped.startswith('- ['):
        # Save previous item
        if current_item:
            pending_items.append(current_item)
        # Parse: - [ ] Title or - [x] Done
        status_match = re.match(r'-\s*\[([ x])\]\s*(.*)', line_stripped)
        if status_match:
            status = "pending" if status_match.group(1) == " " else "done"
            if status == "pending":
                current_item = {"text": status_match.group(2), "full_line": line_stripped, "lines": [line_stripped]}
            else:
                current_item = None
        else:
            current_item = None
    elif line_stripped.startswith('|') and line_stripped.endswith('|'):
        # Table row
        if current_item:
            current_item["lines"].append(line_stripped)
        else:
            pending_items.append({"text": line_stripped, "full_line": line_stripped, "lines": [line_stripped], "table_row": True})
            current_item = None
    else:
        current_item = None

# Also handle the case where the last item was pending
if current_item:
    pending_items.append(current_item)

# Filter out headers and empty
pending_items = [it for it in pending_items if it["text"] and not it["text"].startswith('---') and not it["text"].startswith('| Status')]

# Step 2b: Try to parse table format
# Look for a table with columns: Status, Item, Type, etc.
table_items = []
for item in pending_items:
    if item.get("table_row"):
        cells = [c.strip() for c in item["text"].strip('|').split('|')]
        if len(cells) >= 3:
            status = cells[0].strip().lower()
            if status in ("pending", "in progress", "todo", "backlog", " "):
                table_items.append({
                    "status": cells[0].strip(),
                    "item": cells[1].strip(),
                    "type": cells[2].strip() if len(cells) > 2 else "unknown",
                    "notes": cells[3].strip() if len(cells) > 3 else "",
                    "full_item": cells[1].strip()
                })

# Also parse markdown checklist format
checklist_items = []
for item in pending_items:
    if not item.get("table_row"):
        match = re.match(r'-\s*\[\s\]\s*(.+)', item["text"])
        if match:
            checklist_items.append({"item": match.group(1).strip(), "full_item": match.group(1).strip()})

print(f"[2] Parsed queue:")
print(f"  Table items found: {len(table_items)}")
print(f"  Checklist items found: {len(checklist_items)}")

# Use whichever format has items
if table_items:
    all_items = table_items
    source = "table"
elif checklist_items:
    all_items = checklist_items
    source = "checklist"
else:
    # Fallback: just use the raw text
    all_items = [{"item": t, "full_item": t} for t in pending_items[:5]]
    source = "raw"

# Filter to truly pending (not started) items
if source == "table":
    pending = [it for it in all_items if it["status"].lower() in ("pending", "todo", "backlog", " ", "")]
else:
    pending = all_items

print(f"  Pending items: {len(pending)}")
for i, it in enumerate(pending[:3]):
    print(f"    {i+1}. {it.get('item', it.get('full_item', '?'))}")

# Step 3: Take top 2 items
if len(pending) == 0:
    print("\n[3] No pending items. Nothing to do.")
    print("[SILENT]")
    sys.exit(0)

top2 = pending[:2]
print(f"\n[3] Processing top {len(top2)} items:")

dispatched = []
for i, item in enumerate(top2):
    item_text = item.get('item', item.get('full_item', str(item)))
    print(f"\n  Item {i+1}: {item_text}")
    
    # Determine type
    item_lower = item_text.lower()
    item_type = item.get('type', '').lower() if source == "table" else ""
    
    if 'youtube.com' in item_lower or 'youtu.be' in item_lower:
        item_type = "youtube"
    elif item_lower.startswith('web '):
        item_type = "web"
    
    # Check if item has a URL
    url_match = re.search(r'(https?://[^\s\)\]>]+)', item_text)
    item_url = url_match.group(1) if url_match else None
    
    if item_type == "youtube" or (item_url and ('youtube.com' in item_url or 'youtu.be' in item_url)):
        # YouTube -> dispatch to peer105
        yt_url = item_url or item_text
        print(f"    Type: YouTube -> dispatching to peer105 (RPi3B)")
        health = check_health(peer105["host"], peer105["port"])
        if health:
            print(f"    peer105: ONLINE")
            msg = f"Please transcribe and digest the following YouTube video. Send me the full transcript summary, key points, and any important takeaways. Video: {yt_url}"
            content, err = send_simple_request(peer105["host"], peer105["port"], peer105["api_key"], msg)
            if err:
                print(f"    ERROR dispatching to peer105: {err}")
            else:
                print(f"    Response from peer105: {content[:200]}...")
                print(f"    Full response: {content}")
                dispatched.append({"item": item_text, "peer": "peer105", "result": content[:500]})
        else:
            print(f"    peer105: OFFLINE - cannot dispatch")
            dispatched.append({"item": item_text, "peer": "peer105", "result": "OFFLINE"})
    
    elif item_type == "web" or (item_lower.startswith('web ')):
        # Web research -> dispatch to peer106
        query = item_text
        if item_lower.startswith('web '):
            query = item_text[4:].strip()
        print(f"    Type: Web Research -> dispatching to peer106 (ARMv8)")
        health = check_health(peer106["host"], peer106["port"])
        if health:
            print(f"    peer106: ONLINE")
            msg = f"Please research and summarize the following topic. Search the web, extract relevant information, and provide a comprehensive summary. Topic: {query}"
            content, err = send_simple_request(peer106["host"], peer106["port"], peer106["api_key"], msg)
            if err:
                print(f"    ERROR dispatching to peer106: {err}")
            else:
                print(f"    Response from peer106: {content[:200]}...")
                print(f"    Full response: {content}")
                dispatched.append({"item": item_text, "peer": "peer106", "result": content[:500]})
        else:
            print(f"    peer106: OFFLINE - cannot dispatch")
            dispatched.append({"item": item_text, "peer": "peer106", "result": "OFFLINE"})
    
    else:
        print(f"    Type: unknown - cannot determine where to dispatch")
        dispatched.append({"item": item_text, "peer": "none", "result": "UNKNOWN TYPE"})

# Step 4: Ask peer84 to mark items as "In Progress"
print(f"\n[4] Updating queue status on peer84...")
mark_text = "In Progress"
item_names = [d["item"] for d in dispatched]
mark_msg = (
    f"Please update the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md. "
    f"Mark the following items as '{mark_text}' (change their status from pending/backlog/todo to 'In Progress'):\n\n"
    + "\n".join(f"- {name}" for name in item_names)
    + "\n\nRead the file first, then edit it. Return the updated file contents."
)
response2 = make_api_request(
    peer84["host"], peer84["port"], peer84["api_key"],
    messages=[
        {"role": "system", "content": "You are a file editor assistant. Execute shell commands when instructed."},
        {"role": "user", "content": mark_msg}
    ]
)

result, error = extract_tool_call(response2)
if error:
    print(f"  ERROR updating queue: {error}")
else:
    print(f"  Update result: {result[:300]}...")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for d in dispatched:
    print(f"  - {d['item']}")
    print(f"    Dispatched to: {d['peer']}")
    print(f"    Result: {d['result'][:100]}")
print("=" * 60)
print("Done.")