#!/usr/bin/env bash
# guardiano-peer70.sh — Apre/chiude porta 2222 (SSH) su peer70 via iptables
# Ispirato a guardiano.sh di peer84. peer70 (RPi orchestratore 24/7)
#
# Uso:
#   guardiano-peer70.sh open       # apre porta 2222 per 20 min
#   guardiano-peer70.sh close      # chiude immediatamente
#   guardiano-peer70.sh status     # mostra stato
#   guardiano-peer70.sh keepalive  # prolunga di 20 min
#   guardiano-peer70.sh watchdog   # da eseguire via cron (ogni minuto)
#   guardiano-peer70.sh bootstrap  # configura iptables baseline

STATE_FILE="/tmp/guardiano-peer70-state.json"
KEEPALIVE_FILE="/tmp/guardiano-peer70-keepalive"
PORT=2222
DURATION=1200  # 20 min in secondi
WARN_BEFORE=120  # avviso 2 min prima
LAND_PORTS="22 8642"  # porte sempre aperte per LAN (SSH + Hermes API)

# Colori output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# ============================================================
# Funzioni iptables
# ============================================================

_bootstrap_iptables() {
    # Imposta baseline sicura: DROP default, ma permette:
    # - established/related
    # - loopback
    # - LAN (192.168.178.0/24)

    # Default policy DROP
    sudo iptables -P INPUT DROP
    sudo iptables -P FORWARD DROP

    # Flush existing rules ma non la policy
    sudo iptables -F INPUT
    sudo iptables -F FORWARD

    # Established & related
    sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

    # Loopback
    sudo iptables -A INPUT -i lo -j ACCEPT

    # LAN (subnet locale)
    sudo iptables -A INPUT -s 192.168.178.0/24 -j ACCEPT

    # ICMP (ping)
    sudo iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

    echo -e "${GREEN}✓${NC} Baseline iptables configurata (DROP default, LAN permessa)"
}

_ipt_port_open() {
    local port=$1
    if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        sudo iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        echo -e "${GREEN}✓${NC} Porta $port aperta"
    else
        echo -e "${YELLOW}∼${NC} Porta $port già aperta"
    fi
}

_ipt_port_close() {
    local port=$1
    if sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        sudo iptables -D INPUT -p tcp --dport "$port" -j ACCEPT
        echo -e "${GREEN}✓${NC} Porta $port chiusa"
    else
        echo -e "${YELLOW}∼${NC} Porta $port già chiusa"
    fi
}

_ipt_flush_all() {
    # Rimuove TUTTE le regole ACCEPT per le nostre porte dinamiche
    # (mantiene la baseline)
    while sudo iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; do
        sudo iptables -D INPUT -p tcp --dport "$PORT" -j ACCEPT
    done
}

# ============================================================
# State management
# ============================================================

_save_state() {
    local expiry=$(( $(date +%s) + DURATION ))
    cat > "$STATE_FILE" <<EOF
{
  "port": $PORT,
  "opened_at": $(date +%s),
  "expires_at": $expiry,
  "duration": $DURATION
}
EOF
}

_clear_state() {
    rm -f "$STATE_FILE" "$KEEPALIVE_FILE"
}

_load_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo ""
        return 1
    fi
    cat "$STATE_FILE"
}

# ============================================================
# Comandi
# ============================================================

open_port() {
    echo -e "${GREEN}🔓 Apertura porta $PORT...${NC}"

    # Bootstrap se iptables non è configurato
    if ! sudo iptables -C INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
        _bootstrap_iptables
    fi

    _ipt_port_open "$PORT"
    _save_state
    _show_status
}

close_port() {
    echo -e "${RED}🔒 Chiusura porta $PORT...${NC}"
    _ipt_port_close "$PORT"
    _clear_state
    _show_status
}

