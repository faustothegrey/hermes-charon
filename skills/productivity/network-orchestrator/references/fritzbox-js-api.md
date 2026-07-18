# FritzBox API Access

The FritzBox exposes two complementary API channels. Use the **Node.js fritzbox.js library** for telephony/phonebook, and the **`data.lua` REST endpoint** (via Python or Node) for network status, DSL, WiFi, and connected devices.

---

## Channel 1: Telephony via fritzbox.js (Node.js)

Access AVM FritzBox telephony, phonebook, system info, and call monitoring through the **web/TR-064 API** — a different endpoint than the UPnP/TR-064 port-forwarding interface. This API covers what the TR-064 `fritzconnection` library cannot: call history, phonebook contacts, answering machine messages, click-to-dial, and DECT smart home devices.

## Architecture

```
node fritzbox.js
    │
    ├─ getVersion()          → Fritz!OS version string (no auth)
    ├─ getVersionNumber()    → Fritz!OS version as int (no auth)
    ├─ getSessionId()        → 16-char SID via challenge-response MD5
    │
    ├─ getCalls()            → Call history (CSV → JSON)
    ├─ getPhonebook(id)      → Contact list from phonebook
    ├─ getActiveCalls()      → Currently active calls
    ├─ getTamMessages()      → Answering machine messages
    ├─ downloadTamMessage()  → Download TAM audio (.wav)
    ├─ markTamMessageAsRead()-> Mark TAM message read
    ├─ dialNumber(num)       → Click-to-dial
    ├─ CallMonitor           → Real-time call events (TCP 1012)
    │
    ├─ getSmartDevices()     → DECT smart home devices
    └─ toggleSwitch(id, val) → DECT switch on/off
```

## Installation

```bash
npm install fritzbox.js
```

**Note:** `fritzbox.js` is archived (Jan 2025, v2.0.1) but fully functional on Fritz!OS 07.62 (Fritz!Box 7490). The `request` dependency is deprecated but works.

---

## Channel 2: Network Status via `data.lua` (Python)

The FritzBox's web UI exposes an undocumented REST endpoint at `POST /data.lua` that returns JSON with DSL stats, Internet status, WiFi state, connected devices, and system info. This is the **primary channel for network-level data** — the Node.js library's `wlan.js` module is empty.

### Endpoint

```
POST https://<fritzbox>/data.lua
Content-Type: application/x-www-form-urlencoded
Body: page=<page>&sid=<sessionId>
```

| page | Key data |
|------|----------|
| `overview` | DSL (up/down kbps), Internet (IP, provider, DNS, speeds), WLAN (2.4/5 GHz status), net.devices (all connected devices with state), fritzos (version, product, energy), comfort.func (DynDNS, port forwarding count, NAS) |
| `chan` | 5 GHz radio channel airtime scan: `timestamp,slotCount,slotDuration,ch:val,ch:val,...` |

### Session Auth

Uses the same challenge-response as fritzbox.js: `GET /login_sid.lua` → MD5 challenge → `GET /login_sid.lua?username=...&response=...` → SID string.

### Python Example (self-signed cert friendly)

```python
import requests
urllib3.disable_warnings()  # suppress self-signed cert warnings

def get_sid():
    r = requests.get("https://192.168.178.1/login_sid.lua", verify=False, timeout=8)
    challenge = r.text.split("<Challenge>")[1].split("</Challenge>")[0]
    import hashlib
    m = hashlib.md5((challenge + "-" + PASSWORD).encode("utf-16-le"))
    resp = challenge + "-" + m.hexdigest()
    r2 = requests.get(f"https://192.168.178.1/login_sid.lua?username={USER}&response={resp}",
                      verify=False, timeout=8)
    return r2.text.split("<SID>")[1].split("</SID>")[0]

def get_fritzbox_status():
    sid = get_sid()
    r = requests.post("https://192.168.178.1/data.lua",
                      data={"page": "overview", "sid": sid},
                      verify=False, timeout=25)
    return r.json()
```

**Note:** The first `data.lua` call is slow (~10-20s). Subsequent calls are fast (warm SID + connection pool).

### CLI / Script Module

A reusable Python module exists at `~/.hermes/scripts/fritzbox_data.py` that wraps the auth, data.lua, and status parsing. It provides:

- `get_status()` → dict with `reachable`, `dsl_down_kbps`, `dsl_up_kbps`, `internet_ip`, `provider`, `device_count`, `device_online`, `wifi_24`, `wifi_5`, `fritzos_version`, `product`
- `format_short(status)` → one-liner: `🌐 176.206.11.86 ↓14.8M ↑10.7M 16 disp (12 online)`

