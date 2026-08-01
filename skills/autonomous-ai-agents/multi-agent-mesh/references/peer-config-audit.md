# Peer Config Audit

Cross-peer Hermes config setting check-and-apply with multi-protocol fallback.

## When

You need to verify and optionally enforce a specific Hermes config setting
(e.g. `approvals.mode`, `model.default`, `plugins.enabled`) across every peer
in the mesh. Not just one — **all of them** unless the user says otherwise.

## Multi-Protocol Fallback Order

Try each protocol in order. Move to the next only when the current one
is unreachable or unresponsive.

```
1. HMP :18643         ← primary (fastest, agent processes the request)
2. API :8642          ← fallback (agent-prompt via chat completions)
3. SSH                ← maintenance (direct command or config edit)
```

### Protocol 1: HMP `:18643` (primary)

Send an HMP text message asking the peer to check + apply:

```bash
curl -s --connect-timeout 5 --max-time 15 -X POST \
  http://<peer-ip>:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text",
    "text": "Verifica il setting X. Se non è Y, impostalo a Y. Conferma il risultato.",
    "sender": "peer106"
  }'
```

Poll for response:

```bash
curl -s "http://<peer-ip>:18643/hmp/poll/<message_id>"
```

Status `delivering` → still processing. Wait 10-30s and retry.
Status `completed` → check `response_text` for the peer's answer.

### Protocol 2: API `:8642` (fallback)

When HMP is unreachable but the API server responds on `:8642`:

```bash
curl -s --connect-timeout 5 --max-time 90 -X POST \
  http://<peer-ip>:8642/v1/chat/completions \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "..."}],
    "max_tokens": 200
  }'
```

**Known issues with old API versions:**
- Hermes API v0.16.0 rejects `model` parameter even when it's provided
- `/v1/runs` endpoint may also fail if the peer's .env has no LLM API key
- When the agent engine fails (model errors), skip to SSH

### Protocol 3: SSH (maintenance)

When HMP and API both fail — or the `hermes` CLI binary isn't on PATH:

```bash
# If `hermes` CLI is available:
sshpass -p '<pw>' ssh user@<peer-ip> "hermes config get approvals.mode"
sshpass -p '<pw>' ssh user@<peer-ip> "hermes config set approvals.mode off"

# If `hermes` binary not on PATH, edit config.yaml directly:
sshpass -p '<pw>' ssh user@<peer-ip> "python3 -c \"
import yaml
c = yaml.safe_load(open('/home/fausto/.hermes/config.yaml'))
c['approvals'] = {'mode': 'off'}
yaml.dump(c, open('/home/fausto/.hermes/config.yaml', 'w'))
print('DONE')
\""
```

## Report Format

After contacting every peer, report results as a table:

| Peer | Method | Was | Now |
|------|--------|-----|-----|
| peer58 | HMP :18643 | `smart` | `off` ✅ |
| peer70 | HMP :18643 | `false` | confirmed `off` ✅ |
| peer84 | SSH (HMP/API down) | not set | `off` ✅ |
| peer128 | — | unreachable | ❌ |

## Critical Rule: Contact ALL Peers

When the user says "ask the other agents in the cluster", they mean
**every reachable peer**. Contacting only the first one is wrong.
Batch the sends in parallel where possible.

If multiple are unreachable, state explicitly which ones and why.
