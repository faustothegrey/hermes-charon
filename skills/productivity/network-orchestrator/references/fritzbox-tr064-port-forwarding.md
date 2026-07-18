# FritzBox TR-064 Port Forwarding Management

Manage AVM FritzBox port forwarding rules locally via the TR-064 protocol — no web UI needed.

## Prerequisites

```bash
pip install fritzconnection
```

## Available API Services

On a FRITZ!Box 7490, the following services handle port forwarding:

### `WANIPConn1` (read + write — recommended)
- `GetGenericPortMappingEntry(index)` — list rules sequentially
- `GetSpecificPortMappingEntry(RemoteHost, ExternalPort, Protocol)` — query one rule
- `AddPortMapping(RemoteHost, ExternalPort, Protocol, InternalPort, InternalClient, Enabled, Description, LeaseDuration)` — create
- `DeletePortMapping(RemoteHost, ExternalPort, Protocol)` — delete

### `Layer3Forwarding1` (alternative)
- `GetForwardNumberOfEntries`, `AddForwardingEntry`, `DeleteForwardingEntry`, `GetGenericForwardingEntry`, `SetForwardingEntryEnable`

## Authentication

- **Read operations** (list, info, GetGenericPortMappingEntry) work **without auth** on LAN.
- **Write operations** (AddPortMapping, DeletePortMapping) require a `password` parameter matching the FritzBox admin password, passed via `FritzConnection(address=..., password=...)`.

Error 606 = missing/incorrect password for write ops.

## Script

See `scripts/fritzbox-portmgr.py` in this skill directory for a complete CLI wrapper. Copy/symlink to `~/.hermes/scripts/` to use:

```bash
python3 ~/.hermes/scripts/fritzbox-portmgr.py info
python3 ~/.hermes/scripts/fritzbox-portmgr.py list
FRITZ_PASSWORD=secret python3 ~/.hermes/scripts/fritzbox-portmgr.py add 8080 192.168.178.70 TCP "MyWebServer"
FRITZ_PASSWORD=secret python3 ~/.hermes/scripts/fritzbox-portmgr.py del 8080 TCP
```

## AddPortMapping Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `NewRemoteHost` | string | Usually empty `""` for all remote hosts |
| `NewExternalPort` | uint | External/WAN port number |
| `NewProtocol` | string | `"TCP"` or `"UDP"` |
| `NewInternalPort` | uint | Internal/LAN port number |
| `NewInternalClient` | string | Destination IP address in LAN |
| `NewEnabled` | bool | `True` to enable the rule |
| `NewPortMappingDescription` | string | Human-readable name |
| `NewLeaseDuration` | int | `0` = permanent |
