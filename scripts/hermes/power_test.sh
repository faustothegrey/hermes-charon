#!/bin/bash
set -u
LOG=/tmp/power_test.log
: > "$LOG"
SPID=""
cleanup() {
  [ -n "$SPID" ] && kill $SPID 2>/dev/null && wait $SPID 2>/dev/null
  pkill -f "yes > /dev/null" 2>/dev/null
  sudo systemctl start undervoltage-protect.service 2>/dev/null
  echo "--- RIPRISTINO --- gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" >> "$LOG"
}
trap cleanup EXIT INT TERM

# 1. rimuovi protezione
sudo systemctl stop undervoltage-protect.service
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do echo ondemand | sudo tee "$c" >/dev/null; done
echo "gov dopo set: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

# 2. stress: stress-ng se presente, altrimenti yes su 4 core
if command -v stress-ng >/dev/null; then
  stress-ng --cpu 4 --timeout 130s >/dev/null 2>&1 &
else
  for i in 1 2 3 4; do yes > /dev/null & done
fi
SPID=$!
echo "test start: $(date +%H:%M:%S) gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) stress_pid=$SPID" | tee -a "$LOG"

# 3. monitoraggio ogni 2s, max 120s
Vmin=9; Tmax=0; UV=0
while [ $SECONDS -lt 120 ]; do
  T=$(vcgencmd measure_temp | tr -d "temp='C")
  V=$(vcgencmd measure_volts | sed 's/volt=//')
  TH=$(vcgencmd get_throttled | sed 's/throttled=//')
  F=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
  echo "$(date +%H:%M:%S) V=$V T=$T TH=$TH F=$F" | tee -a "$LOG"
  Vnum=$(echo "$V" | awk '{printf "%.4f", $1}')
  Vmin=$(echo "$Vmin $Vnum" | awk '{print ($2<$1)?$2:$1}')
  Tint=${T%%.*}; [ "$Tint" -gt "$Tmax" ] && Tmax=$Tint
  case "$TH" in
    0x1|*0x1*) echo "!! UNDERVOLTAGE NOW (bit0)" | tee -a "$LOG"; UV=1; break ;;
  esac
  if [ "$Tint" -ge 79 ]; then echo "!! soglia termica 79C raggiunta, stop stress" | tee -a "$LOG"; break; fi
  sleep 2
done
[ -n "$SPID" ] && kill $SPID 2>/dev/null && wait $SPID 2>/dev/null
pkill -f "yes > /dev/null" 2>/dev/null
echo "--- SUMMARY ---" | tee -a "$LOG"
echo "Vmin=$Vmin Tmax=$Tmax UV_now=$UV TH_final=$(vcgencmd get_throttled)" | tee -a "$LOG"
