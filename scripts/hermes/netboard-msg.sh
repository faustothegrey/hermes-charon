#!/bin/bash
# netboard-msg — Invia un messaggio al display NetBoard
# Usa: netboard-msg "Testo" [options]
#      netboard-msg list|active|clean
QUEUE_SCRIPT="$HOME/.hermes/scripts/netboard_queue.py"

if [ $# -eq 0 ]; then
    echo "Usa: netboard-msg <testo> [--priority N] [--duration N] [--sub '...']"
    echo "     netboard-msg list|active|clean"
    exit 1
fi

case "$1" in
    list|active|clean)
        exec python3 "$QUEUE_SCRIPT" "$@"
        ;;
    *)
        exec python3 "$QUEUE_SCRIPT" send "$@"
        ;;
esac
