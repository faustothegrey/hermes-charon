#!/usr/bin/env python3
from pathlib import Path
import json, subprocess, datetime, sys
PEERS = {
    "peer70": ("local", "/home/fausto"),
    "peer84": ("fausto@192.168.178.84", "/home/fausto"),
    "peer106": ("root@192.168.178.106", "/root"),
    "peer138": ("root@192.168.178.138", "/root"),
}
out = Path.home()/".hermes/data/reuse-aggregati"
peerdir = out/"peers"
peerdir.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
items = []
for peer, (target, home) in PEERS.items():
    rel = f"{home}/.hermes/data/reuse-aggregati/latest.json"
    try:
        if target == "local":
            text = Path(rel).read_text()
        else:
            cp = subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=8",target,"cat",rel], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or f"ssh rc {cp.returncode}")
            text = cp.stdout
        data = json.loads(text)
        data["collector_peer_id"] = peer
        (peerdir/f"{peer}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
        items.append({"peer_id": peer, "status": "ok", "generated_at": data.get("generated_at"), "events_processed": data.get("events_processed"), "retrieval_total": (data.get("retrieval") or {}).get("total"), "anomalies": data.get("anomalies", [])})
    except Exception as e:
        items.append({"peer_id": peer, "status": "fail", "error": str(e)[:300]})
summary = {"generated_at": now, "collector": "peer70", "peers": items, "ok_count": sum(1 for x in items if x.get("status")=="ok"), "fail_count": sum(1 for x in items if x.get("status")!="ok")}
(out/"fleet-latest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
