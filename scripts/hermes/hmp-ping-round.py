#!/usr/bin/env python3
"""hmp-ping-round.py — HMP health check a tutti i peer, uno alla volta (staggered).

Scrive i risultati in ~/.hermes/peer-network/hmp_health_status.json
per essere letti da netboard.py e altri dashboard.

Esecuzione: ogni 10 minuti via cron job Hermes (no_agent: true).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
PEER_HMP_MAP = [
    ("peer70",  "127.0.0.1",    "Orchestratore (questo nodo)"),
    ("peer84",  "192.168.178.84",  "N56VV"),
    ("peer106", "192.168.178.106", "Fedora30 ARM"),
    ("peer128", "192.168.178.112", "MacBook"),
    ("peer58",  "192.168.178.58",  "HMP peer"),
]

HMP_PORT = 18643
TIMEOUT_SEC = 8
STAGGER_GAP_SEC = 3  # pausa tra un peer e l'altro
OUTPUT_FILE = Path.home() / ".hermes" / "peer-network" / "hmp_health_status.json"


def hmp_health(ip: str, timeout: int = TIMEOUT_SEC) -> dict:
    """Probe /hmp/health su un peer. Restituisce stato e tempi."""
    url = f"http://{ip}:{HMP_PORT}/hmp/health"
    start = time.monotonic()
    try:
        r = subprocess.run(
            ["curl", "-sf", "--connect-timeout", str(timeout), "--max-time", str(timeout + 2), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        if r.returncode == 0:
            try:
                payload = json.loads(r.stdout)
                return {
                    "reachable": True,
                    "ms": elapsed_ms,
                    "node_id": payload.get("node_id", "?"),
                    "gateway": payload.get("gateway_adapter", False),
                    "raw": payload,
                }
            except json.JSONDecodeError:
                return {"reachable": True, "ms": elapsed_ms, "node_id": "?", "gateway": False}
        else:
            return {"reachable": False, "ms": None, "error": f"curl exit {r.returncode}"}
    except subprocess.TimeoutExpired:
        return {"reachable": False, "ms": None, "error": "timeout"}
    except Exception as e:
        return {"reachable": False, "ms": None, "error": str(e)}


def main():
    timestamp = datetime.now(timezone.utc).isoformat()
    results = []
    all_ok = True

    print(f"[{timestamp}] HMP ping round — {len(PEER_HMP_MAP)} peers")
    sys.stdout.flush()

    for name, ip, desc in PEER_HMP_MAP:
        # Salta se stesso via localhost — è il nodo corrente
        if ip in ("127.0.0.1", "localhost"):
            result = {"reachable": True, "ms": 0, "node_id": name, "gateway": True, "self": True}
        else:
            print(f"  → {name} ({ip}:{HMP_PORT})...", end=" ", flush=True)
            result = hmp_health(ip)
            icon = "✅" if result.get("reachable") else "❌"
            ms = f"{result.get('ms', '?')}ms" if result.get("ms") else ""
            err = result.get("error", "")
            print(f"{icon} {ms} {err}".strip())
            sys.stdout.flush()
            if not result.get("reachable"):
                all_ok = False
            # Stagger: pausa tra un peer e l'altro
            time.sleep(STAGGER_GAP_SEC)

        results.append({
            "name": name,
            "ip": ip,
            "desc": desc,
            "hmp": result,
            "probed_at": timestamp,
        })

    # Scrittura atomica: scrivi su tmp, poi rinomina
    output = {
        "updated_at": time.time(),
        "updated_at_iso": timestamp,
        "all_reachable": all_ok,
        "peers": results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, indent=2), encoding="utf-8")
    tmp.rename(OUTPUT_FILE)

    ok_count = sum(1 for r in results if r["hmp"].get("reachable"))
    print(f"✅ HMP ping round completato: {ok_count}/{len(results)} peers raggiungibili")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
