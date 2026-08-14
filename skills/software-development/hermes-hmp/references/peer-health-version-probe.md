# Peer health & version probe (HMP)

Quick multi-peer probe for "what version is everyone on" — run from peer70.

## One-liner per peer

```bash
for p in "peer70:127.0.0.1" "peer58:192.168.178.58" "peer106:192.168.178.106" "peer138:192.168.178.138" "peer141:192.168.178.141"; do
  name="${p%%:*}"; ip="${p##*:}"
  api=$(curl -s --connect-timeout 3 "http://$ip:8642/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo no-api)
  hmp=$(curl -s --connect-timeout 3 "http://$ip:18643/hmp/agent-card" | python3 -c "import sys,json; print('hmp '+str(json.load(sys.stdin).get('version','?')))" 2>/dev/null || echo no-hmp)
  echo "$name: hermes=$api | $hmp"
done
```

## Gotchas

- `/health` on :8642 returns `version` = Hermes CORE version.
  `/hmp/agent-card` returns `version` = the HMP **plugin** version (0.1.x) —
  NOT the core version. Don't confuse the two; a peer can run a new core and
  an old plugin (peer138/141 were on hmp 0.1.3 while peer58/70/106 were on
  0.1.4 — plugin and core are independent rollouts).
- Some peers don't expose :8642 (peer58 → no-api) or return `?` (peer106).
  Fall back to SSH:
  - `ssh fausto@<ip> 'cd ~/.hermes/hermes-agent && git describe --tags'` →
    tag-based version like `v2026.7.20` on some installs.
  - peer106 (Trixie, Fedora): SSH user is **root**, not fausto:
    `ssh root@192.168.178.106 'hermes --version'` → e.g. "Hermes Agent v0.15.1".
- Asking a peer directly over HMP: `POST http://<ip>:18643/hmp/send_and_wait`
  with `{"to": "<requester-peer>", "message": "...", "timeout": 60}`. The
  reply comes back in `response_text`. Allow ~30s — the peer's own agent
  round-trip is part of the latency. (A 30s wait is normal; the Telegram
  typing indicator stays on for the whole wait, which users may misread as
  a hang.)
- Registry (`~/.hermes/registry/registry.json`) `last_seen` tells you who is
  active before probing; peers offline for weeks (peer84 17/07, peer128 27/07
  in the 14/08 check) should be skipped.
