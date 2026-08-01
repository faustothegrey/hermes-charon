#!/usr/bin/env bash
# ==============================================================
# peer-monitor.sh — Orchestratore rete peer (peer70)
# Pinga tutti i peer conosciuti e scopre nuovi dispositivi LAN
# ==============================================================
set -u
STATUS_FILE="$HOME/.hermes/peer-network/STATUS.md"
STATUS_JSON="$HOME/.hermes/peer-network/status.json"
HISTORY_LOG="$HOME/.hermes/peer-network/history.log"
PEERS_KNOWN="$HOME/.hermes/peer-network/known_peers.txt"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
EPOCH=$(date +%s)

mkdir -p "$HOME/.hermes/peer-network"

# === PEER DEFINITIONS ===
# nome|IP|nota
KNOWN_PEERS=(
  "peer70|127.0.0.1|questo Raspberry Pi (Debian 11 aarch64)"
  "peer84|192.168.178.84|N56VV laptop (Ubuntu 22.04)"
  "peer60|192.168.178.60|Raspberry Pi 3 (Raspbian 9)"
  "peer-host|Faustos-MacBook-Pro-Home-3.fritz.box|Mac (macOS 26.5.1 / vecchio orchestratore)"
)

# === FUNZIONI ===
ping_peer() {
  local ip="$1"
  if ping -c 1 -W 3 "$ip" &>/dev/null; then
    local rtt
    rtt=$(ping -c 1 -W 3 "$ip" 2>/dev/null | tail -1 | grep -oP '\d+\.?\d*/' | head -1 | tr -d '/')
    echo "ONLINE|${rtt:-0}"
  else
    echo "OFFLINE|0"
  fi
}

# === ESECUZIONE ===
output="🌐 **Peer Monitor** — $TIMESTAMP"
output+="\n========================================"

# Ping noti
declare -A RESULTS
output+="\n\n## Stato Peer"
output+="\n| Peer | IP | Macchina | Stato | RTT |"
output+="\n|---|---|---|---|---|"
for peerinfo in "${KNOWN_PEERS[@]}"; do
  IFS='|' read -r name ip note <<< "$peerinfo"
  if [ "$name" = "peer70" ]; then
    RESULTS[$name]="ONLINE"
    output+="\n| **$name** 🏆 | $ip | $note | 🟢 ONLINE (self) | — |"
    continue
  fi
  
  result=$(ping_peer "$ip")
  status=$(echo "$result" | cut -d'|' -f1)
  rtt=$(echo "$result" | cut -d'|' -f2)
  RESULTS[$name]="$status"
  
  case "$status" in
    ONLINE)  icon="🟢" ;;
    OFFLINE) icon="🔴" ;;
  esac
  output+="\n| $name | \`$ip\` | $note | $icon $status | ${rtt}ms |"
done

# Nuovi peer scoperti via ARP
output+="\n\n## Nuovi Dispositivi Rilevati"
new_found=0
neigh_lines=$(ip neigh show dev wlan0 2>/dev/null | grep -v FAILED | grep -v '^fe80' | grep -v '192.168.178.1' | grep -v '192.168.178.84' | grep -v '192.168.178.60')
if [ -n "$neigh_lines" ] && [ "$(echo "$neigh_lines" | grep -c .)" -gt 0 ]; then
  output+="\n| IP | MAC | Note |"
  output+="\n|---|---|---|"
  while IFS= read -r line; do
    local ip mac state
    ip=$(echo "$line" | awk '{print $1}')
    mac=$(echo "$line" | awk '{print $4}')
    state=$(echo "$line" | awk '{print $5}')
    [ "$mac" = "<incomplete>" ] && continue
    host_label=$(host "$ip" 2>/dev/null | grep -oP 'name pointer \K.*' | sed 's/\.$//' || echo "sconosciuto")
    output+="\n| \`$ip\` | $mac | $host_label ($state) |"
    new_found=$((new_found + 1))
  done <<< "$neigh_lines"
else
  output+="\nNessun nuovo dispositivo rilevato."
fi

# Temperature e metriche sistema
temp=$(cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -1)
temp_c=$((temp / 1000))
load=$(cat /proc/loadavg | awk '{print $1", "$2", "$3}')
mem=$(free -h | grep Mem | awk '{print $3" / "$2}')
output+="\n\n## Metriche Sistema (peer70 — orchestratore)"
output+="\n- 🌡️ Temperatura CPU: **${temp_c}°C**"
output+="\n- 📊 Load avg: $load"
output+="\n- 💾 RAM: $mem"
output+="\n- ⏱️ Uptime: $(uptime -p | sed 's/up //')"

# === AGGIORNA FILE STATUS.MD ===
{
  echo "# 🌐 Peer Network — Stato Orchestrato da peer70"
  echo ""
  echo "_Ultimo aggiornamento: $TIMESTAMP_"
  echo ""
  echo "## Stato Peer"
  echo ""
  echo "| Peer | IP | Macchina | Stato | Ultimo RTT |"
  echo "|---|---|---|---|---|"
  for peerinfo in "${KNOWN_PEERS[@]}"; do
    IFS='|' read -r name ip note <<< "$peerinfo"
    if [ "$name" = "peer70" ]; then
      echo "| **$name** 🏆 | $ip | $note | 🟢 ONLINE (orchestratore) | — |"
      continue
    fi
    s="${RESULTS[$name]}"
    case "$s" in
      ONLINE)  ico="🟢" ;;
      OFFLINE) ico="🔴" ;;
    esac
    echo "| $name | \`$ip\` | $note | $ico $s | — |"
  done
  echo ""
  echo "---"
  echo "## Cronologia"
  echo ""
  echo "- $TIMESTAMP — Monitoraggio completato"
} > "$STATUS_FILE"

# === LOG STORICO ===
log_line="$EPOCH|$TIMESTAMP|"
for peerinfo in "${KNOWN_PEERS[@]}"; do
  IFS='|' read -r name ip note <<< "$peerinfo"
  [ "$name" = "peer70" ] && continue
  log_line+="${name}=${RESULTS[$name]} "
done
echo "$log_line" >> "$HISTORY_LOG"

# === DETECT CAMBIAMENTI ===
line_count=$(wc -l < "$HISTORY_LOG")
if [ "$line_count" -ge 2 ]; then
  prev_line=$(tail -2 "$HISTORY_LOG" | head -1)
  curr_line=$(tail -1 "$HISTORY_LOG")
  if [ "$prev_line" != "$curr_line" ]; then
    output+="\n\n⚠️ **Cambiamento di stato rilevato!**"
    # Estrai i campi peer=stato
    prev_peers=$(echo "$prev_line" | cut -d'|' -f3)
    curr_peers=$(echo "$curr_line" | cut -d'|' -f3)
    for word in $prev_peers; do
      pname=$(echo "$word" | cut -d= -f1)
      pstatus=$(echo "$word" | cut -d= -f2)
      cstatus="${RESULTS[$pname]}"
      if [ "$pstatus" != "$cstatus" ] && [ -n "$cstatus" ]; then
        arrow="$([ "$cstatus" = "ONLINE" ] && echo '🟢→ONLINE' || echo '🔴→OFFLINE')"
        output+="\n- $pname: è ora **$arrow**"
      fi
    done
  fi
fi

echo -e "$output"