### NetBoard Integration

The FritzBox stats are integrated into both **NetBoard** dashboards:

1. **Framebuffer display** (`netboard.py`, systemd service) — separate thread polls FritzBox every **60 seconds** (relaxed). Shows DSL/Internet/device count below the peer cards.
2. **Web dashboard** (`netboard-web.py`, port 8191) — endpoint `/api/fritzbox` returns live JSON. The web page fetches it and displays DSL ↓/↑, IPv4, provider, device count, WiFi bands.

Both services restart automatically on boot. See `fritzbox` skill in `sysadmin/` category for full CLI wrapper and API reference.

### Comparison: Node.js vs Python for FritzBox

| Capability | fritzbox.js (Node) | fritzbox_data.py (Python) | fritzconnection (TR-064) |
|------------|-------------------|--------------------------|-------------------------|
| Call history | ✅ | ❌ | ❌ |
| Phonebook | ✅ | ❌ | ❌ |
| DSL status | ❌ | ✅ (data.lua) | ✅ |
| Internet IP/DNS | ❌ | ✅ | ✅ |
| Connected devices | ❌ | ✅ | ✅ |
| WiFi status | ❌ (stub) | ✅ | ✅ |
| Port forwarding | ❌ | ❌ | ✅ |
| DECT smart home | ✅ | ❌ | ❌ (separate AHA) |

They are complementary. Use fritzbox.js for telephony, fritzbox_data.py for quick network status, and fritzconnection for port forwarding / TR-064 config.

---

## Known Patch: CSV Call History Parsing

**Bug:** `getCalls()` crashes with `Cannot read properties of undefined (reading 'replace')` on non-English firmware.

**Root cause:** The library's `callsCsvToJson` in `src/format.js` translates CSV column headers from the FritzBox's locale to English, then does two case-sensitive `.replace()` calls that fail when the translated headers have capitalisation differences. Specifically:

```js
// BROKEN: 'Telephone number' (lowercase n) won't match 'Telephone Number' (uppercase N)
.replace('Extension;Telephone number', 'Extension;NumberSelf')
.replace('Telephone number', 'Number')
```

**Fix:** Replace line 41 of `src/format.js` to write the correct English headers directly, skipping the unreliable `.replace()` chain:

```js
lines[1] = 'Type;Date;Name;Number;Extension;NumberSelf;Duration'
// Then only .replace('sep=;', '') and .trim() — no further replacements
```

Applied in `~/.hermes/tests/fritzbox-test/node_modules/fritzbox.js/src/format.js`.

## CLI Wrapper

A convenience script lives at `~/.hermes/scripts/fritzbox.js` (Node) with complete commands:

```
Usage: node ~/.hermes/scripts/fritzbox.js <command> [args]

Rete:
  info                Fritz!OS, DSL, Internet, comfort features
  devices             Connected devices with status
  wlan                WiFi 2.4/5 GHz status
  channels            5 GHz radio channel occupancy

Telefono:
  calls [N]           Recent call history (default: 10)
  phonebook           Phonebook contacts
  active              Active calls
  tam                 Answering machine messages
  dial <number>       Click-to-dial
```

Also available: `~/.hermes/scripts/fritzbox_data.py` (Python) for programmatic access from other scripts (NetBoard, cron jobs, etc.).

## FritzBox Credentials

Router: `192.168.178.1` (Fritz!Box 7490)
Username: `fausto`
Password: `ccll4372`
Protocol: `https` (uses `rejectUnauthorized: false` for self-signed cert)

## What Works / What Doesn't on Fritz!OS 07.62

| Function | Status | Notes |
|----------|--------|-------|
| `getVersion()` | ✅ | Returns `"07.62"` |
| `getSessionId()` | ✅ | Challenge-response with MD5 + UTF-16LE password |
| `getCalls()`  | ✅ | After the CSV patch above |
| `getPhonebook()` | ✅ | Returns contact array with names, numbers, categories |
| `getActiveCalls()` | ✅ | Returns empty array when none active |
| `CallMonitor()` | ✅ | Requires `#96*5#` to enable call monitor on the FritzBox |
| `dialNumber()` | ✅ | Requires Click-to-Dial config in FritzBox UI |
| `getTamMessages()` | ❌ | "Requested page does not exist" — no TAM configured |
| `getSmartDevices()` | ❌ | "Requested page does not exist" — no DECT devices registered |
| `getSystemEventLog()` | ❌ | Not exported by the library (only in DOCS.md, never implemented) |