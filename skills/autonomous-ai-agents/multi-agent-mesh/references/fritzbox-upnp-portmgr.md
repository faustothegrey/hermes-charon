# FritzBox 7490 — UPnP Port Forwarding via TR-064 / miniupnpc

## Tools

- **CLI wrapper:** `~/.hermes/scripts/fritzbox-portmgr.py` (list/info work without auth; add/delete need FritzBox password)
- **System package:** `miniupnpc` → `upnpc` command (preferred for automation)

## UPnP Commands

### List rules
```bash
upnpc -l
# Or via Python/fritzconnection:
fc.call_action("WANIPConn1", "GetGenericPortMappingEntry", NewPortMappingIndex=0..N)
```

### Add rule
```bash
upnpc -a <internal_ip> <internal_port> <external_port> <protocol> 0
# Example: SSH on peer70
upnpc -a 192.168.178.70 2222 2222 TCP 0
```

### Delete rule — CRITICAL: remote host MUST be empty string
```bash
upnpc -d <external_port> <protocol> ""
#                      ↑↑   WITHOUT "" the delete returns 0 but does NOTHING  ↑↑
# Example:
upnpc -d 4433 TCP ""
```
**Without the trailing `""` (empty remote host), `UPNP_DeletePortMapping()` returns 0 (success) but the rule is NOT removed.** Always include it.

### Python/fritzconnection
```python
from fritzconnection import FritzConnection
fc = FritzConnection(address="192.168.178.1", user="fausto", password="ccll4372")

# Add
fc.call_action("WANIPConn1", "AddPortMapping",
    NewRemoteHost="", NewExternalPort=4433, NewProtocol="TCP",
    NewInternalPort=4433, NewInternalClient="192.168.178.70",
    NewEnabled="1", NewPortMappingDescription="SSH_peer70", NewLeaseDuration="0")

# Delete
fc.call_action("WANIPConn1", "DeletePortMapping",
    NewRemoteHost="", NewExternalPort=4433, NewProtocol="TCP")
```

## Known Bug: External Port 2222

On the FritzBox 7490 (FRITZ!OS 7.62), `AddPortMapping` with `NewExternalPort=2222` **always creates a mapping with external port 22 instead of 2222**. This has been tested with both `upnpc` and `fritzconnection` — same result. Ports 4433, 8080, and others work correctly.

**Workaround:** use a different external port (e.g., 4433) and configure SSH or whatever service on that port on the internal host.

```bash
# This creates: external 22 → internal 2222 (WRONG!)
upnpc -a 192.168.178.70 2222 2222 TCP 0

# This works correctly: external 4433 → internal 4433
upnpc -a 192.168.178.70 4433 4433 TCP 0
```

## Firewall on Internal Host

On RPi/Debian with iptables, the INPUT chain may have `policy DROP` with rules only accepting traffic from the local subnet (`192.168.178.0/24`). Traffic arriving via UPnP port forwarding has a WAN source IP and gets dropped.

```bash
# Open ports permanently
sudo iptables -A INPUT -p tcp --dport 2222 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 4433 -j ACCEPT
sudo netfilter-persistent save   # persist across reboot
```

## FritzBox Credentials

- User: `fausto`
- Password: same as SSH (`ccll4372`)
- Web interface: `http://fritz.box`
