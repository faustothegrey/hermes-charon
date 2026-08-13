#!/bin/bash
# PSU real-measure test: protections OFF, ondemand, full CPU load, sample, restore.
set -u
CORE=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
PIDS=""
cleanup() {
  kill $PIDS 2>/dev/null
  for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do echo powersave > "$c" 2>/dev/null || true; done
  systemctl start undervoltage-protect.service 2>/dev/null || true
  echo "--- RESTORED: governor=$(cat $CORE) service=$(systemctl is-active undervoltage-protect.service)"
}
trap cleanup EXIT

# 1) protections OFF
systemctl stop undervoltage-protect.service
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do echo ondemand > "$c" 2>/dev/null; done
echo "governor=$(cat $CORE) (ondemand = no cap)"

# 2) real load on 4 cores
for i in 1 2 3 4; do
  sha256sum /dev/zero > /dev/null &
  PIDS="$PIDS $!"
done
sleep 3

# 3) sample 60s
echo "t(s) throttled volt temp_freq"
for i in $(seq 1 12); do
  echo "$((i*5)) $(vcgencmd get_throttled | cut -d= -f2) $(vcgencmd measure_volts | cut -d= -f2) $(vcgencmd measure_temp | cut -d= -f2 | tr -d "'C") $(vcgencmd measure_clock arm)"
  sleep 5
done
