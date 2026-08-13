# Undervoltage vs Thermal Throttling — Diagnosis Workflow (RPi)

Diagnose "Pi is slow / crashing / throttled" by separating ELECTRICAL (PSU/cable)
from THERMAL (heat) causes. Every Pi admin hits this; do it in this order.

## 1. Decode `vcgencmd get_throttled` bits

```bash
vcgencmd get_throttled        # hex bitmask
vcgencmd measure_volts        # core voltage
vcgencmd measure_temp         # die temp
```

| Bit | Meaning | Signal |
|-----|---------|--------|
| 0 | Under-voltage **NOW** | ⚠️ electrical problem active |
| 1 | Arm frequency capped NOW | throttling active |
| 2 | Throttled NOW | throttling active |
| 3 | Soft temp limit NOW | 🔥 thermal (80°C) |
| 16 | Under-voltage occurred (latch) | history — resets only on power cycle |
| 17 | Freq cap occurred | history |
| 18 | Throttling occurred | history |
| 19 | Soft temp limit occurred | history |

Key insight: bits 0-3 are **NOW** (current state), bits 16-19 are **occurred**
(latched history that survives reboot until full power cycle). A value like
`0x50005` = UV NOW + throttled NOW + both occurred. `0xe0000` = only historical
thermal bits, nothing active.

**Gotcha:** `throttled` keeps showing `0x50005` for a while after episodes —
the "NOW" bits clear when the firmware sees sustained normal voltage, and
"occurred" bits only clear on full power removal (unplug, not reboot).

## 2. Stress test to separate electrical from thermal

The Pi under NO load reads fine even with a weak PSU. You MUST load all 4 cores:

```bash
# 4 core stress, ~60-90s (background so you can sample)
for i in 1 2 3 4; do timeout 60 sha256sum /dev/zero & done; wait
```

While running, sample every ~10s:
```bash
printf "%s freq=%sMHz throttled=%s volt=%sV temp=%sC\n" \
  "$(date +%H:%M:%S)" \
  "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq | head -c 4)" \
  "$(vcgencmd get_throttled | cut -d= -f2)" \
  "$(vcgencmd measure_volts | cut -d= -f2)" \
  "$(vcgencmd measure_temp | cut -d= -f2 | tr -d "'C")"
```

Interpretation:
- **Electrical (PSU/cable):** new bit 0 (UV NOW) appears under load, voltage
  dips below ~0.85V, freq caps. Voltage stays low/stuck.
- **Thermal:** bit 3 (soft temp limit) appears, temp ≥ 80°C, but voltage stable
  (~0.86V idle is NORMAL — don't be fooled). Throttled may show `0x80008` =
  soft temp NOW + occurred, with ZERO undervoltage bits.
- **Both can coexist.** A marginal PSU + hot August room = crashes that look
  like brownouts but are partly thermal shutdowns.

## 3. Crash-loop forensics (`journalctl --list-boots`)

A Pi that "keeps coming back" after `shutdown -h now` is often crash-looping,
not being rebooted by the user:

```bash
journalctl --list-boots | tail -10   # boots with start—end times
journalctl -b -1 --no-pager | tail -5  # how the previous boot died
```

- Multiple boots ending in `Undervoltage detected!` as the LAST kernel line =
  brownout reset (hardware reset, not clean shutdown).
- Multiple clean shutdowns in a row = USER was power-cycling (trying different
  chargers/cables) — ask what they changed physically.
- A Pi that powers on BY ITSELF while "off" = PSU intermittent: it boots as soon
  as it receives stable current again. Unplug to keep it off.

## 4. Time-of-day pattern analysis

Count events per hour from dmesg (kernel rate-limits duplicate messages, so
dmesg shows the FIRST episodes; journal is the full history):

```python
# events per hour from journal (rate-limit-safe)
import subprocess, time
boot_ts = time.time() - float(open('/proc/uptime').read().split()[0])
out = subprocess.run(['dmesg'], capture_output=True, text=True).stdout
evts = [boot_ts + float(l.split(']')[0].strip('['))
        for l in out.splitlines() if 'Undervoltage' in l]
```

- **Events only in the evening (19:00-23:00)** → grid voltage sag in the
  neighborhood (AC, ovens) + marginal PSU. Try a different wall outlet /
  dedicated line before buying a new PSU.
- **Constant all day** → PSU/cable genuinely undersized.
- **Sudden onset at a specific date/time with no software change** → physical:
  cable moved, PSU dying, something plugged into the same power strip.

## 5. Mitigations while waiting for hardware fix

All soft/reversible; user preference is powersave-only-when-necessary:

```bash
# Reduce peak current draw (biggest software lever):
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
  echo powersave | sudo tee $c >/dev/null
done   # 600MHz fixed → far fewer UV episodes under marginal PSU

# Swap OFF the SD card (SD writes during brownout = corruption risk):
sudo modprobe zram && echo 512M | sudo tee /sys/block/zram0/disksize
sudo mkswap /dev/zram0 && sudo swapon /dev/zram0 && sudo swapoff /var/swap

# Smaller, more frequent dirty flushes (less data lost on crash):
sudo sysctl -w vm.dirty_writeback_centisecs=1500 \
             vm.dirty_expire_centisecs=1000 vm.dirty_ratio=10
```

Make them persistent via a systemd oneshot service
(`After=multi-user.target`, `WantedBy=multi-user.target`) — **rc.local runs too
early on RPi and the cpufreq driver overwrites the governor afterward**, so a
plain rc.local powersave line silently does nothing (verified 2026-08-02).

## 6. Verify the fix

- Repeat the stress test: NOW bits 0-3 must NOT appear; voltage stable.
- `throttled` value only contains historical bits until full power cycle.
- Watchdog pattern: cron every 15 min running `vcgencmd get_throttled`, alert on
  bit 0 (UV NOW), 60-min cooldown, silence = fixed. Persistent state file
  `~/.hermes/state/undervoltage_state.json` for last_alert_ts.

## Pitfall: `measure_volts` in idle is misleading

`vcgencmd measure_volts` returns ~0.85-0.87V at idle even on healthy Pis —
this is the idle core voltage, NOT a sign of undervoltage. Only a dip DURING
the 4-core stress test is diagnostic. Never conclude "PSU is fine/broken" from
an idle voltage reading alone.
