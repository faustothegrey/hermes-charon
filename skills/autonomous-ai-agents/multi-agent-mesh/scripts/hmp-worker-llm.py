#!/usr/bin/env python3
"""
HMP Worker with optional LLM support.
- If Hermes CLI is installed -> uses LLM for chat/conversation payloads
- If not -> graceful fallback to pong/echo
- Works on any peer (Linux ARM, x86, macOS) without modification

Install: cp to /usr/local/bin/worker_llm.py (Linux) or ~/worker_llm.py (macOS)
Run:    python3 /path/to/worker_llm.py
Systemd: see hmp-worker.service in multi-agent-mesh skill
Screen (macOS): screen -dmS hmp-worker python3 /Users/fausto/worker_llm.py
"""

import sys, os, json, subprocess, shutil, importlib.util

HMP_PATH = "/usr/local/bin/hmp.py"
if not os.path.exists(HMP_PATH):
    HMP_PATH = os.path.expanduser("~/hmp.py")  # fallback for macOS/homebrew

spec = importlib.util.spec_from_file_location("hmp", HMP_PATH)
hmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hmp)

HMPWorker = hmp.HMPWorker; HMPBus = hmp.HMPBus; HMPClient = hmp.HMPClient
load_config = hmp.load_config; STATE_COMPLETED = hmp.STATE_COMPLETED

def _find_hermes():
    h = shutil.which('hermes')
    if h: return h
    for d in ['/home/fausto/.local/bin', '/Users/fausto/.local/bin',
              '/usr/local/bin', '/opt/homebrew/bin']:
        p = os.path.join(d, 'hermes')
        if os.path.isfile(p): return p
    return None

HERMES_PATH = _find_hermes()
HAVE_HERMES = HERMES_PATH is not None

def ask_llm(prompt):
    if not HAVE_HERMES:
        return None
    try:
        r = subprocess.run(
            [HERMES_PATH, 'chat', '-q', prompt, '-Q', '--max-turns', '1'],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PATH': '/home/fausto/.local/bin:/Users/fausto/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin'}
        )
        return (r.stdout.strip() or r.stderr.strip()[:200] or None)[:500]
    except Exception as e:
        return f"[errore: {e}]"

def handler(msg):
    payload = msg.get('payload', {}) or {}
    text = payload.get('text', payload.get('message', ''))
    if not text:
        return STATE_COMPLETED, {"type": "pong", "echo": payload}, None
    if HAVE_HERMES:
        prompt = (f"Sei un peer HMP. Rispondi in modo colloquiale "
                  f"e breve in italiano: {text}")
        resp = ask_llm(prompt)
        if resp:
            return STATE_COMPLETED, {"type": "response", "text": resp}, None
    return STATE_COMPLETED, {"type": "pong", "echo": text}, None

def main():
    config = load_config()
    config['supported_types'] = [
        'chat', 'conversation', 'ping', 'health_report', 'code_review'
    ]
    bus = HMPBus(config['db_path'])
    worker = HMPWorker(bus, config, client=HMPClient(), poll_interval=3)
    worker.register_handler('chat', handler)
    worker.register_handler('conversation', handler)
    hermes_status = 'si' if HAVE_HERMES else 'no'
    print(f"[WORKER] Avviato su {config['peer_name']} (hermes={hermes_status})")
    worker.run_forever()

if __name__ == '__main__':
    main()
