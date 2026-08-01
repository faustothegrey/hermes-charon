#!/bin/bash
# load-monitor.sh — monitoraggio carico sistema per peer70
# no_agent=true: esce silenzioso se tutto ok, notifica solo se load eccessivo
# Soglie: load>2.5 = warn, load>4.0 = critico

set -e

# ─── Config ───────────────────────────────────────────────────────────────────
LOAD_WARN=2.5    # load average 1min oltre cui notificare
LOAD_CRIT=4.0    # load critico
UPTIME_THRESH=600  # ignora spike nei primi 10min dopo boot

# ─── Leggi token Telegram dal .env ────────────────────────────────────────────
ENV_FILE="$HOME/.hermes/.env"
if [ -f "$ENV_FILE" ]; then
    TG_BOT_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d ' \t\r\n')
else
    echo "ERRORE: .env non trovato" >&2
    exit 1
fi

TG_CHAT_ID="8508115936"

# ─── Leggi load ───────────────────────────────────────────────────────────────
read LOAD1 LOAD5 LOAD15 REST < /proc/loadavg
UPTIME_SEC=$(awk '{print int($1)}' /proc/uptime)

# Ignora se appena riavviato
[ "$UPTIME_SEC" -lt "$UPTIME_THRESH" ] && exit 0

# Arrotonda load1 a 1 decimale
LOAD1=$(echo "$LOAD1" | awk '{printf "%.1f", $1}')

# Soglia soft via file (per silenziamento manuale)
SILENT_FILE="/tmp/load-monitor-silent"
if [ -f "$SILENT_FILE" ]; then
    SILENT_UNTIL=$(cat "$SILENT_FILE")
    NOW=$(date +%s)
    [ "$NOW" -lt "$SILENT_UNTIL" ] && exit 0
    rm -f "$SILENT_FILE"
fi

# ─── Decidi se notificare ─────────────────────────────────────────────────────
NOTIFY=""
SEVERITY=""

if (( $(echo "$LOAD1 > $LOAD_CRIT" | bc -l) )); then
    NOTIFY="⚠️ ALLERTA CRITICA"
    SEVERITY="CRITICAL"
elif (( $(echo "$LOAD1 > $LOAD_WARN" | bc -l) )); then
    NOTIFY="⚠️ Carico elevato"
    SEVERITY="WARN"
fi

if [ -z "$NOTIFY" ]; then
    # Silenzio — load nella norma
    exit 0
fi

# ─── Raccogli info extra ──────────────────────────────────────────────────────
TOP_CPU=$(ps aux --sort=-%cpu | awk 'NR==2{printf "%.0f%% %s", $3, $11}')
TOP_MEM=$(ps aux --sort=-%mem | awk 'NR==2{printf "%.0f%% %s", $4, $11}')
MEM_TOTAL=$(free -h | awk '/Mem:/{print $3"/"$2}')
TEMP=$(awk '{printf "%.0f", $1/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "?")
LOAD_ALL="$LOAD1 / $LOAD5 / $LOAD15"

MSG="$NOTIFY su peer70

📊 Load: $LOAD_ALL
🌡️  Temp: ${TEMP}°C
💾 RAM: $MEM_TOTAL
🔝 CPU: $TOP_CPU
🔝 MEM: $TOP_MEM"

# ─── Telegram ─────────────────────────────────────────────────────────────────
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TG_CHAT_ID}" \
    -d "text=${MSG}" \
    -d "disable_notification=true" >/dev/null 2>&1

# ─── Email (solo per CRITICAL) ──────────────────────────────────────────────────
if [ "$SEVERITY" = "CRITICAL" ]; then
    TOOL_MEM=$(ps aux --sort=-%mem | head -5 | awk '{printf "%s %.0f%%\\n", $11, $4}' | tr '\n' ' ')
    EMAIL_BODY="Load critico su peer70

Load: $LOAD_ALL
Temperatura: ${TEMP}°C
RAM: $MEM_TOTAL

Processi pesanti:
$TOOL_MEM

$(date '+%Y-%m-%d %H:%M')"

    cat << EOFMSG | himalaya message send 2>/dev/null
From: fausto.lelli@virgilio.it
To: fausto.lelli@virgilio.it
Subject: ⚠ [peer70] Load CRITICO $LOAD1

$EMAIL_BODY
EOFMSG
fi