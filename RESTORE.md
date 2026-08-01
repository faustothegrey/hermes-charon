# Restore procedure — Raspberry Pi (peer70)

This file documents how to restore the Hermes Agent setup and the operational-memory harnesses backed up in this repository.

## 0. Critical prerequisite: secret decryption key

Encrypted secrets in `secrets/*.enc` were encrypted to the SSH public key from the original machine:

```text
~/.ssh/id_rsa.pub
```

To restore `.env`, `auth.json`, OAuth tokens, gateway state, and `state.db`, you need the matching private key, usually:

```text
~/.ssh/id_rsa
```

If that key is lost, the plaintext configuration can still be restored, but secrets must be recreated with `hermes setup`, `hermes auth`, and gateway/platform setup.

## 1. Install base software on the new machine

Install Hermes Agent first:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Required restore tools:

```bash
# openssl, git are pre-installed on Raspberry Pi OS
```

## 2. Clone this backup repo

```bash
mkdir -p ~/Backups
git clone git@github.com:faustothegrey/hermes-charon.git ~/Backups/hermes-config
cd ~/Backups/hermes-config
```

If SSH to GitHub is not ready yet, add your GitHub SSH key first, or clone via HTTPS temporarily.

## 3. Restore Hermes config and secrets

For full restore with encrypted secrets:

```bash
cd ~/Backups/hermes-config
SSH_PRIVATE_KEY=~/.ssh/id_rsa scripts/restore-hermes.sh
```

For config-only restore without secrets:

```bash
cd ~/Backups/hermes-config
scripts/restore-hermes.sh
```

The script restores:

- `~/.hermes/config.yaml`
- `~/.hermes/skills/`
- `~/.hermes/cron/`
- `~/.hermes/profiles/`
- `~/.hermes/plugins/`
- `~/.hermes/memories/`
- `~/.hermes/hooks/`
- `~/.hermes/scripts/` (da `scripts/hermes/` nel repo)
- encrypted secrets/state, if the private key works

## 4. Restore Obsidian vault

The restore script also restores the vault backup from:

```text
obsidian-vault/
```

to:

```text
~/Documents/Obsidian Vault
```

Override the destination if needed:

```bash
OBSIDIAN_VAULT_PATH="/path/to/Obsidian Vault" scripts/restore-hermes.sh
```

## 5. Verify Hermes

Run:

```bash
hermes config check
hermes doctor
hermes tools list
hermes skills list
hermes profile list
hermes cron list
```

For gateway:

```bash
hermes gateway status
```

## 6. Routine backup after restore

Once the machine is working again, update the backup with:

```bash
cd ~/Backups/hermes-config
scripts/backup-hermes.sh
```
