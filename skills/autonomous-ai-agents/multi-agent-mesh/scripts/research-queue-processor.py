#!/usr/bin/env python3
"""
research-queue-processor.py — Cross-peer research queue automation.

Fetches the Research Queue from peer84 (N56VV), parses pending items,
dispatches YouTube URLs to peer105 and web research queries to peer106,
then updates the queue status on peer84.

Designed to run via delegate_task with toolsets=["terminal"] from a cron
context where terminal is blocked. Alternatively, run as a no_agent=True
pre-run cron script.

Usage:
    python3 research-queue-processor.py

Requires:
    - ~/.hermes/scripts/peers_config.json (peer84/105/106 host, port, api_key)
    - Network access to peer84:8642, peer105:8642, peer106:8642
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


# ----- Config Loading -----

CONFIG_PATH = Path.home() / ".hermes" / "scripts" / "peers_config.json"


def load_config():
    """Load peer API keys and connection info from peers_config.json."""
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ----- HTTP Helpers -----

def check_health(host, port, timeout=8):
    """Check if a peer's Hermes API server is reachable via /health (GET)."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return body.get("status") == "ok"
    except Exception:
        return False


def make_api_request(host, port, api_key, messages, timeout=60, model="default"):
    """Send a chat completion request to a peer's Hermes API, requesting a tool call.

    The peer must support the execute_command tool (standard for Hermes agents).
    Returns (command_text, error_message).
    """
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
                        "command": {"type": "string", "description": "Shell command"}
                    },
                    "required": ["command"]
                }
            }
        }],
        "tool_choice": {"type": "function", "function": {"name": "execute_command"}}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, str(e)

    try:
        choice = response["choices"][0]
        msg = choice.get("message", {})
        # Prefer tool call result
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                if tc["function"]["name"] == "execute_command":
                    args = json.loads(tc["function"]["arguments"])
                    return args["command"], None
        # Fallback: raw content
        content = msg.get("content", "")
        if content:
            return content, None
        return None, "No tool call or content in response"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return None, f"Failed to parse response: {e}"


def send_simple_request(host, port, api_key, message_text, timeout=90):
    """Send a simple text-only chat request. Returns (content, error)."""
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": message_text}],
        "max_tokens": 4000,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode())
            content = resp_data["choices"][0]["message"]["content"]
            return content, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, str(e)


# ----- Queue Parsing -----

def parse_queue(content):
    """Parse the Research Queue markdown file into pending/in-progress/completed lists."""
    lines = content.strip().split("\n")
    section = "unknown"
    pending = []
    in_progress = []
    completed = []

    for line in lines:
        stripped = line.strip()
        # Section headers
        if stripped.lower().startswith("## ") or stripped.lower().startswith("# "):
            header = stripped.lstrip("#").strip().lower()
            if "pending" in header:
                section = "pending"
            elif "in progress" in header:
                section = "in_progress"
            elif "completed" in header or "done" in header:
                section = "completed"
            else:
                section = "unknown"
            continue

        # Checklist items
        match = re.match(r"-\s*\[([ xX])\]\s*(.+)", stripped)
        if match:
            item_text = match.group(2).strip()
            checked = match.group(1).strip().lower() == "x"
            entry = {"text": item_text, "raw": stripped}

            if section == "completed" or checked:
                completed.append(entry)
            elif section == "in_progress":
                in_progress.append(entry)
            elif section == "pending":
                pending.append(entry)
            # Fallback: if no section header, empty checkbox = pending
            elif not checked:
                pending.append(entry)
            else:
                completed.append(entry)
            continue

        # Table rows: | Status | Item | Type | Notes |
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 3:
                status = cells[0].lower().strip()
                item = cells[1].strip()
                if status in ("pending", "todo", "backlog", " ", ""):
                    pending.append({"text": item, "raw": stripped, "type": cells[2].strip() if len(cells) > 2 else ""})
                elif status in ("in progress",):
                    in_progress.append({"text": item, "raw": stripped})
                elif status in ("completed", "done", "x"):
                    completed.append({"text": item, "raw": stripped})

    return pending, in_progress, completed


def classify_item(item):
    """Classify an item as 'youtube', 'web', or 'unknown'."""
    text = item["text"].lower()
    item_type = item.get("type", "").lower()

    if "youtube.com" in text or "youtu.be" in text:
        return "youtube"
    if item_type == "youtube":
        return "youtube"

    if text.startswith("web ") or item_type == "web":
        return "web"

    # Check for URL
    url_match = re.search(r"(https?://[^\s\)\]>]+)", text)
    if url_match:
        url = url_match.group(1).lower()
        if "youtube.com" in url or "youtu.be" in url:
            return "youtube"

    return "unknown"


# ----- Main Logic -----

