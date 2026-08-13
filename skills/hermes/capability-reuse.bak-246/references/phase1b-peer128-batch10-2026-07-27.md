# Phase 1B peer128-only batch-10 burn-in — 2026-07-27

Scope: execute all safe peer128-only capability-reuse checks available locally, keeping active dispatch limited to `hmp-healthcheck@1.0.0` and target `peer128`.

## Preflight validation

Command executed from `/root/.hermes/skills/hermes/capability-reuse`:

```text
python3 -m compileall plugin tests scripts
python3 -m unittest discover -s tests -v
/bin/cp -f plugin/*.py plugin/plugin.yaml /root/.hermes/plugins/capability-reuse/
python3 scripts/conformance-suite.py
cmp source/runtime plugin files
```

Results:

```text
compileall: OK
unittest: 29/29 OK
conformance-suite: 15/15 OK, 0 skipped
runtime sync: runtime_sync_ok
```

Conformance report:

```text
/root/.hermes/data/capability-registry/conformance-report.json
```

## Batch execution

Reusable harness:

```text
scripts/active-canary-burnin.py peer128
```

Batch command shape:

```text
for i in $(seq 1 10); do
  python3 scripts/active-canary-burnin.py peer128 | tee /tmp/capreuse-peer128-batch-1785154923/run-$i.out
done
```

Aggregate report:

```text
/tmp/capreuse-peer128-batch-1785154923/aggregate.json
```

Individual reports:

```text
/tmp/peer128-burnin-1785154943-report.json
/tmp/peer128-burnin-1785154944-report.json
/tmp/peer128-burnin-1785154945-report.json
/tmp/peer128-burnin-1785154946-report.json
/tmp/peer128-burnin-1785154948-report.json
/tmp/peer128-burnin-1785154949-report.json
/tmp/peer128-burnin-1785154950-report.json
/tmp/peer128-burnin-1785154951-report.json
/tmp/peer128-burnin-1785154952-report.json
/tmp/peer128-burnin-1785154953-report.json
```

## Aggregate results

```json
{
  "runs": 10,
  "errors": 0,
  "positive_total": 50,
  "positive_decisions": 50,
  "positive_success": 50,
  "negative_total": 50,
  "negative_false_positive": 0,
  "raw_full_blocked": 50,
  "raw_session_only_blocked": 50,
  "fallback_ok": 10,
  "unclean_ok": 10,
  "correlation_errors": 0,
  "event_count_total": 560,
  "node_ids": {"peer128": 50},
  "score_min": 0.6503,
  "score_mean": 0.6847,
  "score_max": 0.7281
}
```

Event counts across the 10 reports:

```json
{
  "retrieval_event": 50,
  "execute_code_started_event": 120,
  "intervention_event": 50,
  "capability_invocation_event": 70,
  "outcome_event": 50,
  "protocol_state_transition": 190,
  "fallback_authorization_event": 20,
  "bypass_event": 10
}
```

## Interpretation

Passed for the narrow peer128-only Phase 1B canary:

- 50/50 positive peer128 health prompts selected `hmp-healthcheck`.
- 50/50 live invocations returned `node_id=peer128`, `peer_status=ok`, and `resolved_success`.
- 50/50 full-context raw `execute_code` attempts were blocked while an intervention was open.
- 50/50 session-only raw `execute_code` attempts were blocked, covering hooks that omit `episode_id`.
- 50/50 negative prompts produced no active decision and no unsafe dispatch.
- 10/10 clean timeout simulations issued and consumed fallback tokens.
- 10/10 unclean read-only simulations reached `failed_unclean_read_only` and accepted one structured continuation.
- 0 event-chain correlation errors across 560 events.

## Safety boundary

This evidence supports only this scope:

```text
peer = peer128
capability = hmp-healthcheck@1.0.0
effect = read-only HMP health probe
active allowlist = hmp-healthcheck
permissions = hmp.network.read
available capability = hmp_client_installed
```

It does not authorize broad active mode, mutating capabilities, raw IP targets, or other peers.
