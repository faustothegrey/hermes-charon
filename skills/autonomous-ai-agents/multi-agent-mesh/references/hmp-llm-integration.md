# HMP + LLM Integration

Connect the HMP Worker Agent to an LLM (Hermes, OpenAI, etc.) for conversational message handling.

## When to Use

- A peer has Hermes installed (`which hermes`) or API access
- You want the worker to generate real LLM responses instead of canned echo/pong
- Payload types: `chat`, `conversation`, or any free-form text

## Hermes CLI Non-Interactive Mode

```bash
hermes chat -q "your prompt here" -Q --max-turns 1
```

| Flag | Purpose |
|------|---------|
| `-q "..."` | Single query (non-interactive mode) |
| `-Q` | Quiet mode: suppress banner, spinner, tool previews |
| `--max-turns 1` | One response only (no follow-up loop) |

Output: the model's response text to stdout.

## Worker Script with LLM Handler

Place at `/usr/local/bin/worker_h.py` or similar:

```python
#!/usr/bin/env python3
import sys, os, json, subprocess, importlib.util

# Load hmp.py as module (avoid executing its __main__)
spec = importlib.util.spec_from_file_location("hmp", "/usr/local/bin/hmp.py")
hmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hmp)

HMPWorker = hmp.HMPWorker
HMPBus = hmp.HMPBus
HMPClient = hmp.HMPClient
load_config = hmp.load_config
STATE_COMPLETED = hmp.STATE_COMPLETED

def llm_handler(msg):
    """Handler for chat/conversation payload types. Calls Hermes."""
    payload = msg.get('payload', {}) or {}
    text = payload.get('text', payload.get('message', ''))
    if not text:
        text = json.dumps(payload)
    prompt = f"Sei {peer_name}, un nodo HMP. Rispondi in italiano: {text}"
    try:
        r = subprocess.run(
            ['hermes', 'chat', '-q', prompt, '-Q', '--max-turns', '1'],
            capture_output=True, text=True, timeout=120
        )
        resp = r.stdout.strip() or r.stderr.strip()[:200] or "..."
    except Exception as e:
        resp = f"Errore: {e}"
    return STATE_COMPLETED, {"type": "response", "text": resp}, None

def main():
    config = load_config()
    config['supported_types'] = ['chat', 'conversation', 'ping', 'health_report']
    bus = HMPBus(config['db_path'])
    worker = HMPWorker(bus, config, client=HMPClient(), poll_interval=3)
    worker.register_handler('chat', llm_handler)
    worker.register_handler('conversation', llm_handler)
    print("[WORKER+LLM] Avviato")
    worker.run_forever()

if __name__ == '__main__':
    main()
```

## Direct API Call (No Hermes CLI)

When Hermes CLI is unavailable but API access exists:

```python
import openai, os

# Load API key from .env
for p in ["/usr/local/lib/hermes-agent/.env", "/root/.hermes/.env"]:
    if os.path.exists(p):
        for line in open(p):
            if "OPENROUTER_API_KEY" in line and "=" in line:
                key = line.split("=",1)[1].strip().strip('"').strip("'")
                break

client = openai.OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
resp = client.chat.completions.create(
    model="openai/gpt-4.1-nano",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=200
)
print(resp.choices[0].message.content)
```

## Deploying the LLM Worker

```bash
# Kill old worker, start LLM worker
pkill -f 'worker_h.py' 2>/dev/null
nohup python3 /usr/local/bin/worker_h.py > /root/.hermes/data/hmp/worker.log 2>&1 &

# Verify
ps aux | grep worker_h
```

## Systemd Service

```ini
[Unit]
Description=HMP Worker + LLM
After=hmp-server.service
Requires=hmp-server.service

[Service]
Type=simple
ExecStart=/usr/local/bin/python3 /usr/local/bin/worker_h.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

## Testing

```python
import json, urllib.request, time
msg = {
    'hmp_version': '1.0',
    'message_id': f'test_llm_{int(time.time())}',
    'idempotency_key': f'test_llm_{int(time.time())}',
    'from': 'peer70', 'to': 'peer106',
    'type': 'request',
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'payload': {'type': 'chat', 'text': 'Ciao! Come va?'},
}
data = json.dumps(msg).encode()
req = urllib.request.Request('http://<peer-ip>:8643/hmp/send', data=data,
    headers={'Content-Type': 'application/json'})