def main():
    print("=" * 60)
    print("RESEARCH QUEUE PROCESSOR")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = load_config()
    peer84 = config["peer84"]
    peer105 = config.get("peer105", {})
    peer106 = config.get("peer106", {})

    if not peer105.get("api_key"):
        print("WARNING: peer105 has no api_key in peers_config.json")
    if not peer106.get("api_key"):
        print("WARNING: peer106 has no api_key in peers_config.json")

    # Step 1: Fetch the queue file from peer84
    print("\n[1] Fetching queue from peer84 (N56VV)...")
    queue_content, error = make_api_request(
        peer84["host"], peer84["port"], peer84["api_key"],
        messages=[
            {"role": "system", "content": "You are a file reader. Execute shell commands when instructed."},
            {"role": "user", "content": (
                "Read the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md "
                "and return ONLY the raw file contents, no commentary."
            )}
        ]
    )
    if error:
        print(f"  ERROR: {error}")
        sys.exit(1)
    print(f"  Queue file received ({len(queue_content)} chars)")

    # Step 2: Parse the queue
    print("\n[2] Parsing queue...")
    pending, in_progress, completed = parse_queue(queue_content)
    print(f"  Pending: {len(pending)}")
    print(f"  In Progress: {len(in_progress)}")
    print(f"  Completed: {len(completed)}")

    # Filter out items already marked as in_progress on peer84
    pending = [p for p in pending if p["text"] not in {ip["text"] for ip in in_progress}]

    if not pending:
        print("\n[3] No pending items. Nothing to dispatch.")
        print("[SILENT]")
        return

    # Step 3: Take top 2 items
    top2 = pending[:2]
    print(f"\n[3] Processing top {len(top2)} items:")

    dispatched = []
    for i, item in enumerate(top2):
        item_text = item["text"]
        item_type = classify_item(item)
        print(f"\n  Item {i+1}: {item_text}")
        print(f"    Type: {item_type}")

        if item_type == "youtube":
            # Dispatch to peer105
            if check_health(peer105["host"], peer105["port"]):
                print(f"    peer105: ONLINE → dispatching YouTube transcript")
                msg = (
                    f"Please transcribe and digest this YouTube video. "
                    f"Return a summary with key points, timestamped highlights. "
                    f"Video: {item_text}"
                )
                content, err = send_simple_request(
                    peer105["host"], peer105["port"],
                    peer105.get("api_key", ""), msg
                )
                if err:
                    print(f"    ERROR: {err}")
                else:
                    print(f"    ✅ Dispatched to peer105")
                    dispatched.append({"item": item_text, "peer": "peer105", "status": "dispatched"})
            else:
                print(f"    peer105: OFFLINE — skipped")
                dispatched.append({"item": item_text, "peer": "peer105", "status": "offline"})

        elif item_type == "web":
            # Extract query (strip "web " prefix)
            query = item_text
            if query.lower().startswith("web "):
                query = query[4:].strip()
            # Dispatch to peer106
            if check_health(peer106["host"], peer106["port"]):
                print(f"    peer106: ONLINE → dispatching web research")
                msg = (
                    f"Please research and summarize the following topic. "
                    f"Search the web, extract relevant information, "
                    f"and provide a comprehensive summary with sources. "
                    f"Topic: {query}"
                )
                content, err = send_simple_request(
                    peer106["host"], peer106["port"],
                    peer106.get("api_key", ""), msg
                )
                if err:
                    print(f"    ERROR: {err}")
                else:
                    print(f"    ✅ Dispatched to peer106")
                    dispatched.append({"item": item_text, "peer": "peer106", "status": "dispatched"})
            else:
                print(f"    peer106: OFFLINE — skipped")
                dispatched.append({"item": item_text, "peer": "peer106", "status": "offline"})

        else:
            print(f"    Unknown type — cannot dispatch")
            dispatched.append({"item": item_text, "peer": "none", "status": "unknown_type"})

    # Step 4: Update queue status on peer84
    if dispatched:
        print(f"\n[4] Updating queue status on peer84...")
        item_names = "\n".join(f"- {d['item']}" for d in dispatched)
        update_msg = (
            f"Edit the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md. "
            f"Mark the following items as 'In Progress' (move them from Pending to "
            f"In Progress section, or change their status indicator):\n\n"
            f"{item_names}\n\n"
            f"Read the file first, then make the edit. Confirm the edit was applied "
            f"by reporting the update."
        )
        result, error = make_api_request(
            peer84["host"], peer84["port"], peer84["api_key"],
            messages=[
                {"role": "system", "content": "You are a file editor. Execute shell commands when instructed."},
                {"role": "user", "content": update_msg}
            ],
            timeout=120
        )
        if error:
            print(f"  WARNING: queue status update may have failed: {error}")
        else:
            print(f"  Queue updated")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for d in dispatched:
        icon = {"dispatched": "✅", "offline": "⏸️", "unknown_type": "❓"}.get(d["status"], "❓")
        print(f"  {icon} {d['item']} → {d['peer']} ({d['status']})")
    print("=" * 60)


if __name__ == "__main__":
    main()