# Phase 1B peer128-only active burn-in — 2026-07-27

Scope: controlled `hmp-healthcheck@1.0.0` active canary against **peer128 only** after review-blocker remediation.

## Runtime scope

Environment used for the burn-in script:

```text
CAPABILITY_REUSE_MODE=active
CAPABILITY_REUSE_ACTIVE_CAPABILITIES=hmp-healthcheck
CAPABILITY_REUSE_PERMISSIONS=hmp.network.read
CAPABILITY_REUSE_AVAILABLE_CAPABILITIES=hmp_client_installed
CAPABILITY_REUSE_INTERVENTION_THRESHOLD=0.65
CAPABILITY_REUSE_MINIMUM_MARGIN=0.10
```

Target policy: PEER_MAP label `peer128` only. Raw IPv4 targets remain rejected by the dispatcher.

Report artifact:

```text
/tmp/peer128-burnin-20260727-1785152154-report.json
```

## Code fixes made during this burn-in

The first peer128-only burn-in attempt surfaced two concrete issues:

1. Prompt recall gap: `show peer128 HMP gateway health` scored `0.6377`, just below the active threshold, despite being an exact read-only HMP health intent.
   - Fix: add a narrow deterministic score boost only for `hmp-healthcheck` prompts containing `hmp` plus explicit health/status/check/ping intent and the common operator token `gateway`.
   - Regression: `test_peer128_gateway_health_prompt_intervenes`.

2. Clean failure simulation gap: `_probe_hmp_health()` timeout rows were returned inside a top-level `success=true` dispatcher result, so clean fallback was not issued.
   - Fix: `hmp_healthcheck()` now returns `success=false` with the first row error when any peer row status is not `ok`.
   - Regression: `test_hmp_healthcheck_row_failure_is_clean_dispatch_failure`.

Additional correlation fix made during burn-in:

- `_remember_retrieval()` now indexes the latest retrieval envelope by several compatible scopes, including `session_id`-only and `session_id+turn_id`, so a later hook that omits `episode_id` still records `retrieval_event_id` on `execute_code_started_event` while preserving the original retrieval episode ID.

## Positive peer128 health prompts

All 5 positive peer128 prompts produced active decisions, blocked raw `execute_code`, invoked the deterministic healthcheck, and resolved success.

| Prompt | Score | peer128 result | execute_code full hook | execute_code session-only hook | Final state |
|---|---:|---|---|---|---|
| `check HMP health for peer128` | 0.6916 | `node_id=peer128`, `status=ok` | blocked | blocked | `resolved_success` |
| `ping HMP status for peer128` | 0.6660 | `node_id=peer128`, `status=ok` | blocked | blocked | `resolved_success` |
| `show peer128 HMP gateway health` | 0.6877 | `node_id=peer128`, `status=ok` | blocked | blocked | `resolved_success` |
| `verify peer128 hmp health endpoint` | 0.7281 | `node_id=peer128`, `status=ok` | blocked | blocked | `resolved_success` |
| `healthcheck peer128 via HMP` | 0.6503 | `node_id=peer128`, `status=ok` | blocked | blocked | `resolved_success` |

Every injection contained the exact `intervention_id` required by `invoke_capability()`.

## Negative peer128 prompts

All 5 negative prompts produced no active decision and no false-positive dispatch:

- `send a message to peer128`
- `deploy plugin to peer128`
- `restart HMP on peer128`
- `ssh to peer128 and run uptime`
- `copy registry to peer128`

Observed for each: `decision=false`, `capability_id=null`.

## Failure-path checks

Clean timeout fallback, simulated against peer128 only:

```json
{
  "invoke_success": false,
  "error": "timeout",
  "token_issued": true,
  "fallback_allowed": true,
  "state": "fallback_consumed"
}
```

Unclean read-only failure, simulated malformed peer128 response:

```json
{
  "invoke_success": false,
  "error": "malformed_response",
  "state_after_invoke": "failed_unclean_read_only",
  "structured_continuation_allowed": true,
  "final_state": "unclean_fallback_recorded"
}
```

## Event-chain audit

Burn-in event audit:

```json
{
  "event_count": 56,
  "correlation_errors": [],
  "counts": {
    "retrieval_event": 5,
    "execute_code_started_event": 12,
    "intervention_event": 5,
    "capability_invocation_event": 7,
    "outcome_event": 5,
    "protocol_state_transition": 19,
    "fallback_authorization_event": 2,
    "bypass_event": 1
  }
}
```

Correlation checks verified:

- positive retrieval/start/invocation chains had no missing event types;
- `retrieval_event_id` propagated to started events even for session-only hooks;
- invocation event IDs matched the actual `invoke_capability()` return value;
- no correlation errors were reported.

## Verification after fixes

Final validation command:

```text
python3 -m compileall plugin tests scripts && \
python3 -m unittest discover -s tests -v && \
cp plugin/*.py plugin/plugin.yaml /root/.hermes/plugins/capability-reuse/ && \
python3 scripts/conformance-suite.py && \
for f in __init__.py compatibility.py dispatcher.py event_store.py protocol.py registry.py retriever.py plugin.yaml; do cmp -s "plugin/$f" "/root/.hermes/plugins/capability-reuse/$f" || exit 1; done
```

Final result:

```text
compileall: OK
unittest: 29/29 OK
conformance-suite: 15/15 OK, 0 skipped
runtime sync compare: runtime_sync_ok
```

Conformance report:

```text
/root/.hermes/data/capability-registry/conformance-report.json
```

## Burn-in verdict

Peer128-only Phase 1B active canary passed for the narrow scope:

- target: peer128 only;
- capability: `hmp-healthcheck@1.0.0` only;
- effect: read-only network health probe;
- active false positives in tested negative prompts: 0/5;
- positive active success: 5/5;
- event correlation errors: 0;
- raw `execute_code` bypass without structured/fallback authorization: 0;
- fallback/unclean failure paths: verified by peer128-only simulations.

This does **not** authorize broad active mode. Keep active scope limited to `hmp-healthcheck@1.0.0` and peer128 until more real runtime episodes are collected.
