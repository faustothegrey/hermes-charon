#!/bin/bash
# restart-gateway.sh — Riavvia il gateway Hermes
# Scritto per essere eseguito da crontab (fuori dal processo gateway)
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
sleep 5
systemctl --user restart hermes-gateway.service
echo "[$(date)] Gateway restart tentato" >> /home/fausto/.hermes/peer-network/restart.log
