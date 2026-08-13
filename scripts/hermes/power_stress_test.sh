#!/bin/bash
# power_stress_test.sh — stress test PSU/termico a regime pieno (ondemand 1.5GHz)
# Uso: bash power_stress_test.sh [durata_secondi]
# Campiona ogni 5s: V / T / TH(bits throttling) / F
# TH bits: 0x1=undervoltage NOW, 0x4=soft-temp NOW, 0x8=throttling NOW,
#          0x10000=undervoltage occurred, 0x40000=soft-temp occurred, 0x80000=throttling occurred
# Exit: ripristina sempre governor=powersave e uccide gli stressor.

DUR=${1:-120}
SAMPLE=5
OUT=/tmp/power_stress_$(date +%H%M%S).log
PIDS=()

cleanup() {
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  sudo sh -c 'for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do echo powersave > "$c"; done'
  echo "== restore: gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) F=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)"
  echo "== log: $OUT"
}
trap cleanup EXIT

# regime pieno
sudo sh -c 'for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do echo ondemand > "$c"; done'
echo "gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor) — stress ${DUR}s, sample ${SAMPLE}s"

# 4 stressor CPU (uno per core)
for i in 1 2 3 4; do
  ( while :; do :; done ) & PIDS+=($!)
done

# campionamento
END=$((SECONDS + DUR))
while [ $SECONDS -lt $END ]; do
  V=$(vcgencmd measure_volts | cut -d= -f2)
  T=$(vcgencmd measure_temp | tr -dc '0-9.')
  TH=$(vcgencmd get_throttled | cut -d= -f2)
  F=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
  echo "$(date +%H:%M:%S) V=$V T=${T}C TH=$TH F=$F" | tee -a "$OUT"
  sleep $SAMPLE
done

# riepilogo eventi
echo "== SUMMARY =="
echo "undervoltage_now:   $(grep -c 'TH=0x[0-9a-f]*[13579bdf]' "$OUT")" 2>/dev/null
echo "softtemp_occurred:  $(grep -cE 'TH=0x[0-9a-f]*[4c]' "$OUT" || true)"
echo "events: $(grep -oE 'TH=0x[0-9a-f]+' "$OUT" | sort | uniq -c | tr '\n' ' ')"
