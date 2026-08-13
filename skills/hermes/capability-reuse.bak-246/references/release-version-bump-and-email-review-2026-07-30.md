# Capability-reuse release version bump + email-review packaging pattern — 2026-07-30

Use this when preparing a new deployable capability-reuse skill/plugin archive for Fausto review.

## Trigger

Fausto asks to bump the skill version and send a ZIP of the implementation for review.

## Durable pattern

1. Treat data-contract/evidence-pipeline changes as a real release.
   - Do not reuse the previous release number when event schema, analyzer schema, rollups, dashboard output, or evidence semantics changed.
   - For the provenance/rollup/review-export work, the correct bump was `2.4.1 -> 2.4.2`.

2. Bump all version surfaces together.
   - `SKILL.md` frontmatter `version`.
   - `plugin/plugin.yaml` source copy.
   - runtime `~/.hermes/plugins/capability-reuse/plugin.yaml` if validating against local runtime.
   - `plugin/protocol.py` source `VERSION`.
   - runtime `~/.hermes/plugins/capability-reuse/protocol.py` if validating against local runtime.
   - `evidence/deployment-manifest.json`: `version`, `skill_version`, `plugin_version`, `protocol_VERSION`, artifact name, release decision, validation command list, and status.

3. Keep runtime/source copies aligned before conformance.
   - The local conformance harness loads runtime plugin files from `~/.hermes/plugins/capability-reuse` when present.
   - If only the source skill is bumped, conformance may validate stale runtime metadata or code.

4. Regenerate evidence after validation.
   - Run `compileall`, full unittest discovery, and `scripts/conformance-suite.py --profile full-required`.
   - Copy `/root/.hermes/data/capability-registry/conformance-report.json` into a versioned evidence file, e.g. `evidence/conformance-report-v2.4.2.json`.
   - Write a versioned unit-test evidence file, e.g. `evidence/unit-test-report-v2.4.2.json`, with exact pass/fail counts.
   - Update `deployment-manifest.json` with current plugin tree hash and report paths.
   - Regenerate `evidence/SHA256SUMS` after every manifest/report edit.

5. Package from the parent directory.

```bash
cd /root/.hermes/skills/hermes
rm -f /tmp/capability-reuse-vX.Y.Z.zip /tmp/capability-reuse-vX.Y.Z.zip.sha256
zip -qr /tmp/capability-reuse-vX.Y.Z.zip capability-reuse \
  -x '*/__pycache__/*' '*.pyc' '*/.pytest_cache/*'
sha256sum /tmp/capability-reuse-vX.Y.Z.zip > /tmp/capability-reuse-vX.Y.Z.zip.sha256
```

6. Validate the canonical archive.

```bash
cd /root/.hermes/skills/hermes/capability-reuse
python3 scripts/validate-release-archive.py \
  /tmp/capability-reuse-vX.Y.Z.zip \
  --version X.Y.Z \
  --sha256-file /tmp/capability-reuse-vX.Y.Z.zip.sha256
```

Expected success shape:

```text
PASS release archive /tmp/capability-reuse-vX.Y.Z.zip version X.Y.Z sha256 <hash> internal_checks <n>
```

7. If you mark `release_archive_validator=PASS` in the manifest after validation, repackage and re-run the archive validator.
   - Editing the manifest changes `SHA256SUMS`, archive content, size, and ZIP hash.
   - The final hash is the one after this last package+validate pass.

8. Email via peer70 when local Himalaya is unavailable.
   - Copy ZIP and sidecar to peer70.
   - Verify `sha256sum -c` and size on peer70 before sending.
   - Use Himalaya MML multipart attachment syntax with `/home/fausto/.local/bin/himalaya template send --account virgilio --output json`.
   - Success signal: `"Message successfully sent!"`.

## Example final verification facts from v2.4.2

- Archive: `/tmp/capability-reuse-v2.4.2.zip`
- SHA256: `8ffd4be2ffa76f23726d036a5ae7e8acf299ca7f4cb37c54eec30bf2ff54ea13`
- Size: `203954 bytes`
- Archive validator: PASS
- Unit tests: 52/52 PASS
- Conformance: 15/15 PASS local-controller
- Email send: `"Message successfully sent!"`

Do not treat this release as changing formal active authorization status. v2.4.2 was passive-shadow/evidence-pipeline only; formal active rollout remains review-gated.
