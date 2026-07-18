# FritzBox TR-064 UPnP Port Forwarding

Tested on **FRITZ!Box 7490** with `fritzconnection` v1.15.1 and `miniupnpc` v2.2.1.

## Capabilities

| Operation | Status | Notes |
|-----------|--------|-------|
| List rules | ✅ Works (no auth required) | `GetGenericPortMappingEntry(index)` |
| Get specific rule | ✅ Works | `GetSpecificPortMappingEntry(port, protocol)` |
| Delete rule | ✅ Works | `DeletePortMapping(host, port, protocol)` |
| Add rule | ❌ Error 606 | AddPortMapping returns "Action not authorized" |
| Count rules | ❌ Error 401 | `GetPortMappingNumberOfEntries` not available |

## Install

```bash
pip install fritzconnection
# or: sudo apt install miniupnpc
```

## Python Usage

```python
from fritzconnection import FritzConnection

fc = FritzConnection(address="192.168.178.1")

# List all rules
i = 0
while True:
    try:
        e = fc.call_action("WANIPConn1", "GetGenericPortMappingEntry",
                           NewPortMappingIndex=i)
        print(f"[{i}] {e['NewPortMappingDescription']} → "
              f"{e['NewInternalClient']}:{e['NewInternalPort']}/{e['NewProtocol']}")
        i += 1
    except:
        break

# Delete a rule
fc.call_action("WANIPConn1", "DeletePortMapping",
    NewRemoteHost="", NewExternalPort=51413, NewProtocol="TCP")

# Add a rule — likely fails with error 606 on most FritzBox models
# Workaround: enable "Allow changes via UPnP" in FritzBox web UI
# System → Network → Network Settings → UPnP access
```

## CLI Usage (miniupnpc)

```bash
# List rules
upnpc -l

# Delete rule — MUST include empty remote host arg
upnpc -d 51413 TCP ""      # ✅ works (empty string for remote host)
upnpc -d 51413 TCP         # ❌ returns 0 but does NOT delete (no remote host)

# Add rule — same error 606 limitation
upnpc -a 192.168.178.70 8080 8080 TCP
```

## Error 606 — Root Cause

Error 606 = "Action not authorized". The FritzBox 7490 (and likely other models)
has UPnP IGD write operations **disabled by default** for security.

**Fix:** In the FritzBox web UI:
1. Go to **System → Network → Network Settings**
2. Under **"Permit access via UPnP"**, enable **"Allow changes to settings via UPnP"**
3. Apply and retry

Or use the web API (login_sid.lua + data.lua) as an alternative.

## CLI Tool

A convenience script at `~/.hermes/scripts/fritzbox-portmgr.py` wraps the FritzBox API:

```bash
python3 ~/.hermes/scripts/fritzbox-portmgr.py info      # router info + external IP
python3 ~/.hermes/scripts/fritzbox-portmgr.py list      # list all port forwarding rules
python3 ~/.hermes/scripts/fritzbox-portmgr.py add 8080 192.168.178.70 TCP "My Service"  # add rule
python3 ~/.hermes/scripts/fritzbox-portmgr.py del 8080 TCP  # delete rule
```

Supports env vars: `FRITZ_IP`, `FRITZ_USER`, `FRITZ_PASSWORD` (defaults: `192.168.178.1`, `fausto`, `ccll4372`).

## Known Bugs on FRITZ!Box 7490

### Port 2222 gets silently mapped as 22

When using `AddPortMapping` (TR-064 or `miniupnpc`) with `NewExternalPort=2222`, the FritzBox 7490 creates the rule as **external port 22** instead, regardless of internal port. The description changes but the external port is always 22. This is consistent across both `upnpc -a` and `fritzconnection.call_action()`.

**Affected:** external port 2222
**Works correctly:** 4433, 8080, 51413, and other ports tested
**Root cause:** likely a firmware-level mapping or reserved-port conflict on the 7490 running FRITZ!OS 7.62

**Workaround:** use a different external port (e.g., 4433) and configure SSH to listen on that port:

```bash
# On the target machine, add SSH on the alternate port
sudo sh -c 'echo "Port 4433" >> /etc/ssh/sshd_config'
sudo systemctl restart sshd

# Verify both ports listen
ss -tlnp | grep -E "4433|2222"
```

Then create the UPnP rule for 4433→4433 instead of 2222→2222.
