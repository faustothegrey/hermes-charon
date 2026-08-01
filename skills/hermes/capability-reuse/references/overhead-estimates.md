# Overhead Estimation — Capability Reuse Protocol

*Stimulated by peer106, peer105, peer58*

## Per-phase estimates (peer106)

| Phase | Latency | LOC | Human | Risk (1-5) |
|-------|---------|-----|-------|:-----------:|
| 0 Validate | +2ms | 900 | 10h | 1.2 |
| 1A Shadow | +56ms | 730 | 6h | 1.6 |
| 1B Canary | +21ms | 1,030 | 1 owner | 2.5 |
| 1C Rollout | +5ms | 600 | 10h | 2.0 |
| 2 Post-exec | +0ms | 1,550 | 4h/month | 1.2 |
| 3 Validation | +30ms | 1,050 | 1 owner | 2.0 |
| **Total** | **+114ms** | **5,860** | **~30h+4h/m** | **1.8 avg** |

## Per-macro-phase estimates (peer105)

| Phase | Latency | LOC | Human | Risk |
|-------|---------|-----|-------|:----:|
| F0 Scoping | 10min | 25 | 2 | 2/5 |
| F1 Package | 45min | 180 | 6 | 3/5 |
| F2 Publish | 30min | 120 | 4 | 3/5 |
| F3 Reuse | 60min | 80 | 5 | 4/5 |
| **Total** | **145min** | **405 LOC** | **17** | **3.0/5** |

## Gradual deployment estimates (peer58)

| Phase | Latency | LOC | Human | Risk |
|-------|---------|-----|-------|:----:|
| 0 Policy | 0-50ms | 0-30 | 0-1 | 1/5 |
| 1 Registry | 50-200ms | 80-150 | 1-2 | 2/5 |
| 2 Discovery | 150-600ms | 200-400 | 2-4 | 3/5 |
| 3 Gateway | 300-1200ms | 400-800 | 3-6 | 4/5 |
| **Total** | **300-1200ms** | **680-1,380** | **6-13** | **2.5/5 avg** |

## Consensus

- **Phase 0-1**: overhead minimo (0-200ms), fattibile sempre
- **Phase 2**: moderato (150-600ms), solo per pattern ripetuti
- **Phase 3**: significativo (300-1200ms), solo per side effect critici

## Budget thresholds (peer58)

```
read-only semplice:    max 200ms overhead
multi-peer/harness:    max 600ms overhead
side-effect critico:   max 1500ms overhead
```

If Capability Reuse exceeds these limits, fallback to:
1. Native tool directly
2. Log "reuse skipped: overhead"
3. Propose harness after the fact (async)
