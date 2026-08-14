# Plugin runtime vs skill-source divergence (2026-08-14)

## The bug

`~/.hermes/skills/hermes/capability-reuse/` (skill source) and
`~/.hermes/plugins/capability-reuse/` (runtime plugin loaded by the
gateway) are **separate installs**. Deploying the skill to peers via
`scp -r ...skills/hermes/capability-reuse ...` does NOT touch the runtime
plugin. After the 2.4.17 release, the skill on all peers said 2.4.17 but
the runtime plugin stayed at 2.4.6 (peer70/138) or 2.4.16 (peer58/106).

## Symptom

`~/.hermes/data/reuse-observer/events.jsonl` keeps gaining events with
`data.plugin_version: 2.4.6` **after** you cleaned pre-2.4.16 events.
You clean, and 10 minutes later stale-version events are back. The
gateway is still running the old plugin.

## Detection (run on every peer)

```bash
# plugin runtime vs skill source
grep '^version' ~/.hermes/plugins/capability-reuse/plugin.yaml
grep '^version' ~/.hermes/skills/hermes/capability-reuse/SKILL.md
grep 'VERSION = ' ~/.hermes/plugins/capability-reuse/protocol.py
# live events still carrying old version?
python3 -c "
import json
from collections import Counter
pv = Counter()
with open('/home/fausto/.hermes/data/reuse-observer/events.jsonl') as f:
    for line in f:
        try: pv[(json.loads(line).get('data') or {}).get('plugin_version')] += 1
        except: pass
print(dict(pv))"
```

Any plugin_version ≠ SKILL.md version = divergence.

## Fix

```bash
mv ~/.hermes/plugins/capability-reuse ~/.hermes/plugins/capability-reuse.bak-mismatch
cp -a ~/.hermes/skills/hermes/capability-reuse/plugin ~/.hermes/plugins/capability-reuse
find ~/.hermes/plugins/capability-reuse -name '__pycache__' -type d -exec rm -rf {} \;
find ~/.hermes/plugins/capability-reuse -name '*.pyc' -delete
# THEN restart the gateway so the new plugin is loaded.
```

Do this on peer70 AND every remote peer (SSH loop). The gateway restart
is mandatory — pycache cleaning alone is not enough; the running process
must reload.

## Event-store version cleanup (when asked to drop pre-N events)

1. `cp events.jsonl events.jsonl.bak-pre<N>` (keep the backup).
2. Rewrite `events.jsonl` keeping only `data.plugin_version == "<N>"`.
3. Regenerate derived files:
   `python3 scripts/generate-review-queue-v245.py` (creates
   candidates/excluded/review queues from the cleaned store).
4. Delete stale derived files that still reference old cohorts
   (`queue-latest.*`, `queue-v244-*`, old `human-labels.jsonl`).
5. **Verify the source of new events is the fixed plugin** (see
   Detection) — otherwise the store re-pollutes immediately.

## Why it bites

Release discipline up to 2.4.17 updated the skill everywhere but the
runtime plugin copy was versioned separately. The "Distribution" section
of SKILL.md mentions copying `plugin/` into `~/.hermes/plugins/`, but the
version-alignment check across peers was missing. Rule: **a skill release
is not deployed until BOTH the skill dir AND the runtime plugin dir agree
on version on EVERY peer, and the gateway restarted.**
