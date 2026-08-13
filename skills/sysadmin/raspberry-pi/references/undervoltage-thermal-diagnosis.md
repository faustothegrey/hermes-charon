# Undervoltage vs Thermal — Session Diagnosis Detail (2026-07/08)

Full diagnosis path from a real incident: Pi 4 (Charon/peer70) in a hot
August house showed weeks of `Undervoltage detected!` crash-loops. The
real cause was **thermal**, not electrical. This is the evidence trail
and the reusable procedure.

## Incident timeline

1. **31 Jul 19:43** — first `Undervoltage detected!` in journal after
   weeks clean. 7 events that evening, then ~1600/day.
2. Crash-loop overnight: 9 boots in 4.5h (03:17→07:46), each boot
   killed with `Undervoltage detected!` as last kernel line.
3. Suspected PSU. User tried 3+ chargers/cables over 10 days.
4. **Real finding**: `vcgencmd measure_volts` stayed at **0.8625-0.869V
   stable under full 4-core load** (1500MHz, sha256sum stress). Temp hit
   82.3°C — over the 80°C soft limit. `throttled=0x80008` (soft temp
   limit NOW). It was thermal throttling the whole time; the dmesg
   "Undervoltage" lines were red herrings from the shared throttling
   path (bit 18) plus rate-limited hwmon messages.

## Evidence table (what each throttled value meant)

| Value | Bits | Meaning |
|---|---|---|
| `0x0` | — | Clean — no active or historical flags |
| `0x50005` | 0+2+16+18 | UV NOW + throttled NOW + UV occurred + throttling occurred |
| `0x80008` | 3+19 | Soft temp limit NOW + occurred (thermal active) |
| `0xe0000` | 17+18+19 | Historical only (freq cap + throttling + soft temp occurred) — not active, clears only on power cycle |

## Rate-limited dmesg pitfall

`dmesg | grep -c Undervoltage` returned 0 even while the journal showed
hundreds. Kernel rate-limits repeated hwmon messages. Always count via
`journalctl`:
```bash
journalctl --since "<date>" | grep -c "Undervoltage detected"
journalctl --list-boots   # shows the crash-loop pattern directly
```

## "Voltage normalised" before "Undervoltage detected"

The journal showed `Voltage normalised` at 19:43:19 BEFORE the first
`Undervoltage detected` at 19:43:24. Normalised = END of an episode →
the episode was already underway before logging began. First logged
event ≠ first actual event.

## Diagnostic procedure that settled it

```bash
# 1. Baseline (idle)
vcgencmd get_throttled; vcgencmd measure_volts; vcgencmd measure_temp

# 2. Full-load stress at MAXIMUM frequency (ondemand, NOT powersave)
for i in 1 2 3 4; do timeout 60 sha256sum /dev/zero & done
for t in 5 25 45; do sleep 20; echo "$(date +%H:%M:%S) thr=$(vcgencmd get_throttled) volt=$(vcgencmd measure_volts) temp=$(vcgencmd measure_temp)"; done
```

Decision:
- volt stable + temp > 80°C + bit 3/19 → **thermal**
- volt drops / bit 0/16 appears under load → **electrical** (PSU/cable/socket)
- idle `measure_volts` alone is NEVER conclusive — marginal PSUs hold idle and sag only under load

## Governor persistence fix

`/etc/rc.local` runs before the cpufreq driver is ready — writing
`powersave` there gets overwritten to `ondemand` later. Use a systemd
oneshot with `After=multi-user.target` (see SKILL.md for the unit).
Disable later with `systemctl disable --now <svc>` + remove the
rc.local block.

## Side protection measures applied while electrical was suspected

These are still good practice for a Pi that had any power issues:
- Swap file on SD → **zram** (512M): zero SD wear (`modprobe zram`,
  `echo 512M > /sys/block/zram0/disksize`, mkswap, swapon; swapoff the
  file swap)
- `journald.conf`: `SystemMaxUse=100M` + `MaxRetentionSec=7d` —
  cut journal from 752MB → 48MB (systemd --user was writing 38GB
  cumulative to SD)
- `vm.dirty_writeback_centisecs=1500`, `dirty_expire_centisecs=1000`,
  `dirty_ratio=10` — smaller, more frequent flushes (less data at risk
  on brownout)

## Watchdog with cooldown (no_agent cron)

Script reads `get_throttled`; prints alert only when bit 0 active; state
file `~/.hermes/state/undervoltage_state.json` holds `last_alert_ts`;
1 alert max per 60 min. Empty stdout = silent (watchdog pattern).
Cron: `every 15m`, `no_agent=true`, `deliver=origin`.

## Hardware lesson

Repeated charger swaps failing to fix "undervoltage" + stable voltage
under load = it was never electrical. Check `measure_volts` DURING the
stress test before buying PSUs. Also: a Pi that re-powers itself after
`shutdown -h now` (boots alone at 03:17) with a marginal PSU is showing
brownout-recovery behavior — the PSU sags, Pi resets, PSU recovers, Pi
boots. That symptom + stable voltage under load can still be thermal if
the reset comes from temp-driven shutdown.
