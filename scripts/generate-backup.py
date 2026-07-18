#!/usr/bin/env python3
"""Regenerate the sanitized Hermes configuration snapshot for this repo.

This copies configuration/state that is useful for disaster recovery while
excluding runtime junk and plaintext secrets. Secret-like values in YAML/JSON/env
style files are redacted. Encrypted secret bundling is handled by
scripts/backup-hermes.sh.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
REPO_DIR = Path(os.environ.get("REPO_DIR", Path(__file__).resolve().parents[1])).expanduser()

OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Documents" / "Obsidian Vault"))).expanduser()

MANAGED_DIRS = ["config", "skills", "cron", "profiles", "plugins", "memories", "hooks", "obsidian-vault", "inventory", "secrets"]

# Keys that trigger value redaction in config files
SECRET_TOKENS = [
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
]


def redact_text(text: str) -> str:
    """Redact simple YAML/JSON-ish/env assignments containing secret-like keys."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue

        if ":" in stripped:
            key = stripped.split(":", 1)[0]
            if any(tok in key.lower() for tok in SECRET_TOKENS):
                prefix = line[: len(line) - len(line.lstrip())]
                lines.append(f'{prefix}{line.lstrip().split(":", 1)[0]}: "<REDACTED>"')
                continue

        if "=" in stripped:
            key = stripped.split("=", 1)[0]
            if any(tok in key.lower() for tok in SECRET_TOKENS):
                prefix = line[: len(line) - len(line.lstrip())]
                lines.append(f"{prefix}{line.lstrip().split('=', 1)[0]}=<REDACTED>")
                continue

        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def remove_managed_dirs() -> None:
    for name in MANAGED_DIRS:
        p = REPO_DIR / name
        if p.exists():
            shutil.rmtree(p)


def copy_file(src: Path, dst: Path, redact: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if redact:
        try:
            dst.write_text(redact_text(src.read_text(errors="replace")), encoding="utf-8")
        except Exception as exc:
            dst.write_text(f"<unreadable or binary; omitted: {exc}>\n", encoding="utf-8")
    else:
        shutil.copy2(src, dst)


def should_exclude(rel: str, name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat) for pat in patterns)


def copy_tree(src: Path, dst: Path, exclude: tuple[str, ...] = ()) -> None:
    if not src.exists():
        return

    def ignore(dirpath: str, names: list[str]) -> list[str]:
        base = Path(dirpath)
        relbase = base.relative_to(src) if base != src else Path(".")
        ignored: list[str] = []
        for n in names:
            rel = str((relbase / n) if relbase != Path(".") else Path(n))
            if should_exclude(rel, n, exclude):
                ignored.append(n)
        return ignored

    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def redact_copied_configs(root: Path) -> None:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml", ".json", ".env"}:
            try:
                p.write_text(redact_text(p.read_text(errors="replace")), encoding="utf-8")
            except Exception:
                pass


def capture_command(cmd: str, out_name: str) -> None:
    try:
        res = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=60)
        out = (
            f"$ {cmd}\nexit={res.returncode}\n\n"
            f"STDOUT:\n{redact_text(res.stdout)}\n\n"
            f"STDERR:\n{redact_text(res.stderr)}\n"
        )
    except Exception as exc:
        out = f"$ {cmd}\nERROR: {exc}\n"
    (REPO_DIR / "inventory" / out_name).write_text(out, encoding="utf-8")


def write_static_files() -> None:
    (REPO_DIR / ".gitignore").write_text(
        """# Never commit plaintext secrets
.env
auth.json
google_token.json
google_client_secret.json
gateway_state.json
pairing
state.db
*.pem
*.key
*.key.plain
*.tar.gz

# Runtime junk
*.tmp
*.lock
*.pid
*.log
__pycache__/
*.pyc
.DS_Store

# Installed executables are not config
profiles/*/bin/

# Allow encrypted secret artifacts
!secrets/*.enc
!secrets/*.pub
!secrets/MANIFEST.json
!secrets/README.md
""",
        encoding="utf-8",
    )
    (REPO_DIR / "README.md").write_text(
        """# Hermes configuration backup — Raspberry Pi (peer70)

This repository backs up the relevant configuration for the Hermes Agent installation on peer70 (Raspberry Pi).

## What is included

- `config/config.yaml` with secret-looking values redacted
- `config/SOUL.md` and other small Hermes config sidecars
- `skills/` for installed and agent-created Hermes skills
- `cron/` for Hermes scheduled jobs
- `profiles/` without per-profile plaintext secrets, runtime state, or installed binaries
- `plugins/`, `memories/`, `hooks/` when present
- `obsidian-vault/`, a copy of the local Obsidian vault
- `inventory/` command outputs useful during restore/debugging
- `scripts/backup-hermes.sh`, `scripts/generate-backup.py`, and `scripts/restore-hermes.sh`
- `secrets/*.enc`, encrypted secret/state bundle

## What is not committed in plaintext

- `~/.hermes/.env`
- `~/.hermes/auth.json`
- Google OAuth token/client-secret files
- gateway/pairing state
- `state.db`
- private SSH/GPG/API keys

Secrets can be committed only as encrypted artifacts under `secrets/*.enc`.
The current backup uses OpenSSL envelope encryption to the local SSH public key when `scripts/backup-hermes.sh` is run and an RSA SSH public key is available.

Important: if the machine crashes and the matching SSH private key is lost, encrypted secrets cannot be decrypted. Keep an offline copy of the private key, or migrate this repo to a long-term age/GPG recipient.

## Routine backup

```bash
cd ~/Backups/hermes-config
scripts/backup-hermes.sh
```

## Restore

See `RESTORE.md` for the complete restore procedure.
""",
        encoding="utf-8",
    )
    (REPO_DIR / "RESTORE.md").write_text(
        """# Restore procedure — Raspberry Pi (peer70)

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
""",
        encoding="utf-8",
    )


