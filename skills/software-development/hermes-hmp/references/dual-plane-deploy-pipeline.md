# Dual-Plane Deploy Pipeline

Safe development/test/deploy pipeline for protocol updates.

## Deploy Order

| Step | Peer | Role | Why |
|------|------|------|-----|
| 1 | **peer70** 🏆 | Dev | Source of truth, instant test |
| 2 | **peer58** | Staging (sidecar) | Hot standby, mirrors peer70, low risk |
| 3 | **peer106** | Prod 1 | Test bed, fast verification |
| 4 | **peer105** | Prod 2 | Same arch as peer106, load test |
| 5 | **peer84** | Prod 3 | After 17:00 (cooling 11-17) |
| 6 | **peer128** | Prod 4 | macOS, sleep risk, last |

## Gate Tests (per-deploy, ~3 min)

| ID | Test | Method | Criterion |
|----|------|--------|-----------|
| A6 | Health | `GET :18644/health` | `status: "ok"`, `version: "2.0.0"` |
| A7 | Invalid JSON | `POST /send` with `"not-json"` | HTTP 400 |
| A8 | Missing fields | `POST /send` with no session_id or no text | HTTP 400 each |
| B1 | Send test | `POST /send {session_id, text}` ping | `status: "ok"`, `channel` non-null |
| Ping | Smoke | Verify `:18644` accepts and responds | Response within 60s |

A6-A8 check server reads requests correctly. B1 checks the LLM processing path.
If B1 falls back to `hmp_fallback` (no API session), that's acceptable for staging.

## Full Battery (peer58 staging only, ~15 min)

| Category | Tests | What they verify |
|----------|-------|------------------|
| **Unit** (A1-A8) | CRUD, Replace, peer_pair_id, env, arg, Health, JSON, Missing fields | Core logic correctness |
| **Session** (B1-B4) | Create, Reuse, Context, Different pairs | Session API + context preservation |
| **Fallback** (C1-C3) | No API, Both down, Timeout | Graceful degradation |
| **Concurrency** (D1-D3) | Same peer, Different peers, Same session | ThreadingHTTPServer safety |
| **Edge case** (E1-E7) | Long text, Unicode, Rapid fire, Empty, Unknown, DB persist, Idempotency | Boundary conditions |

## Rollback

```bash
# Rollback on a peer:
# 1. Switch symlink to previous version
ln -sf hmp_dual_plane.v1.x.x.py hmp_dual_plane.py

# 2. Kill current server
kill $(lsof -t -i :18644)

# 3. Restart with previous version
python3 -c "from hmp_dual_plane import run_server; run_server(port=18644, node_id='peerXX')"

# 4. Verify
curl http://127.0.0.1:18644/health

# 5. Run gate tests (A6, A7, A8, B1)
```

Backup session DB before deploy: `cp dual-plane.db dual-plane.db.bak`

## Protocol Manifest

```json
{
  "protocol": "hmp-dual-plane",
  "current_version": "2.0.0",
  "rollback_version": "1.0.0",
  "deploy_pipeline": {
    "order": ["peer70", "peer58", "peer106", "peer105", "peer84", "peer128"],
    "gate_tests": ["A6", "A7", "A8", "B1", "ping"],
    "full_battery": ["A1-A8", "B1-B4", "C1-C3", "D1-D3", "E1-E7"],
    "rollback": "symlink swap + kill + restart + verify"
  }
}
```
