# Review blocker remediation — 2026-07-27

Use this reference when hardening capability-reuse active/shadow paths after a review finds auditability or enforcement gaps.

## Blockers remediated

- Correlation envelope:
  - Retrieval decisions/events carry `retrieval_event_id`, `session_id`, `episode_id`, and `turn_id`.
  - `pre_tool_call` emits `execute_code_started_event` with `session_id`, `episode_id`, `turn_id`, `task_id`, `tool_call_id`, `code_hash`, and `retrieval_event_id`.
  - `post_tool_call` emits `execute_code_completed_event` with the same envelope.

- Active intervention enforcement:
  - Open-intervention lookup uses the hook-visible envelope and does not require `session_id == episode_id`.
  - If a hook only supplies `session_id`, lookup must still block interventions whose stored `session_id` or stored `episode_id` matches that value. This preserves compatibility with older hook shapes while preventing fail-open active mode.
  - Latest-open lookup should take the store lock before reading intervention state.

- Prompt/invocation contract:
  - Active injection must include the exact `intervention_id` required by `invoke_capability`.
  - Injection should document the structured bypass contract and allowed v1.6 reason codes.

- Intervention/invocation identity:
  - Generate intervention IDs with UUIDs (`int_<uuidhex>`), not timestamp-second IDs.
  - `invoke_capability` should create one invocation ID and pass it through `capability_invocation_event`; returned `invocation_id` and event `invocation_id` must match.

- Bypass/fallback safety:
  - Bypass validation requires matching intervention/capability/version and approved reason codes: `unsupported_feature`, `schema_mismatch`, `taxonomy_gap`, `harness_failure_unclean`.
  - `harness_failure_unclean` requires matching prior invocation and failure code.
  - Clean fallback tokens must be bound to the currently blocking intervention. A token for an old or unrelated intervention must be rejected and must not be consumed.
  - Read-only unclean dispatcher failures transition to `failed_unclean_read_only` and allow exactly one structured continuation path.

- Active availability/scope:
  - Active retrieval must not invent permissions or runtime capabilities. They must come from hook context or explicit trusted runtime config (`CAPABILITY_REUSE_PERMISSIONS`, `CAPABILITY_REUSE_AVAILABLE_CAPABILITIES`).
  - Alternate execution logging should be limited to known arbitrary-execution surfaces, not every non-`execute_code` tool.
  - First-canary `hmp-healthcheck` dispatch should be PEER_MAP-only; reject raw IPv4 targets.

## Verification pattern

Run all three before claiming remediation complete:

```text
python3 -m compileall plugin tests scripts
python3 -m unittest discover -s tests -v
python3 scripts/conformance-suite.py
```

Expected after this remediation:

```text
unittest: 27/27 OK
conformance: 15/15 OK, 0 skipped
```

Also run smoke checks for:

- active retrieval returns UUID intervention + retrieval event ID;
- injection contains exact intervention ID;
- raw `execute_code` is blocked even when hook omits `episode_id`;
- live `invoke_capability(hmp-healthcheck@1.0.0, peer128)` succeeds;
- stale fallback token from an older intervention does not authorize a newer open intervention.

## Review lesson

After implementing reviewer findings, run a second focused code review or adversarial check before finalizing. In this session the second review caught two security blockers that normal tests initially missed:

1. active blocking failed open when execute-code hooks supplied only `session_id` and omitted `episode_id`;
2. fallback tokens were not bound to the current blocking intervention, allowing stale-token cross-intervention bypass.

Encode those as explicit regression tests, not just reasoning notes.
