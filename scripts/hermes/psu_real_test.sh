#!/bin/bash
# Misura reale PSU peer70: protezioni OFF, governor performance, carico pieno
set -u
echo "is-enabled: $(systemctl is-enabled undervoltage-protect 2>&1)"
echo "gov_before: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
systemctl stop undervoltage-protect
echo performance | tee /sys/devices/system/cpu/cpu[0-3]/cpufreq/scaling_governor >/dev/null
echo "gov_test: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
for i in 1 2 3 4; do yes >/dev/null & done
sleep 6
for i in $(seq 1 10); do
  echo "volt=$(vcgencmd measure_volts | cut -d= -f2) arm=$(vcgencmd measure_clock arm | cut -d= -f2) $(vcgencmd get_throttled)"
  sleep 3
done
killall yes 2>/dev/null
echo "=== RIPRISTINO ==="
systemctl start undervoltage-protect
sleep 2
echo "gov_after: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
echo "throttled_final: $(vcgencmd get_throttled)"
echo "temp: $(vcgencmd measure_temp)"
