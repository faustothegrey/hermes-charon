# Testing the HMP gateway adapter in isolation (G0, 2026-08-16)

How to run regression/smoke tests against `~/.hermes/plugins/hmp/adapter.py`
without restarting the gateway or sending real peer traffic. Verified on
Charon (peer70, Hermes 0.17.0); the harness passes 30/30.

## Import requirements

- Use the **Hermes venv python**, NOT system python3 (Debian system python
  3.9 fails on `str | object` unions used by the codebase):
  `~/.hermes/hermes-agent/venv/bin/python`
- `sys.path` needs three roots:
  - `~/.hermes/plugins` → package root so `import hmp.adapter` works
  - `~/.hermes/skills/hermes/capability-reuse/plugin` → `event_store`
  - the hermes-agent repo cwd → `gateway.*`, `hermes_cli.*`
- Do NOT use `importlib.spec_from_file_location` on adapter.py — the relative
  import `from .core import ...` requires package context. `import hmp.adapter`
  (with plugins on sys.path) is the way.

## Register the platform first

`HMPAdapter.__init__` calls `Platform("hmp")`; the dynamic enum member only
exists if the platform is registered (or is a bundled plugin). In tests:

```python
from gateway.platform_registry import PlatformEntry, platform_registry
if not platform_registry.is_registered("hmp"):
    platform_registry.register(PlatformEntry(
        name="hmp", label="HMP",
        adapter_factory=lambda cfg: HMPAdapter(cfg),
        check_fn=lambda: True))
```

Without this: `ValueError: 'hmp' is not a valid Platform`.

## Testable structure (G0 refactor)

The consumer loop is `while True` — never test it directly. G0 extracted
per-message processing into `async def _process_item(item) -> dict` returning
`{trace_id, outcome, error, traffic_type, surf_id}`. Test that instead:

- FakeStore stub: `mark_status`/`fail` no-ops
- stub `a.handle_message = fake_handle` (async, returns None) so no real agent
  turn runs
- monkeypatch module-level `emit_retrieval` / `emit_surface_execution_start` /
  `emit_surface_execution_complete` to capture kwargs (record trace_id per
  emit call) — this is how chain correlation is asserted

## Verified harness

`~/.hermes/skills/hermes/capability-reuse/analysis/test_g0_adapter.py`
(30/30 PASS): unique UUID v4 trace_id per request, same trace across
retrieval→start→complete, 14 fail-closed provenance cases, collector
body>env>absent, no chat_id/peer trace leakage.

## Smoke without gateway restart

Loading the module directly + calling `_process_item` writes real events to
`~/.hermes/data/reuse-observer/events.jsonl` (event_store works when the
capability-reuse plugin dir is on sys.path). Record the event count BEFORE the
smoke and diff after, to isolate the smoke's own events.

**Caveat:** the systemd gateway keeps running the OLD code until a manual
restart (per Fausto policy, restart gateway = manuale). An in-process smoke
validates the new logic, NOT the deployed binary. The deployed adapter only
picks up changes at the next gateway restart.