def main() -> None:
    if not HERMES_HOME.exists():
        raise SystemExit(f"Hermes home not found: {HERMES_HOME}")
    remove_managed_dirs()

    # Config files
    (REPO_DIR / "config").mkdir(parents=True, exist_ok=True)
    for fname in [
        "config.yaml",
        "SOUL.md",
        "context_length_cache.yaml",
        "channel_directory.json",
        "gateway_state.json",
        "gateway_voice_mode.json",
        "shell-hooks-allowlist.json",
    ]:
        src = HERMES_HOME / fname
        if src.exists():
            copy_file(src, REPO_DIR / "config" / fname, redact=src.suffix.lower() in {".yaml", ".yml", ".json"})

    # Hermes subdirectories
    copy_tree(HERMES_HOME / "skills", REPO_DIR / "skills", exclude=("*.pyc", "__pycache__", "*.lock"))
    copy_tree(HERMES_HOME / "cron", REPO_DIR / "cron", exclude=("output", "*.lock", "*.log", "*.pid", "__pycache__", "*.pyc"))
    copy_tree(HERMES_HOME / "plugins", REPO_DIR / "plugins", exclude=("*.pyc", "__pycache__"))
    copy_tree(HERMES_HOME / "memories", REPO_DIR / "memories", exclude=("*.lock", "*.tmp", "*.db-shm", "*.db-wal"))
    copy_tree(HERMES_HOME / "hooks", REPO_DIR / "hooks", exclude=("*.log", "*.tmp"))

    # Obsidian vault
    obsidian_excludes = (
        ".trash",
        ".git",
        "*.tmp",
        "*.lock",
        "*.log",
        ".DS_Store",
    )
    if OBSIDIAN_VAULT.exists():
        try:
            copy_tree(OBSIDIAN_VAULT, REPO_DIR / "obsidian-vault", exclude=obsidian_excludes)
            redact_copied_configs(REPO_DIR / "obsidian-vault" / ".obsidian")
            print(f"  obsidian-vault: OK ({OBSIDIAN_VAULT})")
        except PermissionError:
            print(f"  obsidian-vault: SKIPPED (no permission — expected in cron)")
            skipped_dir = REPO_DIR / "obsidian-vault"
            skipped_dir.mkdir(parents=True, exist_ok=True)
            (skipped_dir / ".SKIPPED-NO-PERM").write_text(
                f"Skipped at {datetime.now(timezone.utc).isoformat()}: "
                f"No permission for {OBSIDIAN_VAULT}\n",
                encoding="utf-8",
            )

    # Profiles
    profile_excludes = (
        ".env",
        "auth.json",
        "google_token.json",
        "google_client_secret.json",
        "state.db*",
        "sessions",
        "logs",
        "audio_cache",
        "image_cache",
        "cache",
        "rollback-backups",
        "state-snapshots",
        "sandboxes",
        "bin",
        "*.lock",
        "*.pid",
        "*.tmp",
        "__pycache__",
        "*.pyc",
    )
    copy_tree(HERMES_HOME / "profiles", REPO_DIR / "profiles", exclude=profile_excludes)
    redact_copied_configs(REPO_DIR / "profiles")

    # Inventory / metadata snapshots
    inv = REPO_DIR / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / "backup-metadata.txt").write_text(
        f"Created: {datetime.now(timezone.utc).isoformat()}\nSource: {HERMES_HOME}\nObsidian vault: {OBSIDIAN_VAULT}\nRepo: {REPO_DIR}\n",
        encoding="utf-8",
    )
    for cmd, name in [
        ("hermes config path", "hermes-config-path.txt"),
        ("hermes config check", "hermes-config-check.txt"),
        ("hermes tools list", "hermes-tools-list.txt"),
        ("hermes skills list", "hermes-skills-list.txt"),
        ("hermes profile list", "hermes-profile-list.txt"),
        ("hermes cron list", "hermes-cron-list.txt"),
        ("hermes status --all", "hermes-status-all.txt"),
    ]:
        capture_command(cmd, name)

    # Secrets manifest (lists what SHOULD be encrypted, doesn't store plaintext)
    secrets = REPO_DIR / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    secret_candidates = [".env", "auth.json", "google_token.json", "google_client_secret.json", "gateway_state.json", "pairing", "state.db"]
    manifest = []
    for rel in secret_candidates:
        src = HERMES_HOME / rel
        if not src.exists():
            continue
        if src.is_file():
            st = src.stat()
            manifest.append({"path": rel, "type": "file", "size": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        elif src.is_dir():
            manifest.append({"path": rel, "type": "dir", "file_count": sum(1 for p in src.rglob("*") if p.is_file())})
    (secrets / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (secrets / "README.md").write_text(
        """# Secrets

Plaintext secrets are intentionally not committed.

The backup script can create encrypted files here:

- `secrets/hermes-secrets.tar.gz.enc`
- `secrets/hermes-secrets.key.enc`
- `secrets/hermes-secrets.key.pub`

Current secret-like files are listed in `MANIFEST.json`.
""",
        encoding="utf-8",
    )

    # Static files (updated every run)
    write_static_files()
    print(f"Regenerated sanitized Hermes backup from {HERMES_HOME} into {REPO_DIR}")


if __name__ == "__main__":
    main()
