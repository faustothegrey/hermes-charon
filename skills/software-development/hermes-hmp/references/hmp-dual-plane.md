# HMP Dual-Plane Protocol v2.0.0 — Reference

## Architecture (Server-Side)

Every peer exposes `:18644` accepting `POST /send {"session_id", "text"}`.
The server-side harness handles everything internally. The client makes ONE call.

### Full Version (Hermes Agent peers: peer70, peer106, peer58, peer105, peer84)

1. `get_or_create_session()` — cache SQLite, GET /api/sessions, POST /api/sessions
2. `POST /v1/chat/completions` with session_id — agent context preserved
3. Fallback to HMP :18643 if API unavailable

### Light Version (Pi Agent / no Hermes: peer136)

1. `ContextStore` — in-memory dict session_id → [messages]
2. `LLMInterface` — HMP loopback (:18643/hmp/send + poll) or direct LLM URL
3. Same HTTP API on `:18644`

### Code Inheritance

`hmp_dual_plane_light.py` (BASE): ContextStore, LLMInterface, LightDualPlaneServer, run_server
`hmp_dual_plane.py` (FULL, extends light): SessionStore(SQLite), HermesLLM(:8642), DualPlaneServer

## Usage

Server: `from hmp_dual_plane import run_server; run_server(port=18644, node_id='peer70')`
Client: `from hmp_dual_plane import send_to_peer; resp = send_to_peer("peer106", "Ciao!")`

## Key vs v1

| v1 (client-side) | v2 (server-side) |
|------------------|-------------------|
| Logic on peer70 | Logic on each peer |
| 3 calls per msg | 1 call per msg |
| HMP notify needed | Synchronous |
| Remote session mgmt | Local session mgmt |
