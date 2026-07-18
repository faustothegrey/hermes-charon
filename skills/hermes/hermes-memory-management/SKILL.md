---
name: hermes-memory-management
category: hermes
description: Diagnose, consolidate, and extend Hermes Agent memory — built-in MEMORY.md/USER.md optimization, provider selection for constrained hardware, and zero-cost external plugins.
version: 1.0.0
author: agent
created_by: agent
platforms: [linux, macos]
triggers:
  - hermes memory
  - memory provider
  - memory consolidation
  - memory full
  - USER.md
  - MEMORY.md
  - memory plugin
  - holographic
  - memory limit
  - memoria piena
  - consolidare memoria
tags:
  - hermes
  - memory
  - consolidation
  - holographic
  - memory-provider
  - constrained-hardware
  - raspberry-pi
---

# Hermes Memory Management

Diagnostics, consolidation, and extension of Hermes Agent's persistent memory. Covers the built-in two-tier store (MEMORY.md / USER.md) and external provider selection for resource-constrained or zero-budget environments.

---

## 1. Diagnostics

Check current state via the system prompt header at session start:

```
MEMORY (your personal notes) [32% — 705/2,200 chars]
USER PROFILE (who the user is) [98% — 1,351/1,375 chars]
```

Or read the raw files:

```bash
cat ~/.hermes/memories/MEMORY.md
cat ~/.hermes/memories/USER.md
```

| Store | Purpose | Limit | Action threshold |
|---|---|---|---|
| `MEMORY.md` | Agent's personal notes — env facts, lessons, conventions | 2,200 chars | ≥80% → consolidate |
| `USER.md` | User profile — preferences, style, personal info | 1,375 chars | ≥80% → consolidate |

### What to look for in content

- **Secrets in memory** — passwords, API keys, tokens. Remove immediately with `memory(action='remove', old_text='password')`. Memory is injected into every system prompt and could leak.
- **Duplicate or overlapping entries** — e.g., two peer descriptions that could merge.
- **Outdated info** — peer IP changes, deprecated workflows.
- **Verbose entries** — can be shortened without losing signal.

---

## 2. Consolidation Strategy

### When to consolidate

- Capacity ≥80% for either store
- Multiple entries reference the same topic (merge them)
- A password or secret is present (remove them)
- Adding a new entry would exceed the limit (error returned)

### How to consolidate

**Best pattern: batch write_file on the raw file.**

Use `memory` tool operations when space is tight — the `operations` array applies adds, removes, and replaces atomically against the final budget:

```python
memory(target="user", operations=[
    {"action": "remove", "old_text": "Telegram bot"},
    {"action": "remove", "old_text": "SSH hosts"},
    {"action": "add", "content": "Merged infrastructure entry..."},
])
```

For a clean rewrite (as demonstrated in this session at 98% capacity), use `write_file` on the raw .md file:

```
write_file(path="~/.hermes/memories/USER.md", content="merged entry 1\n§\nmerged entry 2\n...")
```

### Consolidation patterns

| Original entries (N) | Merge target (1) | Strategy |
|---|---|---|
| Telegram bot config, peer SSH details, NetBoard, Obsidian path, peer cooling | **Infrastructure** | Merge all infra/config facts into one atomic entry |
| Email SMTP config, rules | **Email** | Keep separate but shorten verbosity |
| User preferences, style notes | **Profile** | Keep separate, remove duplicate preferences |
| Iron rules / invariants | **Rules** | Keep separate, shorten to essential |

### Consolidation example (real: 1,360→945 chars, 30% freed)

**USER.md — before (7 entries, 1,360 chars):**
- Telegram bot: long description with bot/chat IDs
- peer128: HMP + SSH + routing note
- Email: full SMTP + Gmail + password path + ban warning
- Fausto: preferences + explicit password
- SSH hosts: 3 hosts + deploy method per host
- NetBoard: port + Obsidian path + peer84 cooling
- REGOLA FERREA: SSH rule

**USER.md — after (4 entries, 945 chars):**
- Infrastructure (merged Telegram + SSH + NetBoard + cooling)
- Email (shortened, no verbosity)
- Profile (shortened, **no password**)
- REGOLA FERREA (shortened, same substance)

---

## 3. External Memory Provider Selection

### Provider comparison for constrained/zero-budget environments

| Provider | Cost | ARM/Pi | Dependencies | API key needed | Notes |
|---|---|---|---|---|---|
| **Holographic** | **€0** | ✅ | SQLite (stdlib) | ❌ | **Best for Pi/ARM.** Zero deps, no daemon, sub-ms recall, trust scoring. |
| OpenViking | €0 | ✅ | pip + running server | ✅ (self-hosted) | Tiered L0/L1/L2 loading. Requires server process. |
| Hindsight | €0 local | ⚠️ | PostgreSQL daemon | ❌ local | Best benchmark (94.6%) but heavy — 200-400MB RAM for PG on Pi. |
| Honcho | €0 self-hosted | ⚠️ | pip + server | ✅ | AGPL v3 license. Complex on Pi. |
| Mem0 | Freemium | ✅ | pip + API key | ✅ | Free tier limited. Self-hosted OSS possible. |
| ByteRover | Freemium | ✅ | pip + API key | ✅ | Depends on plan. |
| RetainDB | 💰 Paid | ❌ | Cloud | ✅ | Excluded for budget. |

