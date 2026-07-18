#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-$HOME/.ssh/id_rsa.pub}"

cd "$REPO_DIR"

now() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

echo "[$(now)] Starting Hermes config backup in $REPO_DIR"

# Generate the sanitized configuration snapshot
if command -v python3 >/dev/null 2>&1 && [ -f scripts/generate-backup.py ]; then
  python3 scripts/generate-backup.py
fi

# Optional encrypted secrets bundle using your SSH public key (RSA).
# Decrypt requires the matching SSH private key.
if [ -f "$SSH_PUBLIC_KEY" ] && command -v openssl >/dev/null 2>&1 && command -v ssh-keygen >/dev/null 2>&1; then
  mkdir -p secrets
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  mkdir -p "$tmpdir/hermes-secrets"
  for item in .env auth.json google_token.json google_client_secret.json gateway_state.json pairing state.db; do
    if [ -e "$HERMES_HOME/$item" ]; then
      cp -a "$HERMES_HOME/$item" "$tmpdir/hermes-secrets/"
    fi
  done
  tar -C "$tmpdir" -czf "$tmpdir/hermes-secrets.tar.gz" hermes-secrets
  openssl rand 32 > "$tmpdir/aes.key"
  openssl enc -aes-256-cbc -salt -pbkdf2 -in "$tmpdir/hermes-secrets.tar.gz" -out secrets/hermes-secrets.tar.gz.enc -pass file:"$tmpdir/aes.key"
  ssh-keygen -f "$SSH_PUBLIC_KEY" -e -m PKCS8 > secrets/hermes-secrets.key.pub
  openssl pkeyutl -encrypt -pubin -inkey secrets/hermes-secrets.key.pub -in "$tmpdir/aes.key" -out secrets/hermes-secrets.key.enc
  chmod 600 secrets/hermes-secrets.tar.gz.enc secrets/hermes-secrets.key.enc
  echo "Encrypted secrets bundle updated. Decryption needs matching private key for $SSH_PUBLIC_KEY"
else
  echo "Skipping encrypted secrets bundle: need ssh-keygen, openssl, and $SSH_PUBLIC_KEY" >&2
fi

git add .
if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "backup: update Hermes configuration — $(now)"
fi
git push

echo "[$(now)] Hermes config backup completed."
