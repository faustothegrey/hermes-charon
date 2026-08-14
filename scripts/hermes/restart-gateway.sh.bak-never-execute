#!/bin/bash
# Restart gateway peer70 (plugin patch load) — eseguito da cron no_agent
PID=$(ps aux | grep 'hermes_cli.main gateway' | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$PID" ]; then
  kill -9 "$PID"
  echo "Gateway $PID killed — systemd riavvia automaticamente"
else
  echo "Gateway process non trovato"
fi
