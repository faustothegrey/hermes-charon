#!/usr/bin/env python3
"""fritzbox_data.py — fetch FritzBox status via data.lua API.

Relaxed polling (60s recommended). Uses Python requests with verify=False
for self-signed HTTPS cert.
"""

import time
import requests
import xml.etree.ElementTree as ET
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FB_HOST = "192.168.178.1"
FB_USER = "fausto"
FB_PASS = "ccll4372"

_SID = None
_SID_AT = 0
_SID_TTL = 600  # refresh SID every 10 min

def _get_sid():
    """Get session ID via fritzbox.js-style challenge-response."""
    global _SID, _SID_AT
    now = time.time()
    if _SID and now - _SID_AT < _SID_TTL:
        return _SID

    r = requests.get(
        f"https://{FB_HOST}/login_sid.lua",
        verify=False, timeout=8
    )
    root = ET.fromstring(r.text)
    challenge = root.findtext(".//Challenge")
    if not challenge:
        raise RuntimeError("No challenge from FritzBox")

    import hashlib
    m = hashlib.md5((challenge + "-" + FB_PASS).encode("utf-16-le"))
    resp = challenge + "-" + m.hexdigest()

    r2 = requests.get(
        f"https://{FB_HOST}/login_sid.lua?username={FB_USER}&response={resp}",
        verify=False, timeout=8
    )
    root2 = ET.fromstring(r2.text)
    sid = root2.findtext(".//SID")
    if not sid or sid == "0000000000000000":
        raise RuntimeError("FritzBox login failed")

    _SID = sid
    _SID_AT = now
    return sid


def _post_data_lua(page):
    """POST to data.lua and return parsed JSON."""
    sid = _get_sid()
    # First data.lua call is slow (~10s); subsequent are fast.
    for attempt in range(2):
        try:
            r = requests.post(
                f"https://{FB_HOST}/data.lua",
                data={"page": page, "sid": sid},
                verify=False, timeout=25
            )
            return r.json()
        except requests.Timeout:
            if attempt == 0:
                continue  # retry once
            raise


def get_status():
    """Return a dict with FritzBox network status.

    Returns:
        {
            "reachable": bool,
            "dsl_down_kbps": int,
            "dsl_up_kbps": int,
            "internet_ip": str,
            "provider": str,
            "dns_servers": [str],
            "wifi_24": bool,
            "wifi_5": bool,
            "device_count": int,
            "device_online": int,
            "fritzos_version": str,
            "product": str,
            "uptime_since": int,
            "error": str or None
        }
    """
    try:
        data = _post_data_lua("overview")
        d = data.get("data", {})
        dsl = d.get("dsl", {})
        inet = d.get("internet", {}).get("connections", [{}])[0]
        ipv4 = inet.get("ipv4", {})
        net = d.get("net", {})
        fw = d.get("fritzos", {})
        wlans = d.get("wlan", [])

        devices = net.get("devices", [])
        online_count = sum(
            1 for dev in devices
            if dev.get("stateinfo", {}).get("online")
        )

        result = {
            "reachable": True,
            "dsl_down_kbps": dsl.get("down", 0),
            "dsl_up_kbps": dsl.get("up", 0),
            "internet_ip": ipv4.get("ip", "-"),
            "provider": inet.get("provider", "-"),
            "dns_servers": [dns.get("ip") for dns in ipv4.get("dns", [])],
            "wifi_24": len(wlans) > 0 and "2,4" in (wlans[0].get("txt", "")),
            "wifi_5": len(wlans) > 1 and "5" in (wlans[1].get("txt", "")),
            "device_count": len(devices),
            "device_online": online_count,
            "fritzos_version": fw.get("nspver", ""),
            "product": fw.get("Productname", ""),
            "uptime_since": ipv4.get("since", 0),
            "error": None,
        }
        return result

    except Exception as e:
        return {
            "reachable": False,
            "error": str(e),
            "dsl_down_kbps": 0, "dsl_up_kbps": 0,
            "internet_ip": "-", "provider": "-",
            "dns_servers": [], "device_count": 0, "device_online": 0,
            "wifi_24": False, "wifi_5": False,
            "fritzos_version": "", "product": "",
            "uptime_since": 0,
        }


def format_short(status):
    """One-liner for CLI / framebuffer bottom bar."""
    if not status.get("reachable"):
        return "🌐 FritzBox: ⚠ non raggiungibile"
    ip = status.get("internet_ip", "-")
    d = status.get("dsl_down_kbps", 0)
    u = status.get("dsl_up_kbps", 0)
    cnt = status.get("device_count", 0)
    on = status.get("device_online", 0)
    return f"🌐 {ip}  ↓{d//1000}.{d%1000//100}M  ↑{u//1000}.{u%1000//100}M  {cnt} disp ({on} online)"


if __name__ == "__main__":
    import json
    s = get_status()
    print(json.dumps(s, indent=2))
    print()
    print(format_short(s))