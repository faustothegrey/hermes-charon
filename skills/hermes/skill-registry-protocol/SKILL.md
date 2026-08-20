---
name: skill-registry-protocol
type: custom
version: 1.0.1
phase: "1"
description: "Use when developing, versioning, or distributing skills in the mesh: every skill is versioned, version bumps are mandatory on improvement, the current coordinator is notified of every new version, and the registry tracks everything. This skill itself is distributed to all mesh agents."
---

# Skill Registry Protocol — versioned skills, coordinator notification

Mesh-wide protocol (Fausto, 18/08): **skills are versioned artifacts. Anyone who improves a skill MUST bump its version. Anyone who publishes a new version MUST notify the current coordinator. The registry is the record.**

## Rules (mandatory)

1. **Every skill is versioned.** `version:` in frontmatter (semver: `MAJOR.MINOR.PATCH`). No unversioned skill in the mesh.
2. **Improvement ⇒ version bump.** Any change to a skill (fix, addition, pitfall) bumps PATCH (or MINOR/MAJOR per impact). Committing a change without bumping the version is a protocol violation.
3. **New version ⇒ notify coordinator.** The peer that bumps a version sends a registry notice to the current coordinator (peer70 by policy). Content: skill name, old version, new version, one-line change summary, artifact hash if distributed.
4. **Registry is the record.** `~/.hermes/registry/` on peer70: `registry.json` (index) + `peers/<peer>.json` (manifests). Each skill entry carries `version` + `version_checked_at`. Publish via `registry-publish.py`.
5. **Distribution is explicit.** SCP for skill dirs (1-6MB), HMP only for payloads <2KB. Backup target before replacing (`mv skill skill.bak-<ver>`), purge `__pycache__` after.
6. **This skill is distributed to all agents** — it defines how the mesh versions and coordinates skills. An agent that does not hold it must receive it (SCP) as part of onboarding.

Coordinator (peer70) then updates the peer manifest + registry index.

## Coordinator workflow on receiving a registry notice

When a peer reports a new skill version, the coordinator does NOT record it
blindly — a notice is a claim until verified:

1. **Verify the claim** (SSH to the reporting peer):
   ```bash
   ssh <user>@<peer-ip> "grep '^version' ~/.hermes/skills/<cat>/<skill>/SKILL.md; stat -c '%y' ~/.hermes/skills/<cat>/<skill>/SKILL.md"
   ```
   Cross-check mtime (fresh) + version (matches the notice). If the peer
   distributed an artifact, verify sha256 of the packaged file.
2. **Update the peer manifest** (`registry/peers/<peer>.json`): set the new
   `version` + `version_checked_at` (now). Do NOT touch other peers' entries.
3. **Update the index** (`registry.json`) only if the index carries versions
   (it usually carries just names — then only bump `updated_at`).
4. **Confirm to the peer** (HMP reply): "registrato <skill> v<new> nel manifest
   di <peer> (checked_at <ts>)" or report the mismatch if verification failed.
5. **Log the change** in the vault if it is a notable version (MINOR/MAJOR or
   behavior change): `session-facts` or a skill changelog.

Example verification for a bump claimed by peer141:
```bash
ssh fausto@192.168.178.141 "grep '^version' ~/.hermes/skills/hermes/hermes-hmp/SKILL.md; stat -c '%y' ~/.hermes/skills/hermes/hermes-hmp/SKILL.md"
# expect: version: 1.27.0 and an mtime newer than the last recorded checked_at
```

A mismatch (version differs, mtime stale, hash wrong) is reported back to the
peer and NOT recorded. The registry must never hold an unverified version.

## Registry notice (preferred path)

```json
{
  "hmp_version": "1.0",
  "from": "<peer_id>",
  "to": "peer70",
  "type": "request",
  "payload": {"text": "REGISTRY NOTICE: skill <name> v<old> -> v<new>. Change: <one line>. Hash: <sha256> (if distributed)."},
  "provenance": "organic_live"
}
```

Coordinator (peer70) then updates the peer manifest + registry index.

## Local Skill registry layout

```
~/.hermes/registry/
├── registry.json          # index: registry_version, updated_at, peers{...}
├── peers/<peer>.json      # per-peer manifest: host, skills[{name,version,version_checked_at}], plugins, skill_count
├── dist/                  # packaged skill artifacts (tar.gz/zip + .sha256 sidecar)
├── registry-publish.py    # publish manifest (auto-scan skills+plugins)
└── registry-server.py     # optional registry status server
```

Skill entries in manifests carry: `name`, `version`, `category`, `version_checked_at` (timestamp of verification — a version without checked_at is a claim, not a fact).

## Publishing a skill to the registry

```bash
python3 ~/.hermes/registry/registry-publish.py --dry-run   # preview
python3 ~/.hermes/registry/registry-publish.py             # publish manifest
```

For distribution packages: create `dist/<skill>-<version>.tar.gz` + `.sha256` sidecar (external, never recursive inside the archive).

## Pitfalls

- **Version without `version_checked_at`/mtime is ambiguous** (lesson 18/08, peer136): two peers can truthfully report different versions at different times. Always pair version with its checked timestamp.
- **The registry index may be stale** (peer70 manifest said capability-reuse 2.2.0 while runtime was 2.6.0): the registry is the publication record, not the runtime. Verify runtime separately (SSH + sha256).
- **registry.json vs peers/<peer>.json**: index holds peer lists; manifests hold per-skill versions. Keep both updated.
- **Never edit the registry during a publish race** — publish is peer70-authoritative; other peers read-only.
- **Skill version bumps from OTHER peers**: verify on your side (SSH, mtime, sha256) before recording — a notice is a claim until verified.

## Verification

- Every skill in `~/.hermes/skills/**` has a `version:` frontmatter.
- After any skill edit: version bumped + registry notice sent to coordinator.
- Registry manifests show current version + checked_at.
- New mesh agent onboarding includes: this skill + memory-vault-hybrid + hermes-hmp + code-dev-reviewer.
