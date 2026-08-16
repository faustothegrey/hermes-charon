# Publishing a Skill to the Mesh Registry (HMP)

## What "global skill registry" means here

When Fausto says "global skill registry" or "publish a skill so the agent
community can use it", he means the **HMP mesh registry**, NOT the public
Hermes skills hub. `hermes skills publish --to github|clawhub` targets the
open-source hub (GitHub PR / ClawHub submission, needs `GITHUB_TOKEN`/gh auth)
— that is a different thing and is NOT what the mesh uses.

Mesh registry location (coordinator = peer70):
- `~/.hermes/registry/registry.json` — aggregate index: `peers.<peer>.skills`
  (names only), `skill_count`, `plugins`
- `~/.hermes/registry/peers/<peer>.json` — per-peer detail: skills as
  `{"name", "version", "category"}` objects, plugins as `{"name", "version", "enabled"}`
- `~/.hermes/registry/registry-publish.py` — the scan + publish script

## What makes a skill registrable

`registry-publish.py` → `scan_skills()` walks
`~/.hermes/skills/<category>/<name>/SKILL.md` and **only includes skills whose
frontmatter contains `type: custom`**. It parses the `version:` line and uses
the parent directory as the category. Bundled/hub skills (no `type: custom`)
are skipped automatically.

A community skill therefore needs frontmatter like:

```yaml
---
name: <skill-name>
type: custom
version: 1.0.0
description: "<trigger-focused one-liner>"
author: peer70 (Fausto)
status: active
changelog:
  - "1.0.0 — initial release: ..."
---
```

## Publish workflow (on the coordinator, peer70)

1. Create the skill at `~/.hermes/skills/<category>/<name>/SKILL.md` with
   `type: custom` + semantic version + changelog (pattern: capability-reuse).
2. Validate frontmatter: starts at byte 0 with `---`, has `name`/`description`/
   `version`/`type`, description ≤ 1024 chars, body after closing `---`.
3. Confirm the scanner picks it up:
   ```bash
   python3 ~/.hermes/registry/registry-publish.py --dry-run
   # look for:    - <name> v<version> (<category>)
   ```
4. On the coordinator the script would HMP-send the manifest to itself
   (`to: peer70`), so update the files directly instead:
   - `peers/peer70.json`: append `{"name", "version", "category"}` to `skills`,
     bump `updated_at` + `registry_updated_at`
   - `registry.json`: append the name to `peers.peer70.skills`, set
     `skill_count = len(skills)`, bump `updated_at`
5. Other peers see it at the next registry sync. Per operating policy:
   targeted sync to a canary peer first, then the rest; no experimental core
   changes on peer70 itself.

## Pitfalls

- **`hermes skills publish` is NOT the mesh registry.** It targets the public
  hub (fork + PR via GitHub API) or ClawHub (manual submit). Fausto's "skill
  registry" always means `~/.hermes/registry/`. Don't reach for the hub
  workflow when he asks to publish a skill for the community.
- **`providers.nous` in auth.json is a plain dict** — not a list, not a
  top-level `nous` key. Parse defensively (`providers.nous` → fallback `nous`).
- **Registry sync discipline**: heartbeat-only changes (`last_seen`) → "OK",
  no JSON. Structural changes (new skills/plugins, version bumps) → compact
  JSON. Never fabricate heartbeat patches — peers update `last_seen` themselves.

## Worked example (2026-08-16)

`nous-credits` v1.0.0 — created at `~/.hermes/skills/hermes/nous-credits/`
with `scripts/check_credits.py` helper, validated with the dry-run scanner,
then registered in `peers/peer70.json` + `registry.json` (peer70 skill_count
7 → 8).
