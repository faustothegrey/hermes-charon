# Coordinator Transition: N56VV → peer70 (2026-07-11, updated 2026-07-11)

## Context
N56VV laptop was the original orchestrator but has thermal constraints (cooling windows). peer70 (RPi4, Debian 11, 24/7 operation) took over as coordinator.

## Fleet
- **peer70** (RPi4, 3.7GB RAM, 59GB disk) — new coordinator, Hermes v0.17.0
- **N56VV/peer84** (laptop, Ubuntu 22.04) — demoted to worker, cooling windows 02-03 + 11-19, Hermes v0.16.0
- **peer105** (RPi3B, Fedora 30, <1GB RAM) — YouTube transcript specialist
- **peer106** (ARMv8, Fedora 30, 939MB RAM, 81% disk) — web research specialist
- **peer128** (MacBook Pro, macOS) — portable, offline since Jul 6

## peer-mesh.yaml

```yaml
peers:
  peer70:
    url: http://192.168.178.70:8642
    api_key_env: HERMES_PEER_70_KEY
    role: coordinator
    capabilities: [hermes, lan, coordinator]
    notes: "Raspberry Pi 4, Debian 11, orchestratore 24/7"
  n56vv:
    url: http://192.168.178.84:8642
    api_key_env: HERMES_PEER_N56VV_KEY
    role: worker
    capabilities: [hermes, lan, heavy]
    notes: "N56VV laptop, Ubuntu 22.04, cooling windows 02-03 + 11-19"
  peer105:
    url: http://192.168.178.105:8642
    api_key_env: HERMES_PEER_105_KEY
    role: worker
    capabilities: [hermes, youtube, transcript]
    notes: "RPi 3B, Fedora 30 aarch64, YouTube transcript specialist"
  peer106:
    url: http://192.168.178.106:8642
    api_key_env: HERMES_PEER_106_KEY
    role: worker
    capabilities: [hermes, research, web]
    notes: "ARMv8, Fedora 30, web research specialist, low disk"
  peer128:
    url: http://192.168.178.128:8642
    api_key_env: HERMES_PEER_128_KEY
    role: worker
    capabilities: [hermes, macos]
    notes: "MacBook Pro, macOS, portatile — frequentemente offline"
```

## Cron Jobs on peer70

| Job | ID | Schedule | Type |
|-----|----|----------|------|
| peer105 heartbeat | a92f69092c39 | hourly | no_agent script |
| peer106 heartbeat | 13fb62c23bc5 | hourly | no_agent script |
| peer128 keepalive | 49a77a64784c | every 2min | no_agent script |
| Peer Network Health Monitor | d5a456f87332 | hourly | no_agent script |
| Peer105+106 Research Queue | 01602cb5c3ba | 0,7,10,20,22 | agent-driven |
| Quest Advancement | c3a2cbbdf963 | every 4h | agent-driven |
| Weekly Peer Exchange | c3d45d4e8163 | Fri 10:00 | agent-driven |
| email-test-virgilio | 79bfa1bc158e | 2026-07-12T08:01 (once) | Retry test email |

## Jobs KEPT on N56VV (thermal/cooling only)
heavy-load-watchdog, cooling periods, thermal snapshots, Hermes config backup

## Services Migrated to peer70

### Himalaya Email — Migrated via API Delegation from peer84
Config extracted sequentially: tool type → config path → config file → password file. IMAP works, SMTP blocked by Virgilio IP rate-limit ban.

## Resolved Issues (2026-07-11)
- peer105 API key: 29b06e40a65d7d9e1c4bdbd6dbab81f7585287336e612fa742e62222d95b8775 ✅
- peer106 API key: 0bbf626ae898168c042a0d69ea06d272dcb2dd6963e002454e402972f87ab186 ✅
- All keys stored in peers_config.json, peer-api-keys.json, and in memory