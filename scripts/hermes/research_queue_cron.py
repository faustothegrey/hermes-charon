#!/usr/bin/env python3
"""Cron job: Process Research Queue from N56VV and dispatch to specialist peers."""

import json
import urllib.request
import urllib.error
import sys

CONFIG_PATH = "/home/fausto/.hermes/scripts/peers_config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def call_llm(host, port, api_key, messages, max_tokens=8192, model="default"):
    """Call an LLM endpoint and return the response content."""
    url = f"http://{host}:{port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]

def check_health(host, port):
    """Check if a peer is online via /health endpoint."""
    try:
        url = f"http://{host}:{port}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    config = load_config()
    peer84 = config["peer84"]
    peer106 = config["peer106"]

    # ── Step 1: Ask N56VV to read the queue file ──
    print("📋 Step 1: Fetching Research Queue from N56VV...")
    queue_content = call_llm(
        peer84["host"], peer84["port"], peer84["api_key"],
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Read the requested file and return its raw contents exactly as-is with no extra commentary."},
            {"role": "user", "content": "Read the file at ~/Documents/Obsidian Vault/Hermes/Research Queue.md and return its raw contents. Respond with ONLY the file contents, no extra commentary or markdown formatting."}
        ]
    )
    print(f"✅ Queue fetched ({len(queue_content)} chars)")
    print("─" * 60)
    print(queue_content)
    print("─" * 60)

    # ── Step 2: Parse the queue ──
    # Expected format: a markdown table or list with columns like Status, Item, Link/Notes
    # We'll ask the LLM on peer84 to parse the top 2 pending items for us
    print("\n🔍 Step 2: Parsing pending items...")
    parse_result = call_llm(
        peer84["host"], peer84["port"], peer84["api_key"],
        messages=[
            {"role": "system", "content": "You are a structured data extractor. Parse the research queue and return ONLY a JSON array. Each object must have: 'description' (short description of the item), 'type' ('youtube' if it's a YouTube URL, 'web' if it starts with 'web', or 'other'), 'url_or_query' (the full URL or query string). Include items that are NOT yet started (status: pending/to-do/backlog/not started). Return ONLY the top 2 such items as a JSON array, nothing else."},
            {"role": "user", "content": f"Parse this research queue and extract the top 2 unstarted items as JSON:\n\n{queue_content}"}
        ]
    )
    
    # Clean up JSON - remove markdown code fences if present
    clean_json = parse_result.strip()
    if clean_json.startswith("```"):
        # Remove code fences
        lines = clean_json.split("\n")
        clean_lines = [l for l in lines if not l.startswith("```")]
        clean_json = "\n".join(clean_lines)
    
    try:
        items = json.loads(clean_json)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON from response: {e}")
        print(f"Raw response:\n{parse_result}")
        sys.exit(1)
    
    if not items:
        print("✅ No pending items found. Nothing to do.")
        return

    print(f"🎯 Found {len(items)} pending item(s):")
    for item in items:
        print(f"   - [{item['type']}] {item['description']}: {item['url_or_query']}")

    # ── Step 3: Dispatch to specialist peers ──
    dispatched_items = []
    
    for item in items:
        item_type = item.get("type", "other")
        description = item.get("description", "Unknown")
        url_or_query = item.get("url_or_query", "")
        
        if item_type == "youtube":
            print(f"\n🎬 Dispatching YouTube item: {description}")
            # YouTube -> peer106 (peer105 removed 2026-08-17)
            # Check peer106 health first
            if not check_health(peer106["host"], peer106["port"]):
                print(f"❌ peer106 is offline. Skipping YouTube item.")
                continue
            
            result = call_llm(
                peer106["host"], peer106["port"], peer106["api_key"],
                messages=[
                    {"role": "system", "content": "You are a research specialist. Your job is to transcribe, summarize, and extract key insights from YouTube videos. For the given URL, fetch the transcript/subtitles (if available) and produce a structured digest: title, channel, duration (from description), key points/bullet summary, and any notable quotes or findings."},
                    {"role": "user", "content": f"Research this YouTube video and provide a detailed digest: {url_or_query}\n\nDescription: {description}"}
                ],
                max_tokens=4096
            )
            print(f"✅ YouTube digest received ({len(result)} chars)")
            print(result)
            dispatched_items.append(item)
            
        elif item_type == "web":
            print(f"\n🌐 Dispatching web research item: {description}")
            # Check peer106 health first
            if not check_health(peer106["host"], peer106["port"]):
                print(f"❌ peer106 (web research specialist) is offline. Skipping.")
                continue
            
            result = call_llm(
                peer106["host"], peer106["port"], peer106["api_key"],
                messages=[
                    {"role": "system", "content": "You are a web research specialist. Your job is to search the web, extract content, and produce a structured summary on any given topic. Use your web search and extraction tools to gather current information. Produce a report with: key findings, sources, data points, and a brief synthesis."},
                    {"role": "user", "content": f"Research this topic thoroughly and provide a structured summary: {url_or_query}\n\nContext: {description}"}
                ],
                max_tokens=4096
            )
            print(f"✅ Web research received ({len(result)} chars)")
            print(result)
            dispatched_items.append(item)
        else:
            print(f"⚠️ Unknown item type '{item_type}', skipping: {description}")

    # ── Step 4: Ask N56VV to mark items as In Progress ──
    if dispatched_items:
        print("\n📝 Step 4: Marking items as In Progress on N56VV...")
        item_names = "\n".join([f"- {i['description']}" for i in dispatched_items])
        mark_result = call_llm(
            peer84["host"], peer84["port"], peer84["api_key"],
            messages=[
                {"role": "system", "content": "You are a file editor. Update the Research Queue file by marking the specified items as 'In Progress'. Read the file, apply the changes, and write it back. Confirm what was changed."},
                {"role": "user", "content": f"In the file ~/Documents/Obsidian Vault/Hermes/Research Queue.md, mark the following items as 'In Progress' (change their status from pending/backlog/not started to 'In Progress'):\n\n{item_names}\n\nRead the file, apply the changes, save the file, and confirm what you changed."}
            ]
        )
        print(f"✅ Mark result: {mark_result}")
    else:
        print("ℹ️ No items were dispatched, nothing to mark.")

    print("\n🏁 Done!")

if __name__ == "__main__":
    main()
