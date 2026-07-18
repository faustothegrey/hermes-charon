---
name: fritzbox
description: Access and manage an AVM FRITZ!Box router via its undocumented web API (data.lua) and the fritzbox.js library
category: sysadmin
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [fritzbox, avm, router, network, dsl, wlan, telephony]
    related_skills: [network-orchestrator, lan-peer-monitor]
---

# FRITZ!Box Router API

Query network status (DSL, Internet, WLAN, connected devices, radio channels, comfort features, port forwarding) and telephony (calls, phonebook, answering machine, click-to-dial) on an AVM FRITZ!Box router.

## Setup (questo RPi, peer70)

- Library install: `~/.hermes/tests/fritzbox-test/` (npm installed, 61 packages)
- Patch applied: `node_modules/fritzbox.js/src/format.js` — `callsCsvToJson` rewritten
- CLI wrapper: `~/.hermes/scripts/fritzbox.js`
- Credentials: fausto / ccll4372 @ 192.168.178.1 (HTTPS, self-signed cert, Fritz!OS 07.62)
- Provider: WIND Tre, IPv4 176.206.11.86, DynDNS settembre2.homepc.it

## Two API Channels

### 1. fritzbox.js (Node library) — Telephony & Auth

- Repo: [lesander/fritzbox.js](https://github.com/lesander/fritzbox.js) (archived v2.0.1, MIT)
- Requires Node ≥ 7.6
- Covers: `getSessionId`, `getVersion`, `getCalls`, `getPhonebook`, `getActiveCalls`, `getTamMessages`, `dialNumber`, `getSmartDevices`, `toggleSwitch`, `CallMonitor`
- **Patch needed**: `getCalls()` crashes because `format.js`'s `callsCsvToJson` uses case-sensitive `.replace()` that doesn't match "Telephone Number" vs "Telephone number". Fix: replace the header line directly:

```js
lines[1] = 'Type;Date;Name;Number;Extension;NumberSelf;Duration'
// Remove the two chained .replace() calls below
```

### 2. data.lua (undocumented REST) — Network Status

`POST https://<fritzbox>/data.lua` with `Content-Type: application/x-www-form-urlencoded` and body `page=<page>&sid=<sessionId>`.

| page | Returns |
|------|---------|
| `overview` | DSL stats, Internet connection (IP, DNS, provider, speeds), WLAN status (2.4/5 GHz), all connected devices with state, mesh info, comfort features (DynDNS, port-forwarding count, NAS, etc.), Fritz!OS info |
| `chan` | 5 GHz radio channel scan + airtime data (compressed format: `timestamp,slots,dur,ch:val,ch:val,...`) |
| `netDev` | Device list (may need extra params) |

The FritzBox returns HTML 404 for direct `.lua` path access (e.g. `/internet/inetstat_monitor.lua`). All routing goes through `data.lua`.

**TR-064 / UPnP SOAP** over port 443 returns 404 on Fritz!OS 07.62/7490 — not available. Use data.lua or TR-064 on the dedicated TR-064 port (typically 49000) if needed.

### Self-Signed Certificate Workaround

The FritzBox uses a self-signed HTTPS cert.

## UPnP / TR-064 Port Forwarding

The FritzBox supports the TR-064/UPnP IGD protocol on port 49000 for listing, adding, and deleting port-forwarding rules. However, **write operations have limitations** depending on Fritz!OS configuration.

### Read Operations (work without auth)
```python
from fritzconnection import FritzConnection
fc = FritzConnection(address="192.168.178.1")
# List port forwarding rules
i = 0
while True:
    try:
        e = fc.call_action(\"WANIPConn1\", \"GetGenericPortMappingEntry\", NewPortMappingIndex=i)
        print(e)
        i += 1
    except: break

# Get external IP
fc.call_action(\"WANIPConn1\", \"GetExternalIPAddress\")
```

### Write Operations (require UPnP write permission)
```python
# Delete works
fc.call_action(\"WANIPConn1\", \"DeletePortMapping\",
    NewRemoteHost=\"\", NewExternalPort=51413, NewProtocol=\"TCP\")

# Add FAILS with error 606 (Action not authorized)
fc.call_action(\"WANIPConn1\", \"AddPortMapping\", ...)
# → UPnPError: errorCode=606 errorDescription=Unknown Error Code
```

Error 606 is **not a library bug** — it's a FritzBox security restriction. On the FritzBox 7490 with Fritz!OS 07.62, delete works but add returns 606 regardless of credentials.

### Solving Error 606

**Option A: Enable UPnP writes in the web UI**
1. Open `http://fritz.box`
2. **System → Network → Network Settings**
3. Under "Access via UPnP", check **"Allow changes to settings via UPnP"**
4. Apply. Now `upnpc -a` and TR-064 `AddPortMapping` should work.

**Option B: Web Form API (data.lua)**
```python
# Login
import hashlib, requests, xml.etree.ElementTree as ET
s = requests.Session()
r = s.get(\"http://192.168.178.1/login_sid.lua\")
challenge = ET.fromstring(r.text).findtext(\"Challenge\")
md5 = hashlib.md5(f\"{challenge}-{PASSWORD}\".encode(\"utf-16le\")).hexdigest()
r = s.get(\"http://192.168.178.1/login_sid.lua\",
    params={\"username\": \"fausto\", \"response\": f\"{challenge}-{md5}\"})
sid = ET.fromstring(r.text).findtext(\"SID\")

# Try to add port forwarding via data.lua
s.post(\"http://192.168.178.1/data.lua\", data={
    \"sid\": sid, \"page\": \"netPort\", \"xhrId\": \"add\", \"xhr\": \"1\",
    \"NewExternalPort\": \"2222\", \"NewProtocol\": \"TCP\",
    \"NewInternalPort\": \"2222\", \"NewInternalClient\": \"192.168.178.70\",
    \"NewEnabled\": \"on\", \"NewPortMappingDescription\": \"SSH_peer70\",
    \"NewLeaseDuration\": \"0\",
})
```

Note: the data.lua approach on Fritz!OS 07.62 may return HTTP 200 without actually creating the rule. The page response is the overview JSON, not a port-forwarding confirmation. This may vary by firmware version.

**Option C: Manual rule creation (always works)**
Browse to `http://fritz.box` → **Internet → Permit Access → Port Forwarding** and add the rule manually.

### CLI Tool

`~/.hermes/scripts/fritzbox-portmgr.py` wraps the TR-064 API:

```bash
python3 ~/.hermes/scripts/fritzbox-portmgr.py list       # Show all rules
python3 ~/.hermes/scripts/fritzbox-portmgr.py add 2222 192.168.178.70 TCP "SSH"
python3 ~/.hermes/scripts/fritzbox-portmgr.py del 2222 TCP
python3 ~/.hermes/scripts/fritzbox-portmgr.py info       # Router info
```

Requires `FRITZ_USER` and `FRITZ_PASSWORD` env vars (or defaults in the script). Read operations work without auth; write operations need a FritzBox user with UPnP write permissions. Node's native `fetch()` does NOT respect `agent: new https.Agent({rejectUnauthorized: false})` for TLS. Use either:

**Option A: `https.request` directly (reliable)**

```js
const https = require('https');
function postForm(urlStr, formBody) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const body = new URLSearchParams(formBody).toString();
    const opts = {
      hostname: u.hostname, port: 443, path: u.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(body)
      },
      rejectUnauthorized: false
    };
    const req = https.request(opts, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(JSON.parse(data)));
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}
```

**Option B: `request-promise` (deprecated but works)**

```js
const rp = require('request-promise');
const r = await rp({
  uri: 'https://192.168.178.1/data.lua',
  method: 'POST',
  form: { page: 'overview', sid },
  rejectUnauthorized: false,
  resolveWithFullResponse: true
});
```

## Session Auth Flow

```js
const fritz = require('fritzbox.js');
const opts = { username: 'admin', password: 'xxx', server: '192.168.178.1', protocol: 'https' };
const sid = await fritz.getSessionId({ ...opts, rejectUnauthorized: false });
// sid is a 16-char hex string
```

## Key Data Points from `page=overview`

```
ov.data.dsl  → { up: kbps, down: kbps, txt: "connessa", led: "led green" }
ov.data.internet.connections[0]  → { provider, state, ipv4: { ip, dns, since }, downstream, upstream, medium_downstream, medium_upstream }
ov.data.wlan  → [{ title, txt, led }]  (2 entries: 2.4 GHz + 5 GHz)
ov.data.net.devices  → [{ name, type, ip, mac, stateinfo: { active, online, nexustrust }, desc }]
ov.data.fritzos  → { nspver, Productname, boxDate, energy, isLabor, isUpdateAvail }
ov.data.comfort.func  → [{ linktxt, details }]  (DynDNS, port-forwarding, NAS, parental control, etc.)
```

## CLI Tool (`~/.hermes/scripts/fritzbox.js`)

Uses `https.request` directly (for self-signed cert support). All commands:

```
node ~/.hermes/scripts/fritzbox.js <comando> [args]

Rete:
  info                Info sistema, DSL, Internet, comfort
  devices             Dispositivi di rete connessi
  wlan                Stato WiFi 2.4/5 GHz
  channels            Canali radio 5 GHz occupati

Telefono:
  calls [N]           Ultime N chiamate (default 10)
  phonebook           Rubrica
  active              Chiamate in corso
  tam                 Segreteria telefonica
  dial <numero>       Click-to-dial
```

## Python Module (`scripts/fritzbox_data.py`)

A reusable Python module for programmatic access (used by NetBoard framebuffer and web dashboards). Import and call:

```python
from fritzbox_data import get_status, format_short
status = get_status()
print(format_short(status))
# → 🌐 176.206.11.86  ↓14.8M  ↑10.7M  16 disp (12 online)
```

Returns dict with: `reachable`, `dsl_down_kbps`, `dsl_up_kbps`, `internet_ip`, `provider`, `device_count`, `device_online`, `wifi_24`, `wifi_5`, `fritzos_version`, `product`.

Uses Python `requests` with `verify=False` (accepts self-signed cert). First call is slow (~10-20s), subsequent calls are fast due to warm SID + connection pool.

## NetBoard Integration

FritzBox stats are integrated into both NetBoard dashboards:

| Dashboard | Service | Polling | FritzBox data |
|-----------|---------|---------|---------------|
| Framebuffer (display) | `netboard.service` | Every 60s (background thread) | DSL ↓/↑, IP, device count, below peer cards |
| Web (browser) | `netboard-web.service` port 8191 | On-demand via `/api/fritzbox` | DSL, IP, provider, WiFi bands, devices |

Both services restart at boot. See `lan-peer-monitor` skill for NetBoard architecture.

## Pitfalls

- **First data.lua call is slow (~10s)** — subsequent calls are fast. Plan for this in cron jobs or scripts by making a warm-up call.
- **`getCalls` CSV is locale-dependent** — the FritzBox returns headers in the configured language (Italian: `Tipo;Data;Nome;...`). The library replaces line[1] with English headers. If the locale changes, the header indices stay the same so the fix still works.
- **No `wlan.js` implementation** — the library has an empty `wlan.js` stub. All WLAN data comes from `data.lua`.
- **`getSystemEventLog` is documented in DOCS.md but NOT exported** — not available in the library.
- **DECT smart devices / TAM require a device that supports them** — "page does not exist" means no hardware connected, not an API error.