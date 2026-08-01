#!/bin/bash
# Helper: say a line with edge-tts voice, save and play
# Usage: sayit <voice_name> <text> <output_name>
# Voices: Diego, Elsa, Isabella, Giuseppe
DIR="${HERMES_TALKSHOW_DIR:-$HOME/voice-memos/hermes-talkshow-live}"
mkdir -p "$DIR"

voice="it-IT-${1}Neural"
text="$2"
file="$3"

edge-tts --voice "$voice" --text "$text" --write-media "${DIR}/${file}.mp3" 2>/dev/null
afplay "${DIR}/${file}.mp3"
echo "${DIR}/${file}.mp3"
