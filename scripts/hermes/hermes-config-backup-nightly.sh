#!/usr/bin/env bash
set -euo pipefail

export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export REPO_DIR="${REPO_DIR:-$HOME/Backups/hermes-config}"
export OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

cd "$REPO_DIR"

now() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

printf '[%s] Starting Hermes config backup in %s\n' "$(now)" "$REPO_DIR"
./scripts/backup-hermes.sh
printf '[%s] Hermes config backup completed.\n' "$(now)"
