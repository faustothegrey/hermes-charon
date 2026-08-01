#!/usr/bin/env python3
"""Process REGISTRY_PUBLISH for peer70."""
import json, sys
from pathlib import Path

reg_file = Path.home() / ".hermes" / "registry" / "registry.json"
peers_dir = Path.home() / ".hermes" / "registry" / "peers"
peers_dir.mkdir(parents=True, exist_ok=True)

manifest = {"peer":"peer70","host":"192.168.178.70","updated_at":"2026-07-27T14:00:02Z",
    "skills":[{"name":"hmp-anti-stallo","version":"1.2.0","category":".archive"},
              {"name":"capability-reuse","version":"2.1.0","category":"hermes"},
              {"name":"daily-exchange","version":"2.0.0","category":"hermes"},
              {"name":"hmp-talkshow","version":"2.0.0","category":"hermes"},
              {"name":"hermes-daily-exchange","version":"1.1.0","category":"software-development"},
              {"name":"hermes-hmp","version":"1.24.0","category":"software-development"},
              {"name":"tts-cast","version":"1.0.0","category":"software-development"}],
    "plugins":[{"name":"capability-reuse","version":"2.1.0","enabled":True},
               {"name":"hmp","version":"0.1.3","enabled":True}]}

# Save full manifest
peer_file = peers_dir / "peer70.json"
manifest["registry_updated_at"] = "2026-07-27T14:00:02Z"
peer_file.write_text(json.dumps(manifest, indent=2))

# Update registry index
registry = json.loads(reg_file.read_text())
registry["updated_at"] = "2026-07-27T14:00:02Z"
registry["peers"]["peer70"] = {
    "last_seen": "2026-07-27T14:00:02Z",
    "host": "192.168.178.70",
    "skills": [s["name"] for s in manifest["skills"]],
    "skill_count": len(manifest["skills"]),
    "plugins": [p["name"] for p in manifest["plugins"]],
    "plugins_detail": [f"{p['name']} v{p['version']}" for p in manifest["plugins"]],
    "plugin_deployed_at": "2026-07-27T14:00:02Z",
}
reg_file.write_text(json.dumps(registry, indent=2))

print(f"✅ peer70 registry updated")
print(f"   Skills: {len(manifest['skills'])} — {', '.join(s['name'] for s in manifest['skills'])}")
print(f"   Plugins: {len(manifest['plugins'])} — {', '.join(p['name'] for p in manifest['plugins'])}")
print(f"   Updated: 2026-07-27T14:00:02Z")
