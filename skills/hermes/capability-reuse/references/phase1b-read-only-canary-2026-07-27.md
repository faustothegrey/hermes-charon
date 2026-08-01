# Phase 1B read-only canary — hmp-healthcheck@1.0.0

Use this reference when extending capability-reuse from shadow observation into narrowly-scoped active dispatch.

## Durable pattern

Start Phase 1B with exactly one read-only, idempotent, allowlisted capability. Do not begin with mutating capabilities.

Implemented canary shape:

- Active mode env: `CAPABILITY_REUSE_MODE=active`.
- Active allowlist env: `CAPABILITY_REUSE_ACTIVE_CAPABILITIES=hmp-healthcheck`.
- Retrieval gates env:
  - `CAPABILITY_REUSE_INTERVENTION_THRESHOLD`
  - `CAPABILITY_REUSE_MINIMUM_MARGIN`
- Default active capability: `hmp-healthcheck@1.0.0` only.
- Mutating/unsafe capabilities such as `hmp-send` remain non-active even if present in the registry.

## Dispatcher rules

The dispatcher must call deterministic audited executors only. It must not synthesize Python or silently fall back to `execute_code`.

Required checks before dispatch:

1. active mode is enabled
2. capability is in active allowlist
3. intervention ID exists
4. requested capability/version matches the intervention
5. input schema validates
6. effect class is `read_only`
7. claim of intervention succeeds atomically

For `hmp-healthcheck@1.0.0`, the executor uses Python stdlib HTTP calls to known HMP health endpoints:

- Hermes peers: `/hmp/health`
- trixie/peer136: `/health`

## Intervention/blocking rules

When an active intervention is open:

- raw `execute_code` must be blocked
- allow raw `execute_code` only with:
  - valid structured bypass tied to the intervention, or
  - valid single-use fallback token after a clean read-only capability failure

Clean read-only failures may issue a fallback token if the failure code is in the contract's clean-failure list. Mutating/unknown effect classes must not receive automatic fallback.

## Event chain to verify

A complete canary episode should persist a reconstructable chain containing at least:

- `retrieval_event`
- `intervention_event`
- `protocol_state_transition` to `open`
- `capability_invocation_event`
- success: `outcome_event` and state `resolved_success`
- clean failure: `fallback_authorization_event`
- unsafe failure: `post_failure_escalation_event`

## Regression tests

Add/maintain tests for:

- active retrieval selects the allowlisted read-only capability
- injection text references exact capability version
- raw `execute_code` is blocked while intervention is open
- successful invoke resolves the intervention
- clean read-only failure issues a single-use fallback token
- mutating capability is refused when not allowlisted

Existing test file from the canary implementation:

`tests/test_phase1b_active_healthcheck.py`

## Verification recipe

Run from the capability-reuse skill directory:

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 -m compileall -q .
/usr/local/lib/hermes-agent/venv/bin/python3 -m unittest discover -s tests -v
/usr/local/lib/hermes-agent/venv/bin/python3 scripts/conformance-suite.py --profile full-required
```

Optional live smoke for the canary: create an `hmp-healthcheck@1.0.0` intervention and invoke it against `peer70`; expected result is `success: true`, peer `status: ok`, intervention state `resolved_success`, and multiple persisted events.

## Pitfall

Do not treat passing local conformance as permission to enable all capabilities. The local harness validates hook contracts and the canary path; each additional capability still needs its own trust promotion, deterministic dispatcher, schemas, fallback policy, and live smoke.