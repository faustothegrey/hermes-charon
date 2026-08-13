# Undervoltage diagnosis — Charon (peer70) case study

Real session detail from 2026-07-31 → 08-02 on a Raspberry Pi 4 running
Raspberry Pi OS Bullseye (kernel 5.15.61-v8+), used as Hermes coordinator
("Charon"). All commands verified on that box (Python 3.9 — no `X | Y`
type syntax in scripts that run with system python!).

## Symptom timeline (the diagnostic pattern to reuse)

1. User reported "check undervoltage" → `vcgencmd get_throttled` =
   `0x50005`, `measure_volts` = 0.856V, temp 63°C (heat ruled out).
2. dmesg showed `hwmon hwmon1: Undervoltage detected!` lines, but dmesg
   is a CIRCULAR buffer — only ~the last few hours survived. Wrong tool
   for "when did it start".
3. `journalctl --no-pager | grep -i undervoltage` gave the real history:
   first episode **Jul 31 19:43:24**, only 7 episodes that day, then
   1596+ on Aug 01. The 7-day journal proved zero episodes before Jul 31.
4. Per-hour histogram showed the diurnal pattern (17:00→143, 19:00→264,
   21:00→272, 23:00→74): evening grid-load correlation → marginal PSU.
5. After user did `sudo shutdown -h now`, the box was found back up hours
   later: `journalctl --list-boots` showed **9 boots** from 03:17 to 07:46,
   every boot ending with `Undervoltage detected!` as its last line →
   brownout RESET loop, not clean shutdown. The Pi had powered itself
   back on (Pi boots whenever it receives stable current).

### Key interpretations

- "Voltage normalised" BEFORE the first "Undervoltage detected" in the
  journal = an episode was already in progress (normalised is the END of
  an episode). Kernel rate-limits repeated hwmon messages, so counts in
  the journal are lower bounds, not totals.
- `throttled` latched bits (0x10000 = UV occurred, 0x40000 = throttling
  occurred) stay set until reboot — a running `0x50005` with no recent
  dmesg events can still mean "no episode right now". Check the LAST
  event timestamp, not the bitmask, for current state.
- Software mitigation (powersave governor, zram, journal cap) did NOT
  stop the episodes — proof the fault is the PSU/cable, not load spikes.

## Protection measures applied (all revertible)

| Measure | Effect | How |
|---|---|---|
| Governor `powersave` (600MHz fixed) | removes current spikes | sysfs write per-core |
| zram 512M swap, `/var/swap` off | zero SD writes for swap | modprobe zram + swapon |
| journald `SystemMaxUse=100M`, `MaxRetentionSec=7d` | SD write reduction | journald.conf + restart (752M→48M) |
| `vm.dirty_writeback_centisecs=1500`, `dirty_expire=1000`, `dirty_ratio=10` | smaller/frequent flushes | sysctl |
| config backup to GitHub | survive SD death | hermes-backup skill |

Persistence: rc.local worked for zram/journal but **NOT for the governor**
(see SKILL.md pitfall — cpufreq driver restores ondemand after rc.local
runs). The working fix is a systemd oneshot service with
`After=multi-user.target` (undervoltage-protect.service).

## Watchdog script pattern

`~/.hermes/scripts/undervoltage_watchdog.py`, cron `every 15m`,
`no_agent=true`, `deliver=origin`:

- Reads `vcgencmd get_throttled`, alerts only when **bit 0 (NOW)** set.
- Cooldown via `~/.hermes/state/undervoltage_state.json`
  (`last_alert_ts`): persistent problem → 1 alert/hour max; new episode
  after recovery → immediate alert.
- Alert body: volts, temp, event count in last 24h (dmesg timestamps).
- Empty stdout = silent (no delivery). Non-empty = delivered verbatim.
- Python 3.9 note: `def f() -> Optional[int]:` — `int | None` is a
  SyntaxError on Bullseye's system python3 (3.9).

## Related watchdogs (same class)

- `session_watchdog.py` — reads `last_prompt_tokens` from
  `~/.hermes/sessions/sessions.json`, alerts at 70% of the model window
  (see `hermes-session-lifecycle` skill).
- DSI bridge watchdog (`dsi_watchdog.py`) — dmesg pattern match on
  tc358762 errors (see SKILL.md DSI section).

## Environment facts worth remembering

- This Pi is "Charon" = peer70, the Hermes coordinator. RPi4, Bullseye,
  Python 3.9.2 system / 3.11 in hermes venv. wlan0 only (no ethernet →
  NO Wake-on-LAN possible; only smart-plug or physical access can power
  it back on).
- SSH keys: peer70's `~/.ssh/id_rsa` is the shared DR key — copied to
  peer58 (sidecar) so it can reach peer106/138 after peer70 goes down.
- `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>50000000'` — find blobs >50MB in a repo (used to verify a 322MB secrets blob was purged from git history).
