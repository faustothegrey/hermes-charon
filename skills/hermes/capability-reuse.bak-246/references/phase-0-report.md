# Phase 0 Report — Capability Reuse Control Loop v1.6

**Generated:** 2026-07-25
**Skill version:** 2.1.0
**Spec version:** 1.6
**Author:** peer70 (coordination), Fausto

---

## 1. Executive Summary

Phase 0 tooling and corpus acquisition for the Capability Retrieval & Reuse Control Loop are complete. The v2.1.0 archive passed installation, packaged checksum, regression-test, and local harness checks in external review. However, the reviewer rejected formal empirical Phase 0 closure because C4/C5/C6/C7/C8/C10 were not backed by independent/manual validation or true runtime dispatcher evidence.

Official status after review:

```text
Phase 0 tooling:                  complete
Phase 0 corpus acquisition:       sufficient volume collected
Phase 0 implementation tests:     pass
Phase 0 empirical validation:     incomplete
Formal Phase 0 closure:           not yet
Passive live shadow:              authorized
Formal Phase 1B authorization:    not authorized
```

The previous C1-C10 closure bundle remains useful evidence, but its synthetic/circular methodology must not be represented as formal empirical closure.

| Metric | Value |
|--------|-------|
| Total LOC (skill) | ~18 KB |
| Scripts | 7 |
| Registered capabilities | 3 |
| Conformance tests | 15 local simulated integration tests; pinned CLI/gateway evidence tracked separately |
| Operation patterns tracked | 8 |
| Phase 0 gates met | Tooling/corpus complete; empirical validation pending independent review |

---

## 2. Steps Delivered

### Step 0.0 — Recurrence Audit

**Script:** `scripts/recurrence-audit.py` (standalone Python)

Analyzes historical Hermes session data for `execute_code` usage patterns. Discovers available SQLite DBs and JSONL logs, extracts code snippets, classifies them into 8 known operation patterns, and produces a frequency report.

**Output:** `~/.hermes/cache/recurrence-audit-report.json`

**Result on peer70:** 0 `execute_code` calls found in local state DB, 3 found in HMP gateway messages DB. Confirms the need for forward collection — session data does not persist tool call history in a directly queryable format.

**Patterns tracked:** hmp_healthcheck, hmp_send, json_parse, ssh_command, file_read, hmp_broadcast, netboard_display, cron_management

### Step 0.1 — Registry Schema + Storage

**Script:** `scripts/init-registry.py` (standalone Python)

Creates the capability registry directory structure and writes the JSON Schema for capability entries (retrieval metadata + invocation contracts).

**Structure:**
```
~/.hermes/data/capability-registry/
├── schema.json       ← Full JSON Schema (draft-07)
├── registry.json     ← Index of all registered capabilities
└── contracts/        ← Per-capability invocation contracts
```

**Schema coverage:**
- Retrieval metadata: capability_id, version, description, examples, supports/excludes text, feature_ids, assumptions, contract_owner
- Invocation contract: executor (kind + entrypoint), input/output/error schemas, effect_class, idempotency, permissions, trust_state, fallback_policy

### Step 0.1b — Hook Conformance Suite

**Script:** `scripts/conformance-suite.py` (standalone Python, §3.3)

Implements 15 conformance tests that verify the Hermes runtime supports the plugin-hook contracts required for Phase 1. Tests cover:
1-3: Plugin discovery, identity, tool visibility (static, importable)
4-5: `pre_llm_call` / `pre_tool_call` firing (live Hermes required)
6: Block return contract (static)
7-8: Post-call observation, identifier stability (live required)
9: Atomic claiming prevention (static, importable)
10: Fail-open behavior (static)
11-15: Multi-surface, kwargs, injection, block origins, approval pipeline (mixed)

**Local integration conformance:** 15/15 tests pass in the isolated plugin harness.
**Pinned Hermes CLI/gateway conformance:** evidence must be packaged as raw artifacts before formal gate closure; simulated hook calls are not independent runtime proof.

### Step 0.1c — Plugin Identity + Surface Inventory

**Deliverable:** Plugin skeleton at `plugin/`:
- `plugin.yaml` — Manifest with hooks (`pre_llm_call`, `pre_tool_call`, `post_tool_call`) and tools (`invoke_capability`)
- `__init__.py` — Appendix A reference skeleton with `register()`, hook handlers, and tool handler

Execution surfaces inventoried per §3.6:
- `execute_code` — primary enforcement target
- `terminal` — alternate execution (monitored, not blocked)
- `delegate_task` — subagent coverage marked `unknown` until child tool events are directly observable

### Step 0.2 — Register First Capabilities

