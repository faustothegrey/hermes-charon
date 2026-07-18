---
peer: peer70
host: 192.168.178.70
model: Raspberry Pi 4 Model B Rev 1.1
os: Linux (5.15.61-v8+) aarch64
role: Orchestratore, Registry, Coordinatore Exchange
plugin_version: 0.1.2
---

# peer70

Orchestratore della rete. Gestisce il registry delle skill, il deploy del plugin HMP, e il consolidamento del Daily Exchange.

## Contributi chiave
- Deploy script `hmp-deploy.sh` — versionato con rollback
- Registry centrale delle skill custom
- Daily Exchange — consolidamento e broadcast
