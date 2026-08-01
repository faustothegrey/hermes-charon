#!/usr/bin/env python3
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from register_capability import register, CAPABILITIES

for name in ["hmp-healthcheck", "hmp-send", "peer-heartbeat"]:
    register(CAPABILITIES[name])

reg = json.loads((Path.home() / ".hermes" / "data" / "capability-registry" / "registry.json").read_text())
print(f"\nRegistry has {len(reg['capabilities'])} capabilities:")
for c in reg["capabilities"]:
    m = c["retrieval_metadata"]
    print(f"  ✅ {m['capability_id']} v{m['version']} — {m['name']}")
