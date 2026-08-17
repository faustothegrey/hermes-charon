#!/bin/bash
# HMP Healthcheck — runs ON peer70, pings all network peers
# Silent when all healthy. Sends formatted HMP alert to peer128 on failure.

PEER128_HOST="192.168.178.112"
PEER128_PORT="18643"
FAILED=0
ALERTS=""
RESULTS=""

check_peer() {
  local NAME=$1 HOST=$2 PORT=$3
  local PING_OK=1 HMP_OK=1

  ping -c1 -W2 $HOST >/dev/null 2>&1 && PING_OK=0
  local HMP=$(curl -s --max-time 5 http://$HOST:$PORT/hmp/send     -d '{"type":"ping","from":"peer70","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'     -H 'Content-Type: application/json' 2>&1)
  [ $? -eq 0 ] && HMP_OK=0

  if [ $PING_OK -eq 0 ] && [ $HMP_OK -eq 0 ]; then
    RESULTS="$RESULTS $NAME=OK"
  elif [ $PING_OK -eq 0 ] && [ $HMP_OK -ne 0 ]; then
    RESULTS="$RESULTS $NAME=HMP_DOWN"
    ALERTS="$ALERTS,$NAME:HMP_down"
    FAILED=1
  else
    RESULTS="$RESULTS $NAME=DOWN"
    ALERTS="$ALERTS,$NAME:unreachable"
    FAILED=1
  fi
}

# Peer con HMP noto
check_peer "peer128" "$PEER128_HOST" "$PEER128_PORT"
# Altri peer noti sulla LAN (check soft — potrebbero non avere HMP plugin)
for TRIAL in "peer84:192.168.178.84" "peer106:192.168.178.106"; do
  NAME=$(echo $TRIAL | cut -d: -f1)
  HOST=$(echo $TRIAL | cut -d: -f2)
  PING_OK=1
  ping -c1 -W1 $HOST >/dev/null 2>&1 && PING_OK=0
  if [ $PING_OK -eq 0 ]; then
    HMP_OK=1
    curl -s --max-time 3 http://$HOST:18643/hmp/send       -d '{"type":"ping","from":"peer70","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'       -H 'Content-Type: application/json' >/dev/null 2>&1 && HMP_OK=0
    [ $HMP_OK -eq 0 ] && RESULTS="$RESULTS $NAME=OK" || RESULTS="$RESULTS $NAME=alive_no_HMP"
  fi
done

TS=$(date '+%H:%M')
echo "[$TS]$RESULTS" >> ~/.hermes/logs/hmp-healthcheck.log

if [ $FAILED -ne 0 ]; then
  ALERT_TEXT="⚠️  HMP healthcheck FAIL:${ALERTS#,} — peer128=OK, others:$RESULTS"
  curl -s --max-time 5 http://$PEER128_HOST:$PEER128_PORT/hmp/send     --data-raw "{\"type\":\"message\",\"from\":\"peer70\",\"to\":\"peer128\",\"text\":\"$ALERT_TEXT\"}"     -H 'Content-Type: application/json' >/dev/null 2>&1
  exit 1
fi
exit 0
