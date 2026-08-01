#!/bin/bash
# netboard.sh — avvia/ferma netboard sul display locale
# Uso: ./netboard.sh {start|stop|status}
# Da eseguire sulla console locale del Pi (non SSH)

SCRIPT="/home/fausto/.hermes/scripts/netboard.py"
PIDFILE="/tmp/netboard.pid"

case "${1:-}" in
    start)
        if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "netboard già in esecuzione (PID $(cat $PIDFILE))"
            exit 0
        fi
        # Disabilita il cursore a terminale, avvia pygame su fb0
        echo "Avvio netboard sul display…"
        export SDL_FBDEV=/dev/fb0
        export SDL_VIDEO_DRIVER=fbcon
        nohup python3 "$SCRIPT" > /dev/null 2>&1 &
        echo $! > "$PIDFILE"
        echo "netboard avviato (PID $!) — q/ESC per uscire dal display"
        ;;
    stop)
        if [ -f "$PIDFILE" ]; then
            kill $(cat "$PIDFILE") 2>/dev/null
            rm -f "$PIDFILE"
            echo "netboard fermato"
        else
            pkill -f "netboard.py" 2>/dev/null && echo "netboard fermato" || echo "netboard non in esecuzione"
        fi
        ;;
    status)
        if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "netboard: ✅ ATTIVO (PID $(cat $PIDFILE))"
        else
            echo "netboard: ❌ FERMO"
        fi
        ;;
    *)
        echo "Uso: $0 {start|stop|status}"
        exit 1
        ;;
esac
