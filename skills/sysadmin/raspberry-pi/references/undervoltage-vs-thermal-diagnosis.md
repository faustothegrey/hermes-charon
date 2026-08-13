# Undervoltage vs Thermal Diagnosis (vcgencmd get_throttled)

Method for distinguishing electrical (undervoltage/PSU) from thermal
(throttling) root causes on Raspberry Pi — proven on Charon (RPi4) during
the 2026-08 crash-loop saga.

## get_throttled bit decoding

```
$ vcgencmd get_throttled
```

| Bit | Mask | Meaning |
|-----|------|---------|
| 0   | 0x1       | Under-voltage **NOW** |
| 1   | 0x2       | Arm frequency capped NOW |
| 2   | 0x4       | Currently throttled NOW |
| 3   | 0x8       | Soft temperature limit NOW |
| 16  | 0x10000   | Under-voltage OCCURRED (latched, resets only on power cycle) |
| 17  | 0x20000   | Arm frequency capping OCCURRED |
| 18  | 0x40000   | Throttling OCCURRED |
| 19  | 0x80000   | Soft temperature limit OCCURRED |

Common values seen in the field:
- `0x50005` = bits 0+2+16+18 → undervoltage NOW + throttled NOW + latched history.
  Classic **PSU/cable** signature.
- `0x80008` = bits 3+19 → soft temp limit NOW + occurred. **Thermal**, not electrical.
- `0xe0000` = bits 17+18+19 → ONLY latched occurred bits (freq cap, throttling,
  soft temp), **no NOW bits** → current state is healthy; flags are stale
  history that clears on next power cycle.
- `0x0` = fully clean.

**Key pitfall:** a value like `0x50005` or `0xe0000` shown minutes after boot
includes latched "occurred" bits that are NOT current events. Do not report
"undervoltage now" from the occurred bits alone. Re-read `get_throttled`
several times over 30-60s and watch for the NOW bits (0-3). The definitive
current-state check is whether any bit < 4 is set.

## Distinguishing PSU vs thermal (the stress test)

The single most informative test: **full-load stress at max frequency while
sampling** `get_throttled`, `measure_volts`, `measure_temp`:

```bash
# 4 cores at 100% for ~60s (sha256sum /dev/zero is a cheap CPU burner)
for i in 1 2 3 4; do timeout 60 sha256sum /dev/zero & done
# meanwhile sample every 10s:
for t in 5 15 25 35 45 55; do
  printf "%ss freq=%s throttled=%s volt=%s temp=%s\n" "$t" \
    "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)" \
    "$(vcgencmd get_throttled | cut -d= -f2)" \
    "$(vcgencmd measure_volts | cut -d= -f2)" \
    "$(vcgencmd measure_temp | cut -d= -f2)"
  sleep 10
done
```

Interpretation:
- **Voltage stays stable (~0.86V idle / ~1.2V expected under load) AND no
  NOW undervoltage bits under stress** → PSU is fine; blame thermal.
- **Temp crosses 80°C (soft limit) under stress → `0x80008`/`0x8000x` NOW bits** →
  thermal throttling. RPi4 without fan in summer hits 80°C+ at full load even
  with a healthy PSU. This is NOT an undervoltage fault.
- **Under-voltage NOW bits appear under load even at low governor frequency** →
  PSU/cable is genuinely marginal. Note: powersave governor (600MHz) does NOT
  fix a bad PSU if it's bad enough — it just reduces the current draw peaks.

## Crash-loop forensics (kernel side)

When a Pi crash-loops (repeated boots every 20-40 min), read the END of each
previous boot in the journal — the LAST line tells you the death cause:

```bash
journalctl --list-boots | tail -20          # see all boots
journalctl -b -1 --no-pager | tail -8       # how the last boot died
```

- Last line `Undervoltage detected!` → electrical brownout reset.
- Last line a normal systemd shutdown (`Reached target Power-Off`) →
  intentional/manual, not a crash.
- **Gotcha:** a "Voltage normalised" appearing BEFORE the first logged
  "Undervoltage detected" means the episode started earlier — kernel
  rate-limits repeated hwmon messages, so dmesg/journal undercounts. Use
  `vcgencmd get_throttled` latched bits for the true count.

## Practical mitigation ladder (soft, reversible)

1. **Limit governor** (reduces current peaks, buys time):
   `echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
   Make it persistent with a systemd oneshot service with `After=multi-user.target`
   (rc.local runs too early — the cpufreq driver isn't ready and the kernel
   resets the governor to ondemand after it).
2. **zram instead of SD swap** (kills SD wear from swap):
   `modprobe zram; echo 512M > /sys/block/zram0/disksize; mkswap /dev/zram0; swapon /dev/zram0; swapoff /var/swap`
3. **Limit journald writes** (systemd --user writes tens of GB to SD over
   months): `SystemMaxUse=100M`, `MaxRetentionSec=7d` in
   `/etc/systemd/journald.conf` + `systemctl restart systemd-journald`
   (dropped 752MB → 48MB instantly).
4. **Aggressive dirty-writeback** (smaller flush windows, less data loss on
   brownout): `vm.dirty_writeback_centisecs=1500 dirty_expire_centisecs=1000 dirty_ratio=10`.

All four are revertible; keep them documented in /etc/rc.local or a service so
a reboot doesn't silently undo them.

## When the user says "I changed the PSU/charger"

Re-verify with a fresh stress test AND check `get_throttled` for a clean `0x0`
after a full power cycle (latched bits clear only on power-off). An
intermittent cable/connector shows as "one undervoltage event at boot (second
7-8) then stable" — the boot-time current spike is the canary for marginal
contacts. Also check `journalctl --list-boots`: multiple clean boots with
manual shutdowns in between = user physically toggling the device, not a crash.
