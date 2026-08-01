#!/bin/bash
# send-harness-email.sh — Send harness-first email via Himalaya
set -euo pipefail

HIMALAYA="/home/fausto/.local/bin/himalaya"
BODY_FILE="/tmp/harness_first_email_body.txt"

# Extract body (skip To:/Subject: headers, take everything after first blank line)
awk 'BEGIN{found=0} /^$/{found=1; next} found{print}' /tmp/harness_first_email_to_fausto.txt > "$BODY_FILE"

"$HIMALAYA" send \
  --to "fausto.lelli@gmail.com" \
  --subject "Hermes harness-first / stable-operation-first — piano condiviso" \
  --body-file "$BODY_FILE"

echo "EMAIL_SENT_OK"
