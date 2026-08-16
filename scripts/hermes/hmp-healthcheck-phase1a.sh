#!/bin/bash
# HMP Phase 1a Watchdog — runs on peer70, sends REAL health-check requests
# to peer141 (and pings other peers) with EXPLICIT scheduled provenance.
#
# Phase 1a (reviewer 2026-08-16): scheduled traffic must be declared
# `scheduled:true` so the consumer_loop classifies it `scheduled_protocol`
# (tuning/challenge + G9 pipeline-health), NEVER organic_live.
#
# This is operational mesh activity, not organic evidence.

PEER141_HOST="192.168.178.141"
PEER141_PORT="18643"
FAILED=0
ALERTS=""
RESULTS=""

# ── Phase 1a: real health-check request to peer141 (declared scheduled) ──
check_peer141() {
  local NAME=peer141
  local PING_OK=1 HMP_OK=1
  ping -c1 -W2 $PEER141_HOST >/dev/null 2>&1 && PING_OK=0
  local TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local HMP=$(curl -s --max-time 8 http://$PEER141_HOST:$PEER141_PORT/hmp/send \
      -d "{\"from_peer\":\"peer70\",\"to\":\"peer141\",\"session_id\":\"watchdog-p70-p141\",\"text\":\"check HMP health for peer141\",\"scheduled\":true,\"traffic_type\":\"scheduled_protocol\"}" \
      -H 'Content-Type: application/json' 2>&1)
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

# ── Existing network ping checks (soft) ──
check_peer_soft() {
  local NAME=$1 HOST=$2 PORT=$3
  local PING_OK=1 HMP_OK=1
  ping -c1 -W1 $HOST >/dev/null 2>&1 && PING_OK=0
  if [ $PING_OK -eq 0 ]; then
    HMP_OK=1
    curl -s --max-time 3 http://$HOST:$PORT/hmp/send \
        -d '{"type":"ping","from":"peer70","timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' \
        -H 'Content-Type: application/json' >/dev/null 2>&1 && HMP_OK=0
    [ $HMP_OK -eq 0 ] && RESULTS="$RESULTS $NAME=OK" || RESULTS="$RESULTS $NAME=alive_no_HMP"
  fi
}

check_peer141
check_peer_soft "peer84" "192.168.178.84" "18643"
check_peer_soft "peer105" "192.168.178.105" "18643"
check_peer_soft "peer106" "192.168.178.106" "18643"

TS=$(date '+%H:%M')
echo "[$TS]$RESULTS" >> ~/.hermes/logs/hmp-healthcheck.log

if [ $FAILED -ne 0 ]; then
  exit 1
fi
exit 0
