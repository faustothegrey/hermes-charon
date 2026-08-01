# Gateway "Stuck" Diagnosis — Session Bloat + Auxiliary Compression Block

Diagnostic chain for a Hermes gateway (Telegram/CLI) that appears stuck:
stops responding to messages, then resumes after a manual restart.
Verified twice on peer70 (2026-07-29 and 2026-07-31).

## Symptom

- User sends a message; the gateway does not reply for many minutes.
- Manual restart (`kill -9` or user action) fixes it temporarily.
- After restart, the SAME queued message takes 100-140s with 10-12 API
  calls to answer a trivial question.

## Diagnostic Chain (in order)

### 1. gateway.log — look at response times and API call counts

```bash
tail -40 ~/.hermes/logs/gateway.log
```

Key line after a stuck episode:

```
response ready: platform=telegram chat=8508115936 time=138.4s api_calls=12 response=548 chars
```

A short response taking 130+s with 10+ API calls = the agent is grinding
through a huge context, not stuck on the network.

### 2. agent.log — check input tokens per API call

```bash
grep "API call" ~/.hermes/logs/agent.log | tail -5
```

```text
API call #12: model=deepseek/deepseek-v4-flash in=243445 out=396 ...
```

`in=243445` means the full live context is ~243K tokens PER CALL. Each
call costs ~10s → 12 calls = 138s per turn. The gateway processes one
message at a time per session, so everything else queues behind it and
the gateway appears dead.

### 3. state.db — find the bloated session

```python
import sqlite3, os
conn = sqlite3.connect(os.path.expanduser("~/.hermes/state.db"))
cur = conn.cursor()
cur.execute("""SELECT id, title, source, message_count, input_tokens, ended_at
               FROM sessions WHERE ended_at IS NULL
               ORDER BY input_tokens DESC LIMIT 5""")
for r in cur.fetchall():
    print(r)
```

A session with `input_tokens` in the tens of millions (cumulative) and a
`started_at` weeks old is the culprit. On peer70: session
`20260629_113713_541684fc` (Telegram DM, opened June 29) had 942
messages, 26.2M accumulated input tokens, 1,575 API calls — never ended.

### 4. errors.log — check the auxiliary model

```bash
grep -i auxiliary ~/.hermes/logs/errors.log | tail -5
```

```text
WARNING agent.auxiliary_client: Auxiliary: marking openrouter unhealthy
for 60s (payment / credit error)
```

**Root cause of the bloat:** context compression uses the *auxiliary*
LLM. If the auxiliary provider is misconfigured (e.g. `auto` resolves to
OpenRouter but `OPENROUTER_API_KEY` is commented out in `~/.hermes/.env`),
compression silently fails → the session context grows unbounded → 243K
tokens → every turn slow → gateway appears stuck.

## Fixes

1. **Immediate:** start a fresh session (`/new` on Telegram, or new
   session id) — resets context to near zero instantly.
2. **Permanent:** point auxiliary tasks at the main provider instead of
   the broken default:
   ```bash
   hermes config set auxiliary.compression.provider nous
   hermes config set auxiliary.vision.provider nous
   # check main provider: grep -A3 '^model:' ~/.hermes/config.yaml
   ```
   (config changes need a gateway restart — use the cron one-shot
   technique from the SKILL.md gateway-restart section).

## Prevention

- Periodically check for month-old active sessions:
  ```python
  cur.execute("SELECT id, input_tokens FROM sessions WHERE ended_at IS NULL ORDER BY started_at")
  ```
- Archive or `/new` long-lived DM sessions before they reach ~100K live
  tokens.
- Verify compression actually runs: after a heavy session, `SELECT
  COUNT(*) FROM messages WHERE compacted=1` should grow, and `in=`
  token counts in agent.log should drop after compression triggers.
