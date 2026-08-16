# Pre-Packaging Review Checklist (peer70 = reviewer)

Reusable review flow for any capability-reuse version bump BEFORE packaging.
First used for the v2.6.0 review (2026-08-16, delta da v2.5.0). Per Fausto
policy, peer70 is the source of truth and must review the complete delta
before the archive is built/distributed.

## Steps

1. **Load SKILL.md** via skill_view — note the declared `version:` in
   frontmatter vs the `description`/changelog: a description already claiming
   the new state while `version:` is stale is normal pre-bump, but flag it.
2. **Verify each delta item in the source tree** (skill) — for code fixes,
   grep the exact symbols/patterns the delta claims (e.g.
   `collector_peer_id`, `operator_solicited`, `EXPECTED_COHORT_LABEL`).
3. **Source ↔ runtime parity**: `diff -rq <skill>/plugin <runtime>/plugins/capability-reuse`
   — only `__pycache__` may differ. Any `.py` divergence = blocker
   (plugin-runtime-vs-skill-divergence rule).
4. **Run the full suite**: `python3 -m unittest discover -s tests`
   — read `Ran N tests` from the real run, NOT `grep -c "def test_"`.
   Grep overcounts when duplicate files exist (v2.6.0: 144 declared vs
   132 executed because `test-p0.py` ≡ `test_phase1a_provenance_failclosed.py`
   but hyphenated module names are silently skipped by discover).
5. **Check referenced evidence exists**: grep the handoff/plan/status docs
   for every `evidence/...` path they cite, then `ls` each one. A doc
   referencing a missing artifact (v2.6.0: `phase0-closed-2026-08-16/` +
   `phase0-closure-review-2026-08-16.md` absent on peer70) is a packaging
   blocker — the archive would ship with broken references.
6. **Changelog hygiene**: check for duplicate entries (v2.6.0: 2.4.6 listed
   twice verbatim) and missing entry for the new version.
7. **Env-default coherence**: compare hardcoded defaults in code
   (`os.environ.get(..., "v2.5.0_live")`) against the actual deployment
   values cited in docs (cohort label `phase0_p141_p70`) — flag mismatches
   as deploy-time requirements.
8. **Out-of-skill P0 fixes** (e.g. `plugins/hmp/adapter.py`): verify in the
   RUNTIME plugin location, not the skill tree.

## Verdict format (Fausto)

- Table of verified items (esito ✓) with line/file evidence.
- Rilievi numbered R1..Rn, each with severity (bloccante/minore) + exact
  fix. Blocking item = packaging must wait.
- Final: `Bump X.Y.Z: OK, ma packaging solo dopo <blocker> + pulizia <R2/R3>`
  — never unconditional GO with open blockers.

## v2.6.0 outcome (reference)

Verdict: bump OK, packaging gated on syncing the missing closure evidence
from peer141 + removing the duplicate test file + changelog dedupe.
