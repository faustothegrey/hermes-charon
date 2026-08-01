# FritzBox UPnP + Firewall Cheat Sheet (peer70)

## Port Forwarding Commands

### List Rules
```bash
upnpc -l                              # via UPnP IGD
python3 fritzbox-portmgr.py list      # via TR-064 (more reliable)
```

### Add Rule (UPnP)
```bash
# Syntax: upnpc -a <internal_ip> <internal_port> <external_port> <protocol> <lease>
upnpc -a 192.168.178.70 4433 4433 TCP 0
```

### Delete Rule (UPnP)
```bash
# ⚠️ ALWAYS include trailing "" for remote host
upnpc -d <external_port> <protocol> ""
upnpc -d 4433 TCP ""
```

### Using Python fritzconnection (TR-064)
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
    NewRemoteHost="", NewExternalPort=22, NewProtocol="TCP")
```

## Bug: Port 2222

**Don't use 2222 as external port.** The FritzBox 7490 silently maps it to 22.
Use 4433 instead. Configure SSH to listen on 4433 as well:
```bash
# Add to /etc/ssh/sshd_config
Port 4433
```

## Local Firewall (peer70 RPi)

The RPi has `iptables INPUT policy DROP` and only accepts LAN traffic.
WAN-forwarded traffic is blocked unless explicitly allowed:

```bash
# Open ports for forwarded traffic
sudo iptables -A INPUT -p tcp --dport 2222 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 4433 -j ACCEPT

# Save persistently
sudo netfilter-persistent save
```

Check current rules:
```bash
sudo iptables -L INPUT -n -v
```

## Web Login (for manual config)

```python
import hashlib, requests, xml.etree.ElementTree as ET
s = requests.Session()
r = s.get("http://192.168.178.1/login_sid.lua")
challenge = ET.fromstring(r.text).findtext("Challenge")
md5 = hashlib.md5(f"{challenge}-ccll4372".encode("utf-16le")).hexdigest()
r = s.get("http://192.168.178.1/login_sid.lua",
    params={"username": "fausto", "response": f"{challenge}-{md5}"})
sid = ET.fromstring(r.text).findtext("SID")
```
