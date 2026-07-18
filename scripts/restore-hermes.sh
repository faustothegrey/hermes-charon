#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SSH_PRIVATE_KEY="${SSH_PRIVATE_KEY:-$HOME/.ssh/id_rsa}"
OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

mkdir -p "$HERMES_HOME"
cd "$REPO_DIR"

# Restore plaintext config
cp -a config/config.yaml "$HERMES_HOME/config.yaml" 2>/dev/null || true
[ -d skills ] && rsync -a --delete skills/ "$HERMES_HOME/skills/"
[ -d cron ] && rsync -a --delete cron/ "$HERMES_HOME/cron/"
[ -d profiles ] && rsync -a profiles/ "$HERMES_HOME/profiles/"
[ -d plugins ] && rsync -a plugins/ "$HERMES_HOME/plugins/"
[ -d memories ] && rsync -a memories/ "$HERMES_HOME/memories/"
[ -d hooks ] && rsync -a hooks/ "$HERMES_HOME/hooks/"

# Restore Obsidian vault
if [ -d obsidian-vault ]; then
  mkdir -p "$(dirname "$OBSIDIAN_VAULT_PATH")"
  rsync -a --delete obsidian-vault/ "$OBSIDIAN_VAULT_PATH/"
  echo "Obsidian vault restored to $OBSIDIAN_VAULT_PATH"
fi

# Decrypt and restore secrets
if [ -f secrets/hermes-secrets.tar.gz.enc ] && [ -f secrets/hermes-secrets.key.enc ]; then
  if [ ! -f "$SSH_PRIVATE_KEY" ]; then
    echo "Encrypted secrets exist, but private key not found: $SSH_PRIVATE_KEY" >&2
    echo "Plaintext config restored. Secrets must be recreated with 'hermes setup'." >&2
  else
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    openssl pkeyutl -decrypt -inkey "$SSH_PRIVATE_KEY" -in secrets/hermes-secrets.key.enc -out "$tmpdir/aes.key"
    openssl enc -d -aes-256-cbc -pbkdf2 -in secrets/hermes-secrets.tar.gz.enc -out "$tmpdir/hermes-secrets.tar.gz" -pass file:"$tmpdir/aes.key"
    tar -C "$tmpdir" -xzf "$tmpdir/hermes-secrets.tar.gz"
    cp -a "$tmpdir/hermes-secrets/"* "$HERMES_HOME/" 2>/dev/null || true
    echo "Secrets restored from encrypted bundle."
  fi
fi

echo "Restore complete."
echo ""
echo "Verify with:"
echo "  hermes config check"
echo "  hermes doctor"
