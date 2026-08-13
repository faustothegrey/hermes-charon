# Post-review remediation pattern — capability-reuse, 2026-07-27

Use this when an external reviewer accepts implementation remediation but rejects formal empirical closure.

## Durable lessons

1. Treat review text as executable specification.
   - Convert each concrete critique into a regression test first or alongside the implementation change.
   - Keep formal status conservative while fixing engineering issues.

2. Separate engineering remediation from empirical authorization.
   - `compileall`, unit tests, local conformance, and smoke tests can prove implementation quality.
   - They do not close Phase 0 if the benchmark uses synthetic/template-leaked holdouts, circular labels, proxy retrievers, simulated runtime conformance, or uncalibrated thresholds.

3. Tombstone/state cleanup invariant for active mode.
   - Turn-scoped decision tombstones must not outlive the turn indefinitely.
   - Cleanup must cover interventions plus auxiliary state: decision tombstones, blocked-call records, fallback/unclean records, and retrieval envelopes.
   - Hooks should run maintenance opportunistically.
   - Missing `turn_id` needs explicit coverage: cleanup and next pre-LLM turn must clear previous missing-turn tombstones.

4. Production retriever evaluation invariant.
   - Never accept regex/proxy benchmark results as evidence for C6/C7.
   - Test the actual production retriever with the claimed threshold and margin.
   - Include hard negatives for negation, informational intent, documentation/code-generation intent, and mutating composites.

5. Read-only canary hard negatives to include.
   - `do not check HMP health for peer128`
   - `what is the HMP health endpoint?`
   - `generate Python code to check HMP health for peer128`
   - `check HMP health and restart peer128 if unhealthy`
   - `explain how to check HMP health`
   - `compare HMP health endpoints`

6. Evidence hygiene.
   - Move rejected closure artifacts under `evidence/phase0/rejected-closure-attempt/`.
   - Add an explicit machine-readable notice: `status=REJECTED_AS_FORMAL_CLOSURE`, `use=tooling_and_corpus_evidence_only`.
   - Regenerate checksums after moving or editing evidence files.
   - Update manifest/test counts and runtime-evidence docs to distinguish local controller conformance from pinned Hermes runtime conformance.

## Validation checklist after fixes

- `python3 -m compileall -q plugin scripts tests`
- `python3 -m unittest discover -s tests -v`
- `python3 scripts/conformance-suite.py --profile full-required --output <path>`
- Sync source plugin to runtime plugin when runtime evidence depends on it.
- Verify source/runtime plugin diff excluding `__pycache__`.
- Recompute `evidence/SHA256SUMS` and `evidence/phase0/SHA256SUMS`.

## Status wording to preserve

```text
Implementation remediation: PASS
Passive shadow collection: GO
Local controller conformance: PASS
Pinned Hermes runtime conformance: pending/partial
Formal Phase 0 closure: NO-GO
Formal Phase 1B authorization: NO-GO
```
