# Memory Provider Comparison — Constrained Hardware / Zero Budget

Compiled from official Hermes Agent docs (memory-providers page) and hands-on testing on Raspberry Pi 4 (ARMv8, 4GB RAM).

## Test environment

- **Device:** Raspberry Pi 4B, ARM Cortex-A72, 4GB RAM
- **OS:** Linux 5.15.61-v8+ (Debian-based)
- **Hermes:** latest (v0.x), Python 3.9
- **Constraint:** €0 budget, no cloud dependencies, no API key subscriptions

## At a glance

| Provider | Cost | ARM/Pi | Dependencies | API key | Daemon | RAM impact | Setup time | Best for |
|---|---|---|---|---|---|---|---|---|
| **Holographic** | **€0** | ✅ | SQLite (stdlib) | ❌ | ❌ | None (~2MB) | 30s | **Local-first, minimal footprint** |
| OpenViking | €0 | ✅ | pip + server | ✅ local | ✅ | Low (~50MB) | 3-5m | Token-conscious deployments |
| Hindsight | €0 local | ⚠️ | pip + PostgreSQL | ❌ local | ✅ | High (~300MB) | 10-15m | Maximum retrieval accuracy |
| Honcho | €0 self-hosted | ⚠️ | pip + server | ✅ | ✅ | Medium | 10m+ | Dialectic user modeling |
| Mem0 | Freemium | ✅ | pip + API key | ✅ | ❌ | Low | 30s cloud | Fastest cloud setup |
| ByteRover | Freemium | ✅ | pip + API key | ✅ | ❌ | Low | 3-5m | Human-readable knowledge trees |
| RetainDB | 💰 Paid | ❌ | Cloud | ✅ | ❌ | N/A | N/A | Hybrid search (vector + BM25) |
| Supermemory | Freemium | ? | API key | ✅ | ❌ | N/A | N/A | Automated background capture |

## Detailed notes

### Holographic (recommended for this cluster)

- **Setup command:** `hermes memory setup holographic`
- **Storage:** `~/.hermes/memory_store.db` (SQLite, ~100KB per 1000 facts)
- **Tools:** `fact_store` (9 actions) + `fact_feedback`
- **Unique features:**
  - HRR (Holographic Reduced Representations) — sub-millisecond recall
  - Trust scoring — facts gain/lose trust based on confirmation/contradiction
  - Zero deps — uses only Python stdlib SQLite
- **Limitations:**
  - No LLM-based extraction (silent FTS5-only fallback when NumPy absent)
  - No knowledge graph
  - Single-machine (no multi-device sync)
- **Setup verified:** `hermes memory setup holographic` → `Activation saved to config.yaml`

### OpenViking

- **Setup:** `pip install openviking` + `openviking-server` + `hermes memory setup`
- **Key advantage:** Tiered L0/L1/L2 context loading (80-90% token savings)
- **Tools:** 5 tools (highest count)
- **License:** AGPL-3.0 (free, open-source)
- **Pi concern:** Requires running a server process. Low memory but persistent.

### Hindsight

- **Setup:** `hermes memory setup` → select Hindsight. Optional: set `HINDSIGHT_API_KEY` in `.env` for cloud sync. Local mode: leave blank.
- **Benchmark:** 94.6% on LongMemEval (highest of all providers)
- **Architecture:** Local PostgreSQL daemon + structured knowledge graphs + reflect synthesis
- **Pi concern:** PostgreSQL alone consumes 200-400MB RAM. Not recommended for 4GB Pi.
- **When to use on Pi:** Only if you have the RAM headroom and need maximum accuracy.

### Honcho

- **Setup:** `pip install honcho-ai` + `hermes memory setup` + API key or self-hosted
- **Unique approach:** Dialectic user modeling (builds a model of *how* you think, not just *what* you know)
- **License:** AGPL v3 (self-hosted requires source release)
- **Pi concern:** Self-hosted requires managing a server. Cloud version costs ~$20/mo.
- **Best for:** Personal assistants needing deepening user model over time.

## Decision flow

```
User has budget?
├── NO
│   ├── Has PostgreSQL running already?
│   │   ├── YES → Hindsight (best accuracy, zero extra cost)
│   │   └── NO
│   │       ├── Can run a Python server 24/7?
│   │       │   ├── YES → OpenViking (token savings)
│   │       │   └── NO → Holographic ← RECOMMENDED for Pi/cluster
│   └── [End]
└── YES
    ├── Needs maximum accuracy?
    │   ├── YES → Hindsight Cloud (sync across machines)
    │   └── NO
    │       ├── Fastest setup → Mem0 (30s)
    │       └── Deepest user modeling → Honcho
    └── [End]
```

## Setup verification

After activating any provider, run:

```bash
hermes memory status
```

Expected output for Holographic:
```
Memory status
────────────────────────────────────────
  Built-in:  always active
  Provider:  holographic

  Plugin:    installed ✓
  Status:    available ✓
```

## Uninstalling

```bash
hermes memory off               # deactivate without removing plugin
hermes config set memory.provider ""  # manual deactivation
```

Holographic has no pip package to uninstall — it's built into Hermes. The SQLite DB (`~/.hermes/memory_store.db`) is safe to delete if you want a clean slate; it will be recreated on next session.
