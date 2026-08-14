# Version-bump stale-test refresh — v2.4.18 (2026-08-13)

When a spec release changes event schema / validation semantics, old unit-test
fixtures assert PRE-bump expectations and fail CORRECTLY against the new code.
Diagnose as stale-expectation BEFORE touching production code: read the
production validation function (e.g. `review_queue.formal_holdout_validation`)
and compare with the spec reference. If code matches spec → fix the fixtures,
never the code.

## Symptom signature (identical on peer70 and peer141)
- `test_phase1b_active_healthcheck.py:243` — asserted `schema_version "1.2"`,
  code now emits `"1.3"` (spec point 1).
- `test_v246_review_remediation.py:79` — fixture was a v2.4.16 event
  (schema 1.2, plugin_version 2.4.16, cohort `v2.4.16_*`), so
  `formal_holdout_eligible=False` — code correctly rejects per spec point 15.
- `test_v247_peer58_scope.py:34` — asserted `PLUGIN_VERSION == "2.4.16"`,
  code now `"2.4.18"`.

## v2.4.18 holdout-eligibility fixture checklist
`formal_holdout_validation` (plugin/review_queue.py) requires ALL of:
- event `schema_version == "1.3"`
- data `plugin_version == "2.4.18"`
- data `deployment_id` present
- data `plugin_artifact_hash` present, NOT starting with "placeholder"
- data `cohort_label == "v2.4.18_live"`
- `provenance.stream == "organic_live"` and `valid is True`
- `traffic_type` in {organic_user, organic_peer};
  registry_sync/test/acceptance/calibration/cron/retry → auto-reject
- data `requester_peer_id` at TOP LEVEL — the one nested inside the
  `requester` sub-dict is NOT read by the validation
- data `trace_id` present
- data `producer_surface` not in (None, "", "unknown")

Also rename test methods whose name embeds the old version (v2414 → v2418).

## Procedure (peer70 coordinator)
1. Reproduce:
   `cd ~/.hermes/skills/hermes/capability-reuse/tests && python3.11 -m unittest discover -s . -p "test_*.py"`
   (tests are unittest-based — pytest is NOT installed on peer70; do not use it)
2. Confirm the failures are stale-expectation, not code bugs (compare
   production validation fn against spec reference).
3. Patch fixtures to current spec; run the full suite: 72/72 green (includes
   the conformance integration gate).
4. Peers re-sync the changed test files via scp from peer70, re-run locally,
   confirm the same green count.

## Environment gotcha
`scripts/conformance-suite.py` Test 1 ("Plugin discovery & registration")
fails with `No module named 'yaml'` when PyYAML is missing. Fix:
`python3.11 -m pip install --user --break-system-packages pyyaml`
(user site-packages only; PEP 668 bypass; does not touch system python).

## Peer alignment verification (pre-release)
When a peer asks to verify alignment, check all three:
1. `version:` in BOTH `~/.hermes/skills/hermes/capability-reuse/SKILL.md`
   and `~/.hermes/plugins/capability-reuse/plugin.yaml`
2. `plugins.enabled` in `~/.hermes/config.yaml` includes capability-reuse
   (missing → hooks never fire; e2e tests would run against inert code)
3. sha256 of skill SOURCE (`skills/.../capability-reuse/plugin/*.py`) vs
   runtime plugin (`~/.hermes/plugins/capability-reuse/*.py`) — must match
