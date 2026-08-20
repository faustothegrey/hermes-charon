---
name: memory-vault-hybrid
type: custom
version: 1.0.0
phase: "1"
description: "Use when saving durable facts: hot memory (MEMORY.md) holds only essential data + pointers, the Obsidian vault (~/Documents/Obsidian Vault/Progetti/Hermes/) holds full detail. Prevents memory saturation and lost context across session restarts."
---

# Memory-Vault Hybrid — hot pointers, vault detail

Fausto's rule (18/08): **vault = dati completi, hot = solo essenziale + puntatori.**

## Essential skill — self-contained distribution

This skill is **essential**: it governs how knowledge survives across sessions.
Pin it so no update/cleanup can remove it, and distribute it to other mesh
agents as a self-contained unit (it needs no external dependencies).

**Pin it (protects from deletion):**
```bash
hermes curator pin memory-vault-hybrid
```
Pin guards against deletion only — patches/edits still apply, so you can keep
improving it. See `hermes curator unpin <name>` to reverse.

**Distribute to a mesh peer (SCP — skill dirs are 1-6MB, HMP only for <2KB):**
```bash
scp -r ~/.hermes/skills/hermes/memory-vault-hybrid <user>@<peer-ip>:~/.hermes/skills/hermes/
# then purge __pycache__ on the target and register in the Local Skill registry
```
Every agent that maintains long-lived memory should carry this skill. It is the
first item in the "essential skills" list every agent should hold:
memory-vault-hybrid, hermes-hmp (mesh protocol), code-dev-reviewer (email review loop).

## When to use

- Saving durable facts that are longer than one compact line.
- Session facts / incident records / decisions that a future session must recover.
- Before a context restart or /new ("salva i fatti nella vault e scrivi i puntatori nella hot").
- When memory is near full (warning threshold ~95%).

## Workflow

### 1. Write full detail to the vault

Path: `~/Documents/Obsidian Vault/Progetti/Hermes/`

Filename convention: `session-facts-YYYY-MM-DD-<topic>.md` (or descriptive names like `topology-study-prereg-v1.1.md`).

Structure (proven):
- Title + date + executor
- Numbered sections per topic (max ~10)
- Concrete data: IPs, versions, hashes, trace IDs, decisions, blockers
- No theory — evidence and facts

### 2. Write only essentials + pointers to hot memory

Hot memory entries must be:
- ≤ ~160 chars each
- A fact a future session needs WITHOUT reading the vault (identity: who/what/where)
- A pointer: `Vault: <filename>` at the end when detail matters

Keep in hot: peer identities, policy rules, recurring preferences, tool quirks, known bugs (short version), active task pointers.
Move to vault: full incident analysis, session transcripts, study reports, bundle contents, long technical detail.

### 3. Consolidate when memory is full

When memory write fails with "over the limit":
- Batch: shorten overlapping entries + add the new one in ONE call
- Merge related entries (e.g. cron + session-lifecycle)
- Prefer removing detail already in the vault (replace with pointer)
- Never drop identity facts (who the peers are, policy)

## Pitfalls

- **Memory at 100% blocks writes** — the tool rejects adds. Keep it ≤95% by moving detail to vault proactively.
- **Entries without timestamps are ambiguous** (lesson 18/08, peer136 vs peer70): if a fact can be stale, include the date or version_checked_at.
- **A version string with no checked_at/mtime is a claim, not a fact** (see hermes-hmp skill 3a).
- **Don't store task progress in hot** — use session_search for transcripts; vault for durable state.
- The vault file is the source of truth for detail; the hot memory pointer must name the exact filename.

## Verification

- Memory usage < 95% after consolidation.
- Every hot entry either is self-contained (identity) or ends with `Vault: <exact filename>`.
- The vault file exists and contains the full detail.
- After a session restart, a fresh agent can reconstruct the state from hot pointers + vault files.
