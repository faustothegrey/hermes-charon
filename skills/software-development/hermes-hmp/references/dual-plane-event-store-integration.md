# Dual-Plane Event Store Integration

## Purpose

Integrate the `capability-reuse` event store into the dual-plane server (`:18644`)
so that every peer-to-peer message emits live-shadow telemetry — without
needing Hermes plugin hooks (which only fire on gateway sessions).

## Architecture

```
peer70 ──POST :18644/send──► peer106 dual-plane server
                                  │
                            process_message()
                              ├── emit_retrieval()      ← live-shadow, ~50µs
                              ├── Hermes API / HMP call ← existing, 3-60s
                              ├── emit_observation()    ← post-exec, ~50µs
                              └── return response
```

## Implementation

In `hmp_dual_plane.py`, the integration lives at the top of the file:

```python
# ── Capability Reuse event store integration ──
try:
    SKILL_DIR = Path.home() / ".hermes" / "skills" / "hermes" / "capability-reuse" / "plugin"
    if SKILL_DIR.exists() and str(SKILL_DIR) not in sys.path:
        sys.path.insert(0, str(SKILL_DIR))
    from event_store import emit_retrieval, emit_observation, emit_execute_code_start, emit_execute_code_complete
    HAS_EVENT_STORE = True
except Exception as e:
    HAS_EVENT_STORE = False
```

And in `process_message()`:

```python
if HAS_EVENT_STORE:
    emit_retrieval(session_id=session_id, text=text[:200])
```

## Overhead

Measured on peer106 (Hermes v0.17.0, Fedora, 939MB RAM):

| Metric | Value | Notes |
|--------|-------|-------|
| Per `emit_` call | ~50-100 µs | JSON serialize + append (no fsync) |
| Emits per message | 3 | retrieval + start + complete |
| Total overhead | **~150-450 µs** | vs 3-60s LLM generation |
| File size per event | ~400 bytes | JSON |
| Daily growth | ~5-10 MB | at 10,000 msgs/day |
| CPU impact | <0.1% | Sequential I/O only |
| Memory | ~50 KB | Write lock buffer, no in-RAM accumulation |

## Deployment

1. Copy `hmp_dual_plane.py` to the peer
2. Ensure `capability-reuse` skill is at `~/.hermes/skills/hermes/capability-reuse/`
3. Restart dual-plane server
4. Verify: `ls ~/.hermes/data/reuse-observer/events.jsonl`

## Verification

```bash
# Check events are being collected
wc -l ~/.hermes/data/reuse-observer/events.jsonl

# Send a test message via dual-plane to trigger event emission
curl -s -X POST http://<peer>:18644/send \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","text":"ping"}'

# Verify count increased
wc -l ~/.hermes/data/reuse-observer/events.jsonl
```

## Status (2026-07-28)

| Peer | Events collected | Status |
|------|-----------------|--------|
| peer70 | 1,113 | ✅ Active for 22.4h |
| peer106 | 56 | ✅ Active |
| peer58 | 4 | ✅ Recently deployed |
| peer84 | 0 | ✅ Deployed |
| peer138 | 0 | ✅ Deployed |

## Notes

- Events are JSONL (append-only, no mutation)
- File location: `~/.hermes/data/reuse-observer/events.jsonl`
- No fsync on write — crash-safe enough for telemetry, not for transactional data
- The event store path is separate from the Hermes gateway event stream
