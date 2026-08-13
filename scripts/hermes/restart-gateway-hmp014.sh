#!/bin/bash
# One-shot gateway restart for HMP plugin v0.1.4 (no_agent cron job).
# Kills the gateway; systemd auto-restarts it; polls until agent-card
# reports version 0.1.4. Writes status to a file for post-bounce check.
STATUS=~/.hermes/data/gateway-restart-hmp014.status
echo "start $(date +%H:%M:%S)" > "$STATUS"

PID=$(pgrep -f "hermes_cli.main gateway" | head -1)
if [ -z "$PID" ]; then
  echo "ERROR: no gateway process found" >> "$STATUS"
  exit 1
fi
echo "killing gateway PID $PID" >> "$STATUS"
kill -9 "$PID"

# Poll for new gateway + plugin 0.1.4 (max 90s)
for i in $(seq 1 45); do
  sleep 2
  NEWPID=$(pgrep -f "hermes_cli.main gateway" | head -1)
  if [ -n "$NEWPID" ] && [ "$NEWPID" != "$PID" ]; then
    VER=$(curl -sf --connect-timeout 2 http://127.0.0.1:18643/hmp/agent-card 2>/dev/null | grep -o '"version": *"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ "$VER" = "0.1.4" ]; then
      echo "OK gateway restarted PID $NEWPID, hmp $VER" >> "$STATUS"
      exit 0
    fi
  fi
done
echo "TIMEOUT: gateway up but hmp version not 0.1.4" >> "$STATUS"
exit 1
