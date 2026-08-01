#!/bin/bash
# peer70-watchdog.sh — Monitoraggio completo per peer70 (orchestratore)
# no_agent=true: silenzioso se tutto ok, notifica solo se critico
#
# Controlla: load, RAM, disk, temp, gateway HMP, netboard-web, UPnP

set -euo pipefail

WARN_FILE="/tmp/peer70-watchdog.warn"
STATUS_FILE="$HOME/.hermes/peer-network/peer70_health.json"
mkdir -p "$(dirname "$STATUS_FILE")"

# ── Soglie ──
LOAD_WARN=3.0
LOAD_CRIT=5.0
MEM_FREE_WARN=300   # MB
DISK_WARN=90        # %
TEMP_WARN=75        # °C

# ── Funzione helper ──
notify() {
    local severity="$1" msg="$2"
    # Log to status file
    echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"severity\":\"$severity\",\"msg\":\"$msg\"}" >> "$WARN_FILE"
    # Telegram via curl (silent)
    TG_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$HOME/.hermes/.env" 2>/dev/null | head -1 | cut -d'=' -f2-)
    if [ -n "$TG_TOKEN" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
            -d "chat_id=8508115936" \
            -d "text=[peer70] $severity: $msg" \
            -d "disable_notification=true" >/dev/null 2>&1 || true
    fi
    # Log to Obsidian
    local vault="$HOME/Documents/Obsidian Vault"
    local logfile="$vault/peer70 Health/$(date +%Y-%m-%d).md"
    mkdir -p "$(dirname "$logfile")"
    echo "- $(date '+%H:%M') | $severity | $msg" >> "$logfile"
}

# ── 1. CPU Load ──
read LOAD1 _ _ < /proc/loadavg
LOAD1=$(echo "$LOAD1" | awk '{printf "%.1f", $1}')
if (( $(echo "$LOAD1 > $LOAD_CRIT" | bc -l 2>/dev/null || echo 0) )); then
    notify "CRITICAL" "Load $LOAD1 (soglia $LOAD_CRIT)"
elif (( $(echo "$LOAD1 > $LOAD_WARN" | bc -l 2>/dev/null || echo 0) )); then
    notify "WARN" "Load $LOAD1 (soglia $LOAD_WARN)"
fi

# ── 2. Memoria ──
MEM_AVAIL=$(free -m | awk '/^Mem:/{print $7}')
if [ "$MEM_AVAIL" -lt "$MEM_FREE_WARN" ]; then
    notify "WARN" "RAM libera: ${MEM_AVAIL}MB (soglia ${MEM_FREE_WARN}MB)"
fi

# ── 3. Disco ──
DISK_USED=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USED" -gt "$DISK_WARN" ]; then
    notify "WARN" "Disk ${DISK_USED}% (soglia ${DISK_WARN}%)"
fi

# ── 4. Temperatura ──
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    TEMP=$(awk '{printf "%.0f", $1/1000}' /sys/class/thermal/thermal_zone0/temp)
    if [ "$TEMP" -gt "$TEMP_WARN" ]; then
        notify "WARN" "Temperatura ${TEMP}°C (soglia ${TEMP_WARN}°C)"
    fi
fi

# ── 5. Gateway HMP ──
if ! curl -sf --connect-timeout 3 http://127.0.0.1:18643/health >/dev/null 2>&1; then
    notify "CRITICAL" "HMP gateway :18643 non risponde"
fi

# ── 6. NetBoard web — DISABILITATO (netboard spento 2026-07-30) ──
# Netboard non è più attivo: il check :8191 generava falsi WARN ogni 5 min.

# ── 7. UPnP router ──
if ! timeout 5 upnpc -s >/dev/null 2>&1; then
    notify "WARN" "UPnP router non raggiungibile"
fi

# ── Salva stato ──
{
    echo "{"
    echo "  \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"load\": $LOAD1,"
    echo "  \"mem_mb\": $MEM_AVAIL,"
    echo "  \"disk_pct\": $DISK_USED,"
    echo "  \"temp_c\": ${TEMP:-0},"
    echo "  \"gateway\": $(curl -sf --connect-timeout 2 http://127.0.0.1:18643/health >/dev/null 2>&1 && echo true || echo false)"
    echo "}"
} > "$STATUS_FILE"

# Silenzioso se tutto ok
if [ ! -f "$WARN_FILE" ]; then
    exit 0
fi
