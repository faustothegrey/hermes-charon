# Dual-Plane → Plugin Convergence (2026-08-13)

## Decision

The standalone dual-plane server (`:18644`, `hmp_dual_plane*.py`) is being retired.
All peer-to-peer messaging converges on the HMP gateway plugin (`:18643`), which
internally uses the Hermes API (`:8642`). Rationale: the plugin already preserves
per-peer session context via `chat_id=from_peer` in `handle_message()` — the
dual-plane added only: explicit `session_id` (peer_pair_id), per-node API keys
(unnecessary inside the gateway), live-shadow event_store, and a `send_to_peer()`
client. Fusing removes a whole process (no more "dual-plane not up after reboot"),
one port, one restart surface, and ~530 lines of code.

## What the plugin needed (parity deltas)

1. **`session_id` in `/hmp/send` payload** → `chat_id = session_id or from_peer`
   (plugin v0.1.4). Keeps per-peer-pair conversational context.
2. **`/send` alias on :18643** for legacy dual-plane clients (body `{session_id, text, max_tokens}`).
3. **Live-shadow event_store in the plugin consumer_loop** (NOT core.py — the
   loop lives in `plugins/hmp/adapter.py`). Grep for `HAS_EVENT_STORE` there.
4. **`send_to_peer()` → `:18643/send_and_wait`** with session_id.

## The metadata gap (why capability-reuse T2 failed)

`emit_retrieval()` in the plugin/dual-plane emitted events with
`traffic_type="unknown"`, `requester_peer_id=None`, `provenance.valid=False`.

Root cause: the gateway plugin hooks (`pre_llm_call` etc.) fire ONLY for
`:8642` traffic (Telegram/CLI/API). HMP/dual-plane traffic does NOT pass through
them, so `hook_context` never carries `source_peer_id`/`requester_peer_id`.
`_extract_traffic_type()` in `retriever.py` returns `"unknown"` without those
fields.

Fix (Option A, agreed with peer106 — single emission source in the hooks, dual-plane/plugin
as context propagator): the emitting path must pass requester metadata explicitly.

```python
# In adapter.py consumer_loop (and equivalently dual-plane process_message):
requester_peer = str(from_peer or "").strip()
emit_retrieval(
    session_id=chat_id,
    user_message_preview=text[:200],
    candidates=[], top_score=0.0, intervened=False, latency_ms=0.0,
    traffic_type="organic_peer" if requester_peer else "unknown",
    provenance="organic_live" if requester_peer else None,
    provenance_source="hmp_plugin.consumer_loop",
    provenance_detail="from_peer",
    requester={
        "actor_type": "agent",
        "actor_id": f"hmp:{requester_peer}" if requester_peer else "unknown",
        "request_channel": "hmp",
        "requester_peer_id": requester_peer,
        "processing_peer_id": self.node_id,
    } if requester_peer else None,
)
```

Client side: `send_to_peer()` must include `"from": "peerXX"` in the POST body
so the receiving peer knows the sender. The handler extracts it:
`requester = body.get("from", body.get("sender", body.get("requester_peer", "")))`
and passes it through `process_message(session_id, text, requester=...)`.

## Verification (T2 equivalent)

After patch + gateway restart, send `{"session_id": "X_Y", "text": "...", "from": "peer58"}`
to `:18643/send` and check the newest `retrieval_event` in
`~/.hermes/data/reuse-observer/events.jsonl`. PASS requires:
`traffic_type=organic_peer`, `requester_peer_id=<sender>`, `actor_id=hmp:<sender>`,
`processing_peer_id=<self>`, `provenance.valid=true`, `schema_version=1.2`.

## Test battery T1-T6 (agreed with peer106, for promoting the 2.4.16 skill)

- **T1 Artifact Identity**: PID+start of gateway, loaded plugin path, all internal
  version surfaces aligned (SKILL.md, plugin.yaml, protocol.VERSION), archive vs
  runtime tree hash (exclude `__pycache__`/`.pyc`/transient), deployment manifest
  is the deployment authority — SKILL.md versions alone do NOT promote a release.
- **T2 Clean Cohort**: one REAL organic hook-path event with full metadata; PASS
  fails if fresh organic events = 0. (This session: initial run FAILED with
  `traffic_type=unknown`, root cause = missing requester metadata — fixed above.)
- **T3 Disposition Accounting**: every retrieval event has exactly one disposition;
  chain errors reported separately (retrieval w/o start, start w/o completion,
  completion w/o start, duplicate completion, id mismatch). Zero unexplained orphans.
- **T4 Eligibility Fail-Closed**: `formal_holdout_eligible` recomputed from trusted
  fields only, never accepted as input flag; reject reasons: legacy_schema,
  unsupported_schema, missing_artifact_hash, wrong_plugin_version,
  wrong_deployment_id, invalid_provenance, non_organic_traffic, unknown_requester,
  unknown_processing_peer, outside_cohort.
- **T5a Reversed/Rejection**: composite prompt ("check health and restart if
  unhealthy") must NOT open an active decision, or be excluded with structured reason.
- **T5b Cross-Peer**: processing peer must emit its OWN chain with live metadata;
  a remote HMP health response alone does not count. Verify peer58 PID/start changed,
  plugin loaded, fresh post-restart retrieval event.
- **T6 Scope**: report must state validation limited to peer58+peer106, no
  generalization to the fleet.

## Rollout order

peer70 (dev, already merged) → peer58 (canary) → peer106 → peer138 → retire
`:18644` + `hmp_dual_plane*.py` last. Parity battery (C1-C5 + reboot persistence
+ session isolation + clean 404 on retired endpoints) must pass on :18643 before
retiring the dual-plane.

## Lesson on "version is ahead" ≠ "deployment"

peer106 had skill 2.4.16 while peer70 was on 2.4.6 and the deployment-manifest
still declared 2.4.7 selected/pending. peer106 itself confirmed: SKILL.md/plugin/
protocol saying 2.4.16 does NOT promote a release — the deployment manifest is
the authority, and promotion requires archive rebuild + hash coherence + clean
deployment boundary + live metadata proof. When a peer appears "ahead", verify
whether it is a successor line or a WIP fork before copying it fleet-wide.
