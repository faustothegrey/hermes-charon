# T3 Disposition Accounting — zero-orphan review-queue fix (2026-08-13)

## The bug

`scripts/generate-review-queue-v245.py` silently SKIPPED every `retrieval_event`
that had no candidates and no `top_capability`:

```python
if not candidates and not d.get("top_capability"):
    continue   # ← event disappears, no disposition assigned
```

Result on peer70: 143 retrieval events in `events.jsonl`, but the review queue
reported only 123 records. **20 events had NO disposition** — including 3 real
`organic_peer` events (dual-plane/plugin live traffic). This violates the
v2.4.16 gate: *"assign every retrieval event exactly one disposition... gate
passes only with zero unexplained retrieval or execution-chain orphans."*

## The fix

Instead of `continue`, emit an explicit excluded record with a structured reason:

```python
if not candidates and not d.get("top_capability"):
    excluded.append({
        "review_schema_version": "1.0",
        "review_id": "excluded_%s" % (ev.get("event_id") or d.get("retrieval_event_id") or "unknown"),
        "timestamp": d.get("timestamp") or ev.get("timestamp") or "",
        "event_schema_version": ev.get("schema_version") or d.get("schema_version") or "",
        "disposition": "excluded",
        "disposition_reason": "no_reviewable_candidate",
        "traffic_type": d.get("traffic_type") or "unknown",
        "requester_peer_id": ((d.get("requester") or {}).get("requester_peer_id")) or "",
        "processing_peer_id": d.get("processing_peer_id") or "",
        "raw_request_ref": "event:%s" % (ev.get("event_id") or d.get("retrieval_event_id") or ""),
    })
    continue
```

Also write `queue-v245-excluded.jsonl` and add to the summary:
`"excluded_records": len(excluded)`, `"disposition_accounting_total": len(records) + len(excluded)`.

## Verification (independent cross-check)

```python
# total in source must equal records + excluded
retrievals = count of '"event_type": "retrieval_event"' in events.jsonl
assert records_total + excluded_records == retrievals   # 123 + 20 = 143 ✅
```

Pass = zero unexplained orphans: every retrieval event has exactly one
disposition (review row OR excluded-with-reason). Explicit exclusions are
acceptable when the reason is structured and reviewable — the gate does not
require all events to become review rows.

## Live-metadata note (same session)

`emit_retrieval` events from the plugin/dual-plane carry metadata only when the
sender identity is present: `traffic_type="organic_peer"` requires a
`requester` dict with `requester_peer_id`, `processing_peer_id`, plus
`provenance="organic_live"`. On HMP, the `from` field in the message body is
what feeds `requester_peer_id` — without it, events come out
`traffic_type=unknown`, `requester_peer_id=""`, and organic-cohort tests fail.
