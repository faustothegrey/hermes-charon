#!/usr/bin/env python3
"""load_data.py — read system load info for NetBoard.

Reads CPU, RAM, disk, temperature. Returns a formatted dict.
"""

import os
import time
from pathlib import Path

# Cache: non chiamare subprocess ogni volta che netboard ridisegna
_cache = None
_cache_time = 0
_CACHE_TTL = 10  # secondi


def get_status() -> dict:
    """Return dict with cpu, ram, disk, temp info."""
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < _CACHE_TTL:
        return _cache

    result = {}

    # CPU load from /proc/loadavg
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            result["cpu_1min"] = float(parts[0])
            result["cpu_5min"] = float(parts[1])
            result["cpu_15min"] = float(parts[2])
    except Exception:
        result["cpu_1min"] = result["cpu_5min"] = result["cpu_15min"] = 0

    # RAM from /proc/meminfo
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                k, v = line.split(":", 1)
                meminfo[k.strip()] = int(v.strip().split()[0])
        total = meminfo.get("MemTotal", 1)
        avail = meminfo.get("MemAvailable", 0)
        result["ram_pct"] = round(100 * (total - avail) / total, 1)
        result["ram_gb"] = round(total / (1024 * 1024), 1)
    except Exception:
        result["ram_pct"] = 0
        result["ram_gb"] = 0

    # Disk from / (root partition)
    try:
        stat = os.statvfs("/")
        total_bytes = stat.f_frsize * stat.f_blocks
        free_bytes = stat.f_frsize * stat.f_bfree
        result["disk_pct"] = round(100 * (total_bytes - free_bytes) / total_bytes, 1)
        result["disk_gb"] = round(total_bytes / (1024**3), 1)
    except Exception:
        result["disk_pct"] = 0
        result["disk_gb"] = 0

    # CPU temperature via vcgencmd (RPi specific)
    try:
        import subprocess
        r = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            temp_str = r.stdout.strip()
            # "temp=45.2'C" → 45.2
            result["temp_c"] = float(temp_str.split("=")[1].split("'")[0])
        else:
            # fallback: thermal zone
            result["temp_c"] = _read_thermal()
    except Exception:
        result["temp_c"] = _read_thermal()

    _cache = result
    _cache_time = now
    return result


def _read_thermal() :
    """Read CPU temp from sysfs thermal zone."""
    for i in range(3):
        p = Path(f"/sys/class/thermal/thermal_zone{i}/temp")
        if p.exists():
            try:
                raw = int(p.read_text().strip())
                return round(raw / 1000, 1)
            except Exception:
                pass
    return None


def format_short(status: dict) -> str:
    """One-liner for framebuffer bottom area."""
    cpu = status.get("cpu_1min", 0)
    ram = status.get("ram_pct", 0)
    disk = status.get("disk_pct", 0)
    temp = status.get("temp_c")

    cpu_icon = "🟢" if cpu < 1.0 else "🟡" if cpu < 2.0 else "🔴"
    ram_icon = "🟢" if ram < 50 else "🟡" if ram < 80 else "🔴"
    disk_icon = "🟢" if disk < 70 else "🟡" if disk < 90 else "🔴"

    parts = [f"{cpu_icon}CPU {cpu:.1f}"]
    parts.append(f"{ram_icon}RAM {ram}%")
    parts.append(f"{disk_icon}DISK {disk}%")
    if temp is not None:
        temp_icon = "🟢" if temp < 60 else "🟡" if temp < 75 else "🔴"
        parts.append(f"{temp_icon}{temp}°C")

    return "  ".join(parts)


if __name__ == "__main__":
    s = get_status()
    print(format_short(s))