**Script:** `scripts/register-capability.py`

Three capabilities registered in the registry:

| Capability | Version | Effect Class | Trust State | Entrypoint |
|------------|:-------:|:------------:|:-----------:|------------|
| hmp-healthcheck | 1.0.0 | read_only | observed | `hermes_harnesses.hmp:healthcheck` |
| hmp-send | 1.0.0 | mutating | observed / not active | `hmp_dual_plane.send_to_peer` |
| peer-heartbeat | 1.0.0 | read_only | observed | `hermes_harnesses.hmp:heartbeat` |

Each includes full retrieval metadata (examples, supported/excluded features, assumptions) and invocation contract (typed schemas, clean failure codes, permissions, fallback policy).

### Step 0.3 — Forward Instrumentation

**Module:** `instrumentation/execute_code_wrapper/__init__.py`

Non-blocking, append-only JSONL wrapper for `execute_code` calls. Captures:
- Timestamp, session/episode context
- Code fingerprint (imports, tool calls, URLs, patterns)
- Outcome, duration, error preview

**Kill switch:** `HERMES_OBSERVER_DISABLE=1`

**Output:** `~/.hermes/data/reuse-observer/events.jsonl`

### Step 0.4 — Post-execution Fingerprint

**Script:** `scripts/code-fingerprint.py`

Three independent fingerprints extracted from generated code:

| Fingerprint | Technique | Extracts |
|-------------|-----------|----------|
| Syntax | AST normalization | Imports, calls, control flow depth, loops, try/except, URL literals |
| Capability | Pattern matching | Libraries, Hermes tools, protocols (hmp, http, ssh), operation classes |
| Effect | Static analysis | Filesystem r/w, network r/w, process spawn, remote mutation, effect class |

**Input:** Code string (file or stdin)
**Output:** JSON fingerprint + human-readable report + saved to `data/reuse-observer/fingerprints/`

---

## 3. Phase 0 Gates Status

| Gate | Status | Notes |
|------|:------:|-------|
| Registry with ≥3 versioned capabilities | ✅ | hmp-healthcheck 1.0.0, hmp-send 1.0.0, peer-heartbeat 1.0.0 |
| Forward instrumentation producing events | ✅ | JSONL at `data/reuse-observer/events.jsonl` |
| ≥3 recurring clusters (≥5 occurrences each) | ⚠️ | Provisional pass; reviewer requires manual cluster validation excluding debugging/retry loops and showing recurrence across sessions/days |
| Hook conformance passed on current runtime | ⚠️ | Local harness 15/15 accepted as implementation evidence; reviewer requires real CLI/gateway dispatcher evidence for formal C8 |
| Execution surfaces inventoried (§3.6) | ✅ | Primary: execute_code; unsupported/unknown surfaces must be stated rather than simulated as pass |
| Dataset C labeled from hook-visible input only | ❌ | Reviewer rejected 72/120 synthetic labels and synthetic/template-overlap holdout; needs ≥100 real/independently authored manually labeled requests |

---

## 4. Skill Structure

```
~/.hermes/skills/hermes/capability-reuse/ (v2.1.0)
├── SKILL.md
├── registry/schema.json
├── scripts/
│   ├── recurrence-audit.py         (0.0)
│   ├── init-registry.py            (0.1)
│   ├── register-capability.py      (0.2)
│   ├── conformance-suite.py        (0.1b)
│   └── code-fingerprint.py         (0.4)
├── instrumentation/
│   └── execute_code_wrapper/__init__.py  (0.3)
├── plugin/
│   ├── plugin.yaml                 (Phase 1 skeleton)
│   └── __init__.py                 (Phase 1 skeleton, Appendix A)
└── references/
```

---

## 5. Overhead Tracking

| Metric | Phase 0 |
|--------|:-------:|
| Additional latency per request | +2 ms (forward instrumentation only) |
| Total LOC (scripts + schema + skeleton) | ~3,500 |
| Human hours invested | ~8h (development + spec review) |
| Behavioral changes to agent | **None** |
| Kill switch present | ✅ |
| Revert mechanism | Remove skill directory |

---

## 6. Recommendations for Phase 1

1. **Run conformance suite** on the deployed Hermes runtime before any Phase 1A code is written — this establishes the actual hook contracts and prevents surprises.
2. **Phase 1 modules order:** protocol.py (state machine) → event_store.py → registry.py → retriever.py → compatibility.py. This order builds from the atomic decision core outward.
3. **Start with `protocol.py`** — the state machine (§3.7) is the most novel and critical component. Without atomic claiming, concurrent tool calls will race.
4. **Label dataset C** as soon as forward collection produces enough samples — retrieval precision depends on it.
