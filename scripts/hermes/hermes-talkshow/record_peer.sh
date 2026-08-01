#!/bin/bash
# Record a peer's response text with given voice and play it
# Usage: record_peer <voice> <text> <output_name>
voice="it-IT-${1}Neural"
text="$2"
file="$3"
DIR="${HERMES_TALKSHOW_DIR:-$HOME/voice-memos/hermes-talkshow-live}"

edge-tts --voice "$voice" --text "$text" --write-media "${DIR}/${file}.mp3" 2>/dev/null
afplay "${DIR}/${file}.mp3"
echo "${DIR}/${file}.mp3"
