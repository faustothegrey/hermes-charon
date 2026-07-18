# Guardiano SSH — On-Demand Port Opening via iptables

## Peer: peer84 (N56VV laptop, Ubuntu 22.04, 192.168.178.84)

### Script: `~/.hermes/scripts/guardiano.sh`

Manages iptables rules with a 20-minute auto-expiry timer.

**Commands:**
| Command | Effect |
|---------|--------|
| `guardiano.sh open` | Open ports 2222 (SSH) and 3001 (Hermes API) via iptables, set 20-min expiry |
| `guardiano.sh close` | Remove iptables rules, clear state |
| `guardiano.sh status` | Show "APERTE (Xs rimanenti) — 2222 3001" or "CHIUSE" |
| `guardiano.sh keepalive` | Touch `/tmp/guardiano-keepalive` to reset timer |
| `guardiano.sh watchdog` | Run every minute via cron: applies keepalive or closes on expiry |

**Trigger phrases (via Hermes agent):**
- `"apriti sedano"` — agent runs `guardiano.sh open`, confirms with expiry time
- `"Sisisi"` — agent runs `guardiano.sh keepalive`
- `"chiudi sedano"` — agent runs `guardiano.sh close`

### Router Config

The router (FRITZ!Box, likely) has a permanent port-forward rule pointing to `192.168.178.84`. The *external* port number is unknown — only the internal target `:2222` is known. Port 3001 (Hermes API) is not forwarded from the router; it's only available on the LAN.

### API Access

- **Host:** `192.168.178.84:8642`
- **Key:** stored in `~/.hermes/peer-network/peer-api-keys.json`
- **Model:** `hermes-agent`
- **Response time:** 30-90 seconds (slow laptop, overheating issues)
- **API endpoint:** `POST /v1/chat/completions`