show_status() {
    local state
    state=$(_load_state)
    if [ -z "$state" ]; then
        # Verifica se per caso c'è una regola iptables senza state file
        if sudo iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
            echo -e "${YELLOW}⚠ Porta $PORT APERTA (iptables) ma senza state file${NC}"
            echo "  Usa 'open' per resettare il timer"
        else
            echo -e "${RED}⛔ CHIUSA${NC}"
        fi
        return 0
    fi

    local expires_at port
    expires_at=$(echo "$state" | python3 -c "import sys,json; print(json.load(sys.stdin)['expires_at'])")
    port=$(echo "$state" | python3 -c "import sys,json; print(json.load(sys.stdin)['port'])")

    local now
    now=$(date +%s)
    local remaining=$(( expires_at - now ))

    if [ $remaining -le 0 ]; then
        echo -e "${RED}⛔ Porta $port — SCADUTA${NC}"
        # Auto-cleanup: chiudi se scaduto
        _ipt_port_close "$port"
        _clear_state
        return 0
    fi

    local mins=$(( remaining / 60 ))
    local secs=$(( remaining % 60 ))
    echo -e "${GREEN}🔓 APERTA (${mins}m ${secs}s rimanenti) — porta $port${NC}"

    if [ -f "$KEEPALIVE_FILE" ]; then
        echo -e "  ${YELLOW}🔁 Keepalive attivo${NC}"
    fi
}

keepalive() {
    if [ ! -f "$STATE_FILE" ]; then
        echo -e "${RED}❌ Nessuna apertura attiva. Usa 'open' prima.${NC}"
        return 1
    fi

    touch "$KEEPALIVE_FILE"
    _save_state
    echo -e "${GREEN}🔁 Keepalive applicato — timer resettato a ${DURATION}s${NC}"
}

watchdog() {
    # Da eseguire ogni minuto via cron
    local state
    state=$(_load_state)
    if [ -z "$state" ]; then
        # Nessuna apertura: assicurati che la porta sia chiusa
        if sudo iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
            _ipt_port_close "$PORT"
        fi
        return 0
    fi

    local expires_at
    expires_at=$(echo "$state" | python3 -c "import sys,json; print(json.load(sys.stdin)['expires_at'])")

    local now
    now=$(date +%s)
    local remaining=$(( expires_at - now ))

    if [ $remaining -le 0 ]; then
        echo "[watchdog] Porta $PORT scaduta — chiusura"
        _ipt_port_close "$PORT"
        _clear_state
        return 0
    fi

    # Se keepalive flag è presente, resetta il timer
    if [ -f "$KEEPALIVE_FILE" ]; then
        _save_state
        rm -f "$KEEPALIVE_FILE"
        echo "[watchdog] Keepalive applicato — reset timer"
    fi

    # Avviso se in scadenza
    if [ $remaining -le $WARN_BEFORE ] && [ $remaining -gt 0 ]; then
        local mins=$(( remaining / 60 ))
        local secs=$(( remaining % 60 ))
        echo "[watchdog] ⚠ Porta $PORT in scadenza tra ${mins}m ${secs}s"
    fi
}

# ============================================================
# Main
# ============================================================

case "${1:-}" in
    open|apri)
        open_port
        ;;
    close|chiudi)
        close_port
        ;;
    status|stato)
        show_status
        ;;
    keepalive|sisisi)
        keepalive
        ;;
    watchdog)
        watchdog
        ;;
    bootstrap)
        _bootstrap_iptables
        ;;
    *)
        echo "Uso: $0 {open|close|status|keepalive|watchdog|bootstrap}"
        echo ""
        echo "  open        — apre porta $PORT per $((DURATION/60)) min"
        echo "  close       — chiude porta $PORT"
        echo "  status      — mostra stato"
        echo "  keepalive   — prolunga apertura di $((DURATION/60)) min"
        echo "  watchdog    — controllo automatico (da cron)"
        echo "  bootstrap   - configura iptables baseline"
        exit 1
        ;;
esac
