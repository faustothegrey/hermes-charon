# LAN Health Checks Without Terminal Access

When the agent does not have a terminal tool (only browser + web tools), or when `web_extract` blocks private/internal IPs, use `browser_navigate` to check peer `/health` endpoints on the LAN.

## The Problem

```python
# ❌ This fails for private IPs like 192.168.178.x:
web_extract(urls=["http://192.168.178.105:8642/health"])
# → "Blocked: URL targets a private or internal network address"
```

## The Workaround

`browser_navigate` can reach internal LAN addresses directly:

```python
# ✅ This works:
browser_navigate(url="http://192.168.178.105:8642/health")
# → response: {"status": "ok", "platform": "hermes-agent"}
```

The response is returned as a browser page snapshot containing the JSON body as static text.

## Limitations

- The browser snapshot shows the raw JSON as StaticText, not parsed — you read it visually
- No HTTP status code is returned (unlike `curl -w "%{http_code}"`)
- Timeout is the browser's default (usually 30-60s)
- Works for `/health` and other GET-only endpoints; POST endpoints like `/v1/chat/completions` are not accessible this way

## When to Use

1. Agent has `browser` toolset but not `terminal` toolset
2. `web_extract` refuses private IPs (Firecrawl/web tool restriction)
3. Quick health-check pings during orchestrator handover
4. Verifying a peer is alive before creating cron jobs

## Example: Full Handover Health Verification

```python
# During orchestrator handover, verify all peers before committing:
peers = [
    ("peer105", "http://192.168.178.105:8642/health"),
    ("peer106", "http://192.168.178.106:8642/health"),
    ("n56vv",   "http://192.168.178.84:8642/health"),
]

for name, url in peers:
    result = browser_navigate(url=url)
    # Check snapshot for {"status": "ok"}
    # This tells you the peer is alive and its Hermes API server is running
```
