# Topology Study v1.1 — outcome & prerequisite gap (2026-08-16)

## Verdict

**UNDERPOWERED** (frozen prereg, §7 minimums not met). Study stopped at §7;
no models fitted, no bootstrap, no graph. Prereg is authoritative — do not
redesign, do not tune, do not proceed to §8 with current data.

## Key counts (corpus as of 16/08)

- 3,352 dedup events across 5 sources; only **79 execute_code_started** in
  16 sessions; **63 usable transitions**; **4 clusters** (71/79 = unknown/other)
- §7 minimums: ≥300 failure-slice transitions pooled, ≥100 high-confidence
  tier → BOTH fail (63 ≤ 300; tiers don't exist)
- Natural harvest rate ≈ 4.8 transitions/week → 2.5–5 years to reach 300

## ⚠️ Prerequisite gap (critical for any future Phase-1 work)

**recurrence-audit.py v1.2 does NOT emit confidence tiers
{low, medium, high}.** The prereg §2 assumes clusters carry a tier from this
script. Reality: only OPERATION_PATTERNS classification (8 patterns +
`unknown/other`) plus a binary "high-value ≥3" flag.

Consequences:
- §5 tier stratification (mandatory axis) is NOT executable as preregistered
- §7 high-confidence minimum (≥100) is structurally unreachable
- Fixing tier emission is a **prerequisite**, not an experiment change —
  do it WITHOUT touching the frozen study or the retriever

## Sparsity attribution (combined)

| Factor | Evidence |
|---|---|
| Few executions | 79 started / ~15 days; but 38 (48%) in ONE session |
| Schema observability | 911 alternate_execution (terminal), 309 retrieval, 1,974 observation events carry capability-bearing payloads but are excluded by §2 construction |
| Audit resolution | 90% (71/79) land in unknown/other — 8 patterns insufficient |
| Session fragmentation | 16 sessions {1:8, 2:3, 4:2, 7:1, 12:1, 38:1}; session_id often empty or = peer name |

Key insight: transition volume does NOT change with cluster resolution (it's
determined by invocations/session, not labels). Resolution improves
specificity (failure-slice, stratification), not volume.

## Artifacts (in skill, under analysis/)

- `analysis/topology-study-report.md` — full §7 counts, cutoffs, verdict
- `analysis/inventory.py` — read-only inventory script (reproducible)
- `analysis/corpus-audit.py` — event-type/clusterability/attribution audit
- `analysis/manifest.json` — frozen artifacts, sources, cutoffs
- Vault copy of prereg: `~/Documents/Obsidian Vault/Progetti/Hermes/topology-study-prereg-v1.1.md`

## Accelerators (operator decision, not study changes)

- calibration_probe traffic (already in event vocabulary) for controlled volume
- multi-peer aggregation (peer141/138/58 publish manifests); current log is
  peer70-dominated
- tier emission fix in recurrence-audit (prerequisite, see above)
