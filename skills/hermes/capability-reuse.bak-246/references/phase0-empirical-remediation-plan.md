# Phase 0 empirical validation remediation plan

Goal: convert v2.1.0 from tooling/corpus-complete to formally reviewable empirical Phase 0 closure.

## Target official status during this work

```text
PHASE_0_TOOLING_AND_CORPUS_COLLECTION_COMPLETE
EMPIRICAL_LABELING_AND_INDEPENDENT_VALIDATION_PENDING
```

## Workstreams

### 1. Manual Dataset B: post-execution equivalence

Deliverable: `evidence/phase0-review/dataset-b-human-labels.jsonl`

Minimum size: 100–150 pairs.

Required fields per row:

```json
{
  "pair_id": "B0001",
  "left_event_id": "...",
  "right_event_id": "...",
  "left_summary": "redacted human-readable operation summary",
  "right_summary": "redacted human-readable operation summary",
  "label": "same_reusable_operation | related_but_different | unrelated | incompatible | uncertain",
  "effect_class_left": "read_only | mutating | unknown",
  "effect_class_right": "read_only | mutating | unknown",
  "rationale": "short human rationale",
  "labeler": "human or reviewer id",
  "reviewed_at": "ISO timestamp"
}
```

Sampling rules:
- blind labels: labelers must not see regex operation buckets or predicted labels;
- include hard cases and non-healthcheck operations;
- cap any one recurring family so `json_aggregation` cannot dominate;
- include same, related-but-different, unrelated, incompatible, and uncertain cases.

### 2. Manual Dataset C: pre-execution request/capability matching

Deliverable: `evidence/phase0-review/dataset-c-human-labels.jsonl`

Minimum size: 100 real or independently authored hook-visible requests.

Rules:
- no `variant N` suffixes;
- no template overlap between tuning and holdout;
- synthetic examples may be kept only in a dev set, not holdout;
- include meaningful hard negatives: mutating HMP send/deploy/restart/ssh/copy requests, ambiguous health/status prompts, unrelated tasks;
- labels must be manual or independently reviewed.

Required fields per row:

```json
{
  "request_id": "C0001",
  "hook_visible_text": "redacted text",
  "expected_capability_id": "hmp-healthcheck | none | ...",
  "expected_version": "1.0.0 | null",
  "expected_effect_class": "read_only | mutating | unknown | null",
  "label": "eligible | no_match | incompatible | uncertain",
  "rationale": "short human rationale",
  "split": "tuning | holdout",
  "labeler": "human or reviewer id",
  "reviewed_at": "ISO timestamp"
}
```

### 3. Actual retriever evaluation

Deliverable: `scripts/evaluate-retriever-human-labels.py` plus JSON/MD reports.

The evaluator must call the real retriever pipeline and record:
- candidate list and scores;
- top-1 score;
- top-2 score;
- margin;
- hard-filter decisions;
- compatibility result;
- trust/effect/allowlist eligibility;
- final intervention decision.

It must not predict with a second regex classifier.

### 4. Threshold and margin sweep

Deliverable: `evidence/phase0-review/threshold-sweep.json` and `.md`.

Sweep over candidate thresholds and margins, e.g.:
- threshold: 0.55, 0.60, 0.65, 0.70, 0.75, 0.80;
- margin: 0.00, 0.03, 0.05, 0.10.

Report per point:
- tuning precision/recall;
- holdout precision/recall;
- intervention count;
- false read-only↔mutating matches;
- false positives by effect class;
- lower confidence bound where feasible.

### 5. Runtime conformance, not simulated callback tests

Deliverable: raw pinned runtime artifacts under `evidence/runtime-conformance/`.

Required surfaces:
- real Hermes CLI turn;
- real gateway request;
- real plugin dispatch path for pre_llm/pre_tool/post_tool;
- real co-resident plugin block or explicitly marked unsupported/not installed;
- delegation either tested genuinely or documented as unsupported/unknown, not passed by shape simulation.

### 6. Manual recurrence validation

Deliverable: `evidence/phase0-review/manual-cluster-validation.jsonl`.

For each proposed recurring cluster, show:
- examples across distinct sessions/days;
- exclusion of debugging/retry loops;
- human decision whether it represents recurring user demand;
- capability reuse value estimate.

## Exit criteria for next review

- C4, C5, C6, C7, C8, C10 are backed by independent evidence.
- C2/C3 calculations corrected and manually validated.
- All generated reports explicitly separate dev/tuning/holdout.
- Formal status remains pending until reviewer accepts the methodology.
