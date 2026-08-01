# Undervoltage detection & mitigation (Raspberry Pi)

Chronic undervoltage from an under-powered PSU is the #1 silent killer of
Pi SD cards. This is the full recipe used on peer70/Charon (RPi 4, Bullseye).

## Detection

```bash
vcgencmd get_throttled     # e.g. 0x50005
vcgencmd measure_volts     # e.g. 0.8563V (healthy under load: ~1.2V)
vcgencmd measure_temp      # distinguish undervoltage from thermal throttling
dmesg | grep -i undervoltage | tail   # event log with timestamps
```

Decode `get_throttled` bits (value is hex):
- bit 0  (0x1)      = under-voltage **NOW**
- bit 1  (0x2)      = arm frequency capped NOW
- bit 2  (0x4)      = throttled NOW
- bit 3  (0x8)      = soft temp limit NOW
- bit 16 (0x10000)  = under-voltage has **OCCURRED** (latched since boot)
- bit 18 (0x40000)  = throttling has OCCURRED (latched)

`0x50005` = 0x1 + 0x4 + 0x10000 + 0x40000 → UV NOW + throttled NOW +
both occurred. **The latched "occurred" bits never clear until reboot** —
so the value staying 0x50005 after mitigation is NOT proof the problem
persists; the NOW bits (0x1/0x2/0x4) are the live signal.

Count events per 24h from dmesg timestamps (boot-relative seconds) to
quantify severity (peer70: 110 events/24h = PSU seriously under-powered).

## Mitigation (all soft, reversible — no reboot needed for most)

Order of impact, all written to `/etc/rc.local` for persistence:

### 1. Pin CPU governor to powersave (biggest win)
With a weak PSU, the SoC boosting to max freq (1.5GHz) draws current
spikes the PSU can't supply → UV events. Pinning to 600MHz fixed freq
removes the spikes:

```bash
for _c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
  echo powersave > "$_c" 2>/dev/null || true
done
# verify: cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq → 600000
```

Reversible: `echo ondemand > .../scaling_governor` per core (after PSU fix).

### 2. Move swap off the SD card (zram)
A swap FILE on SD = continuous writes to the very card UV can corrupt.
Replace with compressed RAM swap (zero SD wear):

```bash
modprobe zram
echo 512M > /sys/block/zram0/disksize
mkswap /dev/zram0 && swapon /dev/zram0
swapoff /var/swap        # disable the SD swap file
```
`swapon --show` should list only `/dev/zram0`.

### 3. Aggressive dirty writeback (less data at risk on crash)
```bash
sysctl -w vm.dirty_writeback_centisecs=1500 \
        vm.dirty_expire_centisecs=1000 \
        vm.dirty_ratio=10
```
Smaller, more frequent flushes = less data lost if a UV spike kills a write.

### 4. Cap systemd journal (systemd --user is often top SD writer)
`/etc/systemd/journald.conf`:
```
SystemMaxUse=100M
SystemKeepFree=200M
MaxRetentionSec=7d
```
then `sudo systemctl restart systemd-journald`. Real result: 752MB → 48MB.
`journalctl --disk-usage` to verify. The journal is a top cumulative SD
writer on Pi (check with `/proc/<pid>/io` read_bytes/write_bytes deltas —
systemd --user routinely beats the app process).

## Persistence — /etc/rc.local

All four blocks go in `/etc/rc.local` before `exit 0` (backup the file
first; `sudo bash -n /etc/rc.local` to validate syntax). This runs at
every multiuser boot, no systemd unit needed.

## Watchdog cron (alert on Telegram when UV is NOW)

Classic no_agent watchdog: read `get_throttled`, if bit 0 set AND
cooldown elapsed (state file `~/.hermes/state/undervoltage_state.json`,
`last_alert_ts`), print alert → delivered verbatim by cron. Cooldown 60min
prevents spam while persisting; a new episode after recovery re-alerts.

Key alert contents: volts, temp, events/24h, and explicit note that the
fix is physical (5V/3A official PSU + short thick cable 26AWG or less) —
do NOT promise a remote fix.

Working script: `~/.hermes/scripts/undervoltage_watchdog.py` on peer70,
cron `undervoltage-watchdog` every 15m. **Python 3.9 (Bullseye): use
`Optional[int]` not `int | None`** (see main SKILL.md Python table).

## Restoration checklist (after PSU replacement)

1. `echo ondemand > /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
2. `vcgencmd get_throttled` → NOW bits (0x1/0x2/0x4) should clear within
   minutes; measure_volts should rise toward ~1.2V under load
3. Optionally restore SD swap file / revert journal limits (keep zram —
   it's strictly better)
4. Reboot once to clear latched "occurred" bits, confirm 0x0 baseline