### Quick decision tree

```
Can you afford cloud/API costs?
  ├── NO ──→ Can you run a daemon/service on this machine?
  │           ├── NO (Pi, low RAM) ──→ Holographic ← BEST for this session
  │           ├── YES, PostgreSQL OK ──→ Hindsight (best accuracy)
  │           └── YES, simple server ──→ OpenViking (tiered loading, token savings)
  └── YES ──→ Mem0 (fastest setup) or Honcho (dialectic modeling) or Hindsight Cloud (multi-machine sync)
```

### Setup

```bash
# Interactive picker (shows all available providers)
hermes memory setup

# Direct provider (skips picker)
hermes memory setup holographic

# Check status
hermes memory status

# Disable external provider (built-in remains)
hermes memory off
```

Config is saved to `~/.hermes/config.yaml`:

```yaml
memory:
  provider: holographic
```

### Holographic specifics

- **Requirements:** None — uses SQLite (stdlib everywhere). NumPy optional for HRR algebra.
- **Setup:** `hermes memory setup holographic` — no pip install, no API key.
- **Tools added:** `fact_store` (9 actions: add, search, probe, related, reason, contradict, update, remove, list), `fact_feedback` (trust scoring).
- **Config** (in `config.yaml` under `plugins.hermes-memory-store`):

| Key | Default | Description |
|---|---|---|
| `db_path` | `$HERMES_HOME/memory_store.db` | SQLite database path |
| `auto_extract` | `false` | Auto-extract facts at session end |
| `default_trust` | `0.5` | Default trust score for new facts |
| `hrr_dim` | `1024` | HRR vector dimensions |

- **Edge case — NumPy absent:** Holographic silently degrades to FTS5-only when numpy is not installed. HRR-based retrieval is disabled but the provider still works.
- **Cost:** zero — no cloud, no API calls, no recurring charges.

### Architecture note: additive, not replacement

External memory providers are **additive** — the built-in MEMORY.md and USER.md remain active alongside them. The external provider adds tools (`fact_store`, `fact_feedback`) and context injection, but never replaces the core two-tier store.

---

## 4. Advanced Patterns

### Daily reflection cron

Schedule a cron job that periodically reviews memory and consolidates:

```python
cronjob(
    schedule="0 3 * * *",  # daily at 3am
    prompt="Review MEMORY.md and USER.md for consolidation opportunities. "
           "Merge related entries, remove stale ones, check for secrets. "
           "Report what was changed.",
    skills=["hermes-memory-management"]
)
```

### Obsidian as secondary storage

Use the Obsidian vault as a deep persistent store for information too large for memory:

- Save long peer notes, research results, or project docs as `.md` notes
- Reference them via the `obsidian` skill when needed
- See also: `skill_view(name="obsidian")`

### Profile isolation

Use separate profiles to prevent memory pollution between contexts:

```bash
hermes profile create work    # isolated memory, skills, sessions
hermes -p work                # run in work profile
```

Each profile has its own `~/.hermes/profiles/<name>/memories/` directory.

---

## Pitfalls

- **Don't put passwords in memory.** Memory is injected into every system prompt. If a password must be referenced, note the file path (e.g., `~/.config/himalaya/virgilio.pass`), never the value.
- **USER.md fills faster than MEMORY.md** because preferences accumulate. Check it more frequently (every 5-10 sessions).
- **External providers don't fix the built-in limit.** The built-in 2,200/1,375 char caps still apply. A provider adds tools and context injection but MEMORY.md and USER.md still need maintenance.
- **Holographic auto_extract is off by default.** Keep it OFF on production/main nodes. The regex-based extraction (`'I prefer...'`, `'we decided...'`) produces noisy, imprecise facts — no context awareness, no negation handling. Manual `fact_store(action='add')` gives far higher quality. Only enable auto_extract on a scratch/experimental profile where noise is acceptable.
- **hermes-agent skill is protected.** Memory configuration guidance must live in this skill, not in the bundled hermes-agent skill.

## References

- `references/memory-provider-comparison.md` — full provider comparison table with Pi/ARM notes, cost analysis, and setup commands.
- Official Hermes memory docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- Official provider guide: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers
- Skill `raspberry-pi`: Pi hardware configuration (display, boot, GPIO)
- Skill `obsidian`: reading/creating notes in the local Obsidian vault
