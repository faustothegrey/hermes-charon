# Cross-peer version probing (2026-08-14)

How to check the Hermes Agent version on all active peers, and how to ask a
peer a direct question over HMP. Validated against the Fausto network.

## Version sources per peer — probe order

The agent-card `version` field is the **HMP plugin** version (e.g. 0.1.4),
NOT the Hermes core version. To get the core version:

1. **API health** — `curl -s http://<ip>:8642/health` → `version` field.
   Not all peers expose it (peer58: no API at all; peer106: API answers but
   version field is `?`).
2. **HMP send_and_wait** — ask the peer directly (see below). Works on any
   peer with the HMP plugin; response ~30s.
3. **SSH fallback** — `git describe --tags` in the repo, or
   `hermes --version`:
   - peer58 (fausto@): `cd ~/.hermes/hermes-agent && git describe --tags`
     → `v2026.7.20`
   - peer106 (Trixie, Fedora): SSH user is **root** (not fausto), and the
     repo lives under `/root/.hermes/hermes-agent`; `hermes --version`
     → `Hermes Agent v0.15.1 (2026.5.29)`. `root@` worked, `fausto@` and
     `trixie@` were denied.
   - peer141 (Stella): SSH `fausto@` works (keys exchanged).

## Direct question over HMP (send_and_wait)

One HTTP call, synchronous reply in `response_text`:

```bash
curl -s --connect-timeout 5 -X POST http://<ip>:18643/hmp/send_and_wait \
  -H "Content-Type: application/json" \
  -d '{"to": "peer70", "message": "What version of the Hermes agent are you running? Reply with just the version string.", "timeout": 60}' \
  --max-time 70
```

- `"to"` = the peer the request is routed for (here peer70 = us; the peer
  answering is the one we address). Reply comes back in `response_text`.
- Set `timeout` and `--max-time` generously (peer141 took ~30s).
- For peer operations that need SSH/sudo/upnpc on the remote, the remote
  agent may wait for Fausto's approval → send_and_wait can time out; use it
  for read-only questions (version, status) only.

## Result snapshot (2026-08-14)

| Peer | Host | Hermes | HMP plugin | Source |
|---|---|---|---|---|
| peer70 | Charon (local) | 0.17.0 | 0.1.4 | API :8642 |
| peer58 | 192.168.178.58 | v2026.7.20 | 0.1.4 | SSH git describe |
| peer106 | Trixie (Fedora) | 0.15.1 | 0.1.4 | SSH root hermes --version |
| peer138 | 192.168.178.138 | 0.19.0 | 0.1.3 | API :8642 |
| peer141 | Stella (RPi) | 0.20.1 | 0.1.3 | HMP send_and_wait |

peer84 and peer128 were offline (last seen 17/07 and 27/07) — not probed.
