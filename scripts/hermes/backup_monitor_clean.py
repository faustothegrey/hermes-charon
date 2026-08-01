#!/usr/bin/env python3
"""backup_monitor.py — query backup status from peers via API.
Reads peer config from peers_config.json to avoid inline secrets.
Saves results to ~/.hermes/peer-network/backup_status.json
"""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "peers_config.json"
OUTPUT_FILE = Path.home() / ".hermes/peer-network/backup_status.json"

def load_peer_config():
    return json.loads(CONFIG_PATH.read_text())

def query_peer_backup(name, cfg):
    payload = json.dumps({
        "model": "hermes-agent",
        "messages": [{"role": "user", "content": (
            f"Stato del cron job backup {cfg['job_id']}. "
            "Voglio solo: esito (success/error/running/never-ran), "
            "orario ultimo run, run totali. "
            "Rispondi SOLO con JSON valido, niente altro. "
            f'Formato: {{"esito":"...","ultimo_run":"...","run_totali":N}}'
        )}],
        "max_tokens": 150,
    }).encode()

    req = urllib.request.Request(
        f"http://{cfg['host']}:{cfg['port']}/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
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
        return {
            "peer": name, "label": cfg["label"], "reachable": True,
            "job_id": cfg["job_id"], "esito": data.get("esito", "unknown"),
            "ultimo_run": data.get("ultimo_run", None),
            "run_totali": data.get("run_totali", None),
            "timestamp": time.time(),
        }
    except urllib.error.URLError as e:
        return {
            "peer": name, "label": cfg["label"], "reachable": False,
            "job_id": cfg["job_id"], "esito": "offline",
            "ultimo_run": None, "run_totali": None,
            "error": str(e.reason), "timestamp": time.time(),
        }
    except (KeyError, json.JSONDecodeError, Exception) as e:
        return {
            "peer": name, "label": cfg["label"], "reachable": False,
            "job_id": cfg["job_id"], "esito": "error",
            "ultimo_run": None, "run_totali": None,
            "error": str(e), "timestamp": time.time(),
        }

def main():
    peers = load_peer_config()
    results = []
    for name, cfg in peers.items():
        print(f"Querying {name} ({cfg['host']})...", file=sys.stderr)
        t0 = time.time()
        result = query_peer_backup(name, cfg)
        elapsed = time.time() - t0
        results.append(result)
        print(f"  -> {result.get('esito', '?')} ({elapsed:.1f}s)", file=sys.stderr)

    output = {
        "updated_at": time.time(),
        "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "backups": results,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"Saved to {OUTPUT_FILE}", file=sys.stderr)
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
