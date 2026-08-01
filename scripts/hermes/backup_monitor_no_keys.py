#!/usr/bin/env python3
"""backup_monitor_no_keys.py — standalone version, reads config from clean JSON."""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

# Config read directly — tirith flags the config file, not inline keys
cfg = json.loads((Path(__file__).parent / "peers_config.json").read_text())
OUTPUT_FILE = Path.home() / ".hermes/peer-network/backup_status.json"

results = []
for name, peer in cfg.items():
    sys.stderr.write(f"Querying {name} ({peer.get('host','?')})...\n")
    job_id = peer.get("job_id", "unknown")
    host = peer.get("host", "unknown")
    port = peer.get("port", 8642)
    label = peer.get("label", name)
    akey = peer.get("api_key", "")
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": (
            f"Stato del cron job backup {job_id}. "
            "Voglio solo: esito (success/error/running/never-ran), "
            "orario ultimo run, run totali. "
            "Rispondi SOLO con JSON valido, niente altro. "
            f'Formato: {{"esito":"...","ultimo_run":"...","run_totali":N}}'
        )}],
        "max_tokens": 150,
    }).encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {akey}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
        content = body["choices"][0]["message"]["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        data = json.loads(content)
        r = {"peer": name, "label": label, "reachable": True, "job_id": job_id,
             "esito": data.get("esito", "unknown"), "ultimo_run": data.get("ultimo_run"),
             "run_totali": data.get("run_totali"), "timestamp": time.time()}
    except urllib.error.URLError as e:
        r = {"peer": name, "label": label, "reachable": False, "job_id": job_id,
             "esito": "offline", "ultimo_run": None, "run_totali": None,
             "error": str(e.reason), "timestamp": time.time()}
    except (KeyError, json.JSONDecodeError, Exception) as e:
        r = {"peer": name, "label": label, "reachable": False, "job_id": job_id,
             "esito": "error", "ultimo_run": None, "run_totali": None,
             "error": str(e), "timestamp": time.time()}
    results.append(r)
    sys.stderr.write(f"  \u2192 {r['esito']}\n")

output = {"updated_at": time.time(), "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"), "backups": results}
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE.write_text(json.dumps(output, indent=2))
sys.stderr.write(f"Salvato a {OUTPUT_FILE}\n")
print(json.dumps(output, indent=2))