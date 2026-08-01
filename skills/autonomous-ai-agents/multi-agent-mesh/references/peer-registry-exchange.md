# Peer Registry & Exchange Digest

Structured metadata messages that peers can publish to the orchestrator via HMP.

## REGISTRY_PUBLISH

A peer publishes its capabilities (skills, plugins) as a structured JSON message.

### Format

```json
{
  "peer": "peer106",
  "host": "192.168.178.106",
  "updated_at": "2026-07-16T11:46:10Z",
  "skills": [
    {"name": "skill-name", "version": "1.0.0", "category": "category-name"}
  ],
  "plugins": [
    {"name": "hmp", "version": "1.0.0", "enabled": true}
  ]
}
```

### Storage

Orchestrator saves to `~/.hermes/peer-network/<peer-name>-registry.json`:

```json
{
  "peer": "peer106",
  "host": "192.168.178.106",
  "updated_at": "2026-07-16T11:46:10Z",
  "skills_count": 0,
  "skills_categories": {
    "category-name": ["skill1", "skill2"]
  },
  "plugins": [{"name": "hmp", "version": "1.0.0", "enabled": true}]
}
```

### When to publish

- On initial peer onboarding
- When skills/plugins change (add/remove/update)
- On request from orchestrator

## EXCHANGE_DIGEST

A peer reports its daily session activity and state.

### Format

```
EXCHANGE_DIGEST <peer-name> <date>
---
peer: <peer-name>
date: <date>
plugin_version: <semver>
type: daily
---

## Sessioni di oggi

  - <HH:MM> | <session-title-or-id>
  - ...

## Skill modificate

  (nessuna skill modificata)
  - or: <skill-name> — <change-description>

## Plugin HMP

Versione plugin: <version>
```

### Storage

Orchestrator saves structured JSON to `~/.hermes/peer-network/exchange-digests/<peer-name>-<date>.json`:

```json
{
  "peer": "peer106",
  "date": "2026-07-17",
  "plugin_version": "0.1.2",
  "type": "daily",
  "sessions": [
    {"time": "18:11", "title": "session-title-or-id"}
  ],
  "skills_modified": [],
  "plugin_hmp_version": "0.1.2"
}
```

### When to send

- At end of day (daily digest)
- On orchestrator request
- After significant activity changes

## Implementation notes

- Both formats are sent as plain text via HMP DM — not wrapped in `payload` objects
- The orchestrator acknowledges receipt and persists to `~/.hermes/peer-network/`
- Digests under `exchange-digests/` subdirectory for clean separation from status files
