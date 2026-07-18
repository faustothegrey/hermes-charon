# Peer Network Template

Copy this file to `~/.hermes/memories/PEERS.md` and fill in your peers.

```markdown
# Peer Network — Orchestrated by <hostname>

## Peer conosciuti

| Nome    | IP               | Host             | OS                            | Ruolo           | Stato       |
|---------|------------------|------------------|-------------------------------|-----------------|-------------|
| peerXX  | 192.168.178.XX   | hostname         | OS details                    | **orchestratore** 🏆 | Online    |
| peerXX  | 192.168.178.XX   | hostname         | OS details                    | peer            | Online      |

## Altri dispositivi sulla LAN (scoperti da ARP)

Use `ip neigh show dev <interface>` to discover. Filter out `fe80::` and `fd00::` IPv6 addresses.

| IP               | MAC              | Hostname                     | Note            |
|------------------|------------------|------------------------------|-----------------|
| 192.168.178.XXX  | xx:xx:xx:xx:xx:xx | device.fritz.box             | Description     |

## Accesso SSH
- Tutti sulla subnet <subnet>
- Chiave <key_name> installata su <peers>
- Password (if shared): <password>

## Monitoraggio
- <orchestrator> esegue ping a tutti i peer ogni N ore (cronjob Hermes)
- Stato salvato in ~/.hermes/peer-network/STATUS.md
- Storico in ~/.hermes/peer-network/history.log
```