print(json.loads(urllib.request.urlopen(req, timeout=10).read()))
# Wait ~15s for Hermes to respond, then check sender's bus for the response
```

## Graceful Fallback Pattern (No Hermes)

When a peer doesn't have Hermes CLI installed, the worker should fall back to pong/echo instead of crashing:

```python
import shutil
HAVE_HERMES = shutil.which('hermes') is not None

def handler(msg):
    payload = msg.get('payload', {}) or {}
    text = payload.get('text', payload.get('message', ''))
    if not text:
        return STATE_COMPLETED, {"type": "pong", "echo": payload}, None
    if HAVE_HERMES:
        prompt = f"Sei un peer HMP. Rispondi in italiano: {text}"
        resp = ask_llm(prompt)
        if resp:
            return STATE_COMPLETED, {"type": "response", "text": resp}, None
    return STATE_COMPLETED, {"type": "pong", "echo": text}, None
```

This pattern:
- Detects Hermes availability at startup (single `shutil.which` call)
- Returns LLM response when available, plain echo otherwise
- Never crashes due to missing binary
- Works identically on Linux ARM, x86, and macOS

See `scripts/hmp-worker-llm.py` for the complete universal worker script.

## macOS Deployment (screen)

On macOS, background processes via `nohup ... &` often die when the SSH session ends. Use `screen`:

```bash
screen -dmS hmp-worker python3 /Users/fausto/worker_llm.py
```

The worker runs in a detached screen session. To check: `screen -list | grep hmp-worker`. To attach and see logs: `screen -r hmp-worker`.

The script auto-detects the platform and sets `hmp_path`:
```python
HMP_PATH = "/usr/local/bin/hmp.py"
if not os.path.exists(HMP_PATH):
    HMP_PATH = os.path.expanduser("~/hmp.py")  # fallback for macOS
```

## Finding Hermes in Non-Standard Paths

`shutil.which('hermes')` fails when Hermes is installed in paths not in the SSH/sytemd `PATH`:
- Ubuntu: `/home/fausto/.local/bin/hermes`
- macOS: `/Users/fausto/.local/bin/hermes`
- Homebrew: `/opt/homebrew/bin/hermes`

The universal worker script (`scripts/hmp-worker-llm.py`) implements a `_find_hermes()` function that checks these common locations as fallback:

```python
def _find_hermes():
    h = shutil.which('hermes')
    if h: return h
    for d in ['/home/fausto/.local/bin', '/Users/fausto/.local/bin',
              '/usr/local/bin', '/opt/homebrew/bin']:
        p = os.path.join(d, 'hermes')
        if os.path.isfile(p): return p
    return None
```

Additionally, the `subprocess.run` call passes an augmented `PATH` env var so that Hermes can find its own dependencies:

```python
env={**os.environ, 'PATH': '/home/fausto/.local/bin:/Users/fausto/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin'}
```

Without this, systemd services and screen sessions fail to locate Hermes even when the binary is present.

## Pitfalls

- **Timeout**: Hermes API calls can take 30-120s. Worker poll interval should be 3-5s, but handler timeout set to 120s.
- **Concurrent requests**: The worker processes one message at a time. If Hermes takes 60s, subsequent messages queue up.
- **importlib vs exec**: Use `importlib.util.spec_from_file_location()` to load hmp.py as a module. Using `exec(compile(...))` triggers `if __name__ == '__main__'` which runs the default server.
- **State transition**: Ensure `STATE_WORKING` is in `TRANSITIONS[STATE_PENDING]` (added in protocol v1.0). Otherwise the worker loops processing the same message repeatedly.
- **macOS nohup caveat**: `nohup ... &` inside an SSH command may not survive SSH disconnect on macOS. Always use `screen -dmS` or a LaunchAgent for persistence.
