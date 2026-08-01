# Capability Reuse review remediation — 2026-07-27

Use this reference when resuming work on the capability-reuse plugin after external review of the Phase 0 / Phase 1A live-shadow implementation.

## Core lesson

A plugin can look architecturally aligned while still being non-operational. For live-shadow work, verify an end-to-end episode, not just module presence:

1. `pre_llm_call`/controller calls retriever.
2. Retriever emits a redacted `retrieval_event`.
3. Candidate evidence includes IDs, versions, scores, eligibility and ineligibility reasons.
4. Shadow mode returns no intervention/injection.
5. `pre_tool_call`/`post_tool_call` passive observations persist correlated events.
6. Automated tests prove at least one real shadow episode.

## Review findings that became required checks

- Do not leave protocol/controller methods as no-op stubs when real implementations exist elsewhere; wire the live-shadow path directly.
- In shadow mode, never register executable tools that claim success without dispatch. Either hide the tool or return explicit `success=false` / `shadow_mode_not_executable`.
- Hermes plugin tool schemas should use the documented shape: `{name, description, parameters}`.
- Conformance gates must fail when required tests are skipped. A result like `2 passed / 13 skipped` is not a pass.
- HMP send/message delivery is mutating, unsafe to retry blindly, and can have uncertain/partial effects after timeout.
- Static fingerprinting must be conservative: `requests.post()` is mutating; `Path.read_text()` is read-only; static hints are not observed effects; stable IDs use SHA-256, not Python `hash()`.
- Structured JSONL audits should inspect object fields such as `tool`, `arguments.code`, and `code` before falling back to regex over text.
- Persisted previews need redaction for tokens/passwords, credentialed URLs, sensitive query params, and private paths.
- Protocol state machines need explicit transition tables, defensive snapshots, and single-live-token fallback semantics.

## Verification pattern

Run from the skill/plugin root:

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 -m compileall -q .
/usr/local/lib/hermes-agent/venv/bin/python3 -m unittest discover -s tests -v
/usr/local/lib/hermes-agent/venv/bin/python3 scripts/register-capability.py
/usr/local/lib/hermes-agent/venv/bin/python3 - <<'PY'
from plugin import protocol
print(protocol.retrieve(
    session_id='verify-session',
    user_message='check all HMP peers',
    hook_context={'episode_id': 'verify-episode'},
))
PY
```

Expected smoke result in shadow mode:

- `retrieve()` returns `None`.
- `/root/.hermes/data/reuse-observer/events.jsonl` receives a `retrieval_event`.
- Candidate list includes semantic candidates with `eligible_for_intervention=false` and explicit reasons such as `trust_state_observed`, `permissions_unknown`, or `availability_unknown`.
- `hmp-send` appears as `effect_class: mutating`.

For the conformance gate:

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 scripts/conformance-suite.py --profile full-required
```

Expected until live Hermes integration tests are implemented:

- exit code `1`
- skipped required tests reported explicitly
- report written under `/root/.hermes/data/capability-registry/conformance-report.json`

This failure is intentional and safer than a false pass.
