# External review six-blocker remediation — 2026-07-27

Status: implemented in source skill and synchronized runtime plugin.

Scope remains conservative:
- Passive live-shadow collection: GO.
- Formal empirical Phase 0 closure: NOT YET.
- Formal active Phase 1B authorization: NO-GO until empirical gates and raw pinned-runtime evidence are packaged.
- Active path is only an engineering smoke test / narrow peer burn-in for `hmp-healthcheck@1.0.0`.
- `hmp-send@1.0.0` remains mutating/unsafe/not active.

## Blockers remediated

1. Exactly-once execution decision per turn
   - Added turn-scoped decision tombstones in `InterventionStore`.
   - After a bypass, successful capability invocation, clean fallback consumption, or unclean continuation, a second decision-capable `execute_code` in the same turn is rejected.

2. Clean fallback requires structured `harness_failure` bypass
   - Removed token-only continuation from the active authorization path.
   - Clean fallback now requires `capability_reuse_bypass.reason_code=harness_failure` with `prior_invocation_id`, `failure_code`, and `fallback_authorization_id` matching the issued token.
   - Token consumption happens only after the structured record validates.

3. Protocol blocks are recorded as blocked outcomes
   - `authorize_execute_code()` records protocol blocks keyed by `tool_call_id`.
   - `record_tool_outcome()` emits `outcome=blocked` and `block_origin=protocol` for those calls.

4. v1.6 bypass vocabulary
   - Accepted reason codes now include: `missing_feature`, `taxonomy_gap`, `incompatible_input`, `incompatible_output`, `environment_constraint`, `harness_failure`, `harness_failure_unclean`.
   - Structured fields include `proposed_feature_slug`, `schema_path`, `constraint_id`, `prior_invocation_id`, `failure_code`, and `fallback_authorization_id` as applicable.
   - Back-compat aliases `unsupported_feature` and `schema_mismatch` are accepted only for compatibility.

5. Input/output contract enforcement
   - Added `strict_validate_against_schema()` and call it at `invoke_capability` boundary.
   - Dispatcher outputs are validated against `output_schema` before `resolved_success`.
   - Output violations return `output_contract_violation` and transition to failure state, not success.
   - Uses `jsonschema.Draft7Validator` if installed; otherwise enforces the draft-07 subset used by bundled contracts.

6. Exact-version contract lookup
   - `registry.get_contract(capability_id, version)` now fails closed if the exact version is absent.
   - It no longer falls back to `contracts/<capability_id>.json` when a version was explicitly requested.
   - Versioned file fallback requires `contracts/<capability_id>/<version>.json` with matching internal `capability_id` and `version`.

## New regression tests

`tests/test_external_review_blockers_20260727.py` covers:
- second decision in same turn rejected;
- clean fallback without structured record rejected;
- protocol-blocked tool result logged as `outcome=blocked`, `block_origin=protocol`;
- v1.6 reason codes accepted with spec fields;
- invalid dispatcher output becomes `output_contract_violation`;
- unknown exact capability version returns `None`.

## Validation

Final local validation after source/runtime sync:
- `python3 -m compileall -q plugin tests scripts /root/.hermes/plugins/capability-reuse`: OK
- `python3 -m unittest discover -s tests -q`: 37/37 OK
- `python3 scripts/conformance-suite.py`: local simulated integration 15/15 OK
- `python3 scripts/active-canary-burnin.py peer138`: errors 0; positives 5/5; negatives 0/5 false positives; clean fallback `fallback_consumed`; unclean `unclean_fallback_recorded`; correlation errors 0

Evidence bundle added under `evidence/`:
- `deployment-manifest.json`
- `conformance-report.json`
- `peer138-burnin-smoke-20260727.json`
- `selected-event-chains.jsonl`
- `SHA256SUMS`
