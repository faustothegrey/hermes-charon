# Topology Study v1.1 — Report

**Project:** capability-reuse (spec v1.6) — Phase 1 gate
**Preregistration:** `topology-study-prereg-v1.1.md` (FROZEN, authoritative)
**Executor:** Hermes (peer70) · **Date:** 2026-08-16
**Status:** **UNDERPOWERED** — §7 locked minimums not met. §§4–8 not executed.

---

## 1. Prerequisite finding (pre-data, recorded per §2)

**recurrence-audit.py v1.2 does NOT emit confidence tiers `{low, medium, high}`.**
The prereg §2 states "Each cluster carries its confidence tier {low, medium,
high} from recurrence-audit.py" — this is **not implemented** in the current
script. It emits only:
- OPERATION_PATTERNS classification (8 patterns + `unknown/other`)
- a binary "high-value (>=3 occurrences)" flag (≥3, not a 3-level tier)

Consequences, recorded without redesign (prereg §9 prohibitions respected):
- Tier stratification (mandatory second axis, §5) is **not executable** as
  preregistered.
- The §7 high-confidence minimum (≥100) is therefore structurally unreachable
  until recurrence-audit emits tiers. This is a prerequisite gap, not an
  experimental outcome.

## 2. Data sources (all read-only, dedup by event_id)

| Source | Path | Events |
|---|---|---|
| Pre-2.4.16 log | `~/.hermes/data/reuse-observer/events.jsonl.bak-pre2416` | 2 801 |
| Current v2.5.0 live | `~/.hermes/data/reuse-observer/events.jsonl` | 91 |
| Collector raw peer70 | `capreuse-central/raw/peer70/events.jsonl` (backup tar) | 102 |
| Collector raw peer106 | `capreuse-central/raw/peer106/events.jsonl` (backup tar) | 35 |
| peer138 export | `~/.hermes/data/capreuse-backup-20260813-1735/peer138/events.jsonl` | 317 (no `event_type` field — excluded from started/completed counts) |
| **Total (dedup)** | | **3 352** |

## 3. §7 Power / inventory counts

| Metric | Value | §7 locked minimum | Met? |
|---|---|---|---|
| Total episodes (sessions with ≥1 execute_code) | **16** | — | — |
| Excluded episodes (< 2 clustered invocations) | 8 | — | — |
| Usable transitions (≥2 invocations) | **63** | — | — |
| Distinct clusters | **4** | — | — |
| Embedding-failure-slice transitions (pooled) | ≤ 63 (subset; needs M1) | **≥ 300** | **NO** |
| High-confidence-tier transitions | **0** (tiers not emitted) | **≥ 100** | **NO** |

### Cluster inventory (occurrences)

| Cluster | Count |
|---|---|
| unknown/other | 71 |
| hmp_healthcheck | 6 |
| json_parse | 1 |
| cron_management | 1 |

### Cutoffs (episode min-timestamp quantiles, §3)

| Cutoff | Timestamp |
|---|---|
| T1 (50%) | 2026-08-13T16:15:25Z |
| T2 (65%) | 2026-08-13T16:28:27Z |
| T3 (80%) | 2026-08-13T19:21:45Z |

Transitions per cutoff (session min-ts < cutoff): T1=25, T2=26, T3=63.

## 4. Verdict

**UNDERPOWERED.**

Both locked §7 minimums fail:
1. **≤ 63 usable transitions** vs ≥ 300 required for the embedding-failure slice
   (the slice is a strict subset of these 63, so the true count is lower).
2. **0 high-confidence-tier transitions** — tiers are not emitted by
   recurrence-audit.py v1.2 (prerequisite gap), so the ≥ 100 high-conf minimum
   is structurally unreachable.

Per §7: "Do not proceed to §8." §§4–6 (models, endpoints, ablations) were NOT
executed. No fitting, no bootstrap, no graph.

## 5. Estimated additional data required

At the observed historical rate (~63 usable transitions across ~13 days of
logging, ≈ 4.8/week), reaching ≥ 300 failure-slice transitions requires
**≥ 600–1 200 total transitions** (failure-slice is a subset; fraction unknown
without M1) — roughly **2.5–5 years** of natural passive harvest.

**Acceleration paths (for the operator to decide, not part of this study):**
- `calibration_probe` traffic (already in the event vocabulary) can generate
  synthetic-but-labeled transitions at controlled volume.
- Fixing the tier emission in recurrence-audit.py is a **prerequisite**, not an
  experiment change: without tiers the §5 stratification axis and the §7
  high-conf minimum cannot be satisfied under any corpus size.
- Multi-peer aggregation (peer141/138/58 already publish manifests) would
  widen the corpus; current log is peer70-dominated.

## 6. What this verdict does and does not license (≤10 lines)

This verdict licenses: nothing about skill quality, topology value, or policy.
It only establishes that the current corpus (16 episodes, 63 transitions,
4 clusters, no tiers) cannot support the preregistered test. It does not
license: dropping the graph, adopting the graph, changing the retriever, or
any registry/skill write. It also does not license proceeding to §8 with the
current data. The preregistered design remains the only admissible test once
the corpus and the tier prerequisite are satisfied.

---

*Frozen artifacts: `analysis/inventory.py` (this inventory, read-only),
`analysis/manifest.json` (sources, cutoffs, cluster map, counts).*
