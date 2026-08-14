---
name: hermes-session-lifecycle
description: "Manage Hermes session context size and lifecycle: read real token usage, compression config, session_reset policies, and watchdog patterns for long-running gateway sessions."
version: 1.0.0
author: agent
created_by: agent
platforms: [linux, macos]
triggers:
  - session too large
  - session getting big
  - token warning
  - context compression
  - /new vs /compress
  - session reset
  - session watchdog
  - last_prompt_tokens
  - 243K session
  - telegram session stuck
metadata:
  hermes:
    tags: [hermes, sessions, compression, context, watchdog, gateway]
---

# Hermes Session Lifecycle & Context Size

How to manage long-running Hermes gateway sessions (Telegram, HMP) that
grow toward the model's context window — measuring real usage, tuning
auto-compression, and building pre-reset warnings. Covers the class of
problem that ends with "session stuck at 243K tokens, had to /new".

## Where the REAL context size lives

**`~/.hermes/sessions/sessions.json`** (gateway routing index) carries
`last_prompt_tokens` per session key. This is the size of the last
prompt actually sent to the API — i.e. the current context size. The
gateway updates it after every completed turn
(`gateway/session.py::update_session`, called from `gateway/run.py`
~line 10808 with `agent_result.get("last_prompt_tokens", 0)`).

**state.db is NOT the right source for "current size":**
- `sessions.input_tokens/output_tokens` are CUMULATIVE over the whole
  session (a 962-message session shows 26M input tokens) — useless for
  "how big is the context right now"
- `messages.token_count` is often NULL — don't rely on it

## Model context windows

`agent/model_metadata.py` holds the canonical per-model context length
(e.g. `deepseek-v4-flash: 1_000_000`, `deepseek: 128000` fallback).
Read it there before computing percentages. Note: the model's window is
1M but effective working context is what the provider serves — check
usage from sessions.json rather than assuming the window is fully usable.

## Compression config (`compression:` in config.yaml)

```yaml
compression:
  enabled: true
  threshold: 0.5        # compress when context hits 50% of window
  target_ratio: 0.2     # keep 20% of threshold tokens after compress
  protect_last_n: 20    # last N messages always preserved verbatim
  protect_first_n: 3    # first non-system head messages preserved
```

Compression is NOT a destructive renew: it summarises old context and
preserves the last N messages + system prompt. It triggers automatically
mid-turn near the threshold.

### Historical pitfall: compression silently failing on auxiliary model

A gateway session stuck at 243K tokens happened because the `auxiliary`
config pointed compression at `openrouter` with no API key — every
compress attempt failed silently, so the session just grew until the
model refused.

**Current status (fixed):** `config.yaml` has NO `auxiliary` section →
the compression model `(auto)` resolves via
`agent/auxiliary_client.py::_resolve_auto`, whose Step 1 is "user's
main provider + main model" (works for nous/DeepSeek OAuth). If a user
reports compression failing again, check for a stale `auxiliary` section
in config.yaml and REMOVE it (or point `auxiliary.compression.provider`
at a provider with valid credentials) — do not leave `auto` resolving to
a keyless provider.

**Verify without guessing:** `hermes config` shows the compression
section; the resolved model shows as `(auto)` when no explicit model is
set.

## session_reset policy — notify is POST, not PRE

`session_reset.mode`: `daily` (at_hour), `idle` (idle_minutes), `both`,
`none`. When a reset fires, the gateway sends the user a
"◐ Session automatically reset" message — but **only after** the reset
(`gateway/run.py`, `_was_auto_reset` block). There is NO native
pre-reset warning hook.

**Implication:** if the user wants "at least one warning before the
session renews", the only mechanism is a watchdog cron job that reads
sessions.json and alerts at a threshold below the compression point.

## Watchdog pattern (no_agent cron + script)

Session-size watchdog = classic `no_agent=true` watchdog:

- Script reads `~/.hermes/sessions/sessions.json`, finds the active
  platform session (`agent:main:<platform>:dm:<chat_id>`), reads
  `last_prompt_tokens`, compares to model window × threshold
- Empty stdout = silent (nothing delivered); non-empty stdout =
  delivered verbatim to the job's target
- Schedule `every 30m` is fine — the gateway updates sessions.json on
  every turn so data is fresh enough

Working implementation with the exact script, threshold math, and test
recipe: `references/session-watchdog.md`.

## Pruning old sessions (`hermes sessions prune`)

When state.db grows huge (1GB+), prune sessions older than N days:

```bash
hermes sessions prune --older-than 7 --yes
```

**Pitfalls learned the hard way:**

- **It is SLOW on big DBs.** A 1.2GB / 12K-session / 192K-message DB took ~18
  minutes at 600MHz CPU (RPi). The default 300s foreground timeout KILLS it —
  always run in background: `terminal(background=true, notify_on_complete=true)`.
- **Progress is invisible for most of the run.** Deletes land in the WAL
  (watch it grow to 500MB+) and the sessions/messages COUNT stays unchanged
  until late in the run. Don't conclude "stuck" — check `state.db-wal` size
  and the process %CPU instead of counting rows.
- **`prune` does NOT shrink the file.** SQLite keeps freed pages; a 1.2GB DB
  stays 1.2GB until you run `VACUUM`. After pruning always:
  ```python
  import sqlite3; con = sqlite3.connect("~/.hermes/state.db", timeout=60)
  con.execute("VACUUM"); con.commit()
  ```
  (also background it — VACUUM on 1GB+ takes minutes). Real result: 1.18GB → 583MB.
- **Active/protected sessions survive the prune** (in-use or locked ones
  remain even if older than the cutoff) — that's expected, not a failure.
- Query before pruning to preview impact:
  ```python
  SELECT COUNT(*), SUM(message_count) FROM sessions WHERE started_at < <cutoff_ts>
  ```
- Cron pattern: offer a monthly auto-prune cron (`no_agent=true`,
  `deliver=local`) with the script wrapping prune + VACUUM.

## Pitfalls

- **Stale "typing" indicator on Telegram ≠ session too big.** A user
  reporting "still typing for minutes" looks like the classic oversized-
  session symptom, but check `last_prompt_tokens` (sessions.json) FIRST and
  the gateway log response times. If responses ARE delivered on time, the
  indicator is a rendering artifact: custom progress bubbles (e.g.
  capability-reuse's 🔍 `tool.considered` events) make the progress consumer
  call `adapter.send_typing()` after EVERY bubble edit, and Telegram has no
  stop-typing API — the ~5s timer keeps getting re-armed, so the bubble
  lingers as long as the queue drains (minutes of stale "typing" after the
  reply was already delivered). Fix (gateway/run.py, commit `5bb34a7`):
  guard BOTH restore-typing call sites with
  `_run_still_current() and not progress_queue.empty()` so the timer expires
  once the turn's bubbles are drained. Verification: `grep "response ready"`
  in gateway.log shows normal per-turn times the whole time.
- **Cron `script` field is a bare filename**, not a path: it must exist
  in `~/.hermes/scripts/`. Passing `/home/fausto/.hermes/scripts/foo.py`
  is rejected by `cronjob(action=create)` — use `foo.py`.
- **Testing scripts that read a module-level constant:** when using
  `importlib` to stub `SESSIONS_JSON` (or any module constant) for a
  test, `spec.loader.exec_module()` re-executes the module body and
  OVERWRITES your override. Set the attribute AFTER `exec_module`, not
  before.
- **Sessions.json vs state.db confusion** — always use
  `last_prompt_tokens` from sessions.json for "current context size";
  cumulative counters in state.db mislead.
- **Compression threshold is relative to the model window**, not to
  "90 turns" or message count — a 70% watchdog threshold + 50%
  compression threshold means compression always fires first.
- User preference: when asked "can we auto-clean the session", the
  answer is compression (already on) + watchdog for the pre-warning;
  don't propose changing auxiliary provider config unless the auxiliary
  section actually exists and is broken.
- **"Still typing…" on Telegram for minutes = stale typing re-arm, NOT a
  session-size problem.** Symptom: user reports the typing indicator lingers
  long after the reply arrived (gateway.log shows "response ready … Sending
  response" while the user still sees typing). First rule out size via
  `last_prompt_tokens` from sessions.json (this is almost always fine), then
  suspect the gateway progress consumer: it re-arms Telegram's ~5s typing
  timer via `adapter.send_typing` after EVERY progress-bubble edit, including
  the last one of a turn — and Telegram exposes no stop-typing API (issue
  #48678), so nothing cancels the indicator. The custom 🔍 `tool.considered`
  bubbles (capability-reuse harness feedback) emit one event per tool call,
  keeping the progress queue non-empty and the indicator alive for minutes
  after the final answer. Fix (gateway/run.py, 2026-08-14): guard both
  restore-typing call sites with `_run_still_current() and not
  progress_queue.empty()` so the timer naturally expires once the turn's
  bubbles are drained. During diagnosis, a long `send_and_wait` to a peer
  (~30s) also keeps the indicator on for the whole wait — that's normal
  turn duration, not a block.

## Pitfall: Telegram stuck "typing…" indicator — NOT a session problem

**Symptom:** user reports the bot shows "typing…" for minutes (even
>2 min) and worries the session file is too big / stuck (it was a real
session problem once — 243K tokens with silently-broken compression).
This time it is almost always a **cosmetic Telegram platform bug**, and
responses ARE being delivered.

**Root cause (verified 2026-08-14, v0.17.0):** Hermes runs a
`_keep_typing` refresh loop (`gateway/platforms/base.py` ~line 3526)
that re-sends `sendChatAction(typing)` every ~2s because Telegram's
typing bubble self-expires after ~5s. At end of turn the gateway calls
`adapter.stop_typing(chat_id)` (`gateway/run.py` ~line 10363), but
`BasePlatformAdapter.stop_typing` (`base.py` ~line 2985) is a **no-op**
(`pass` — "Override in subclasses that start background typing loops").
Discord/Slack/Matrix/Google Chat/Photon all override it; **the Telegram
adapter (`plugins/platforms/telegram/adapter.py`) does NOT** — so the
loop keeps re-arming Telegram's ~5s timer and the bubble never dies.
Code comments reference upstream issue #48678; the adapter explicitly
avoids re-triggering typing on the final reply (`metadata["notify"]`)
for exactly this reason.

**Diagnosis order (rule out session first, cheap → deep):**
1. `~/.hermes/sessions/sessions.json` → `last_prompt_tokens` for the
   session key vs model window (compression 50%, watchdog 70%). ~10%
   of window = session fine, stop blaming the session.
2. `tail ~/.hermes/logs/gateway.log` → look for
   `response ready: platform=telegram ... time=..s` lines. If responses
   are being sent, nothing is blocked — it's the bubble only.
3. Confirm the code path: grep `def stop_typing` in
   `plugins/platforms/telegram/adapter.py` → absent = confirmed.

**Fix location (if ever implemented):** add
`async def stop_typing(self, chat_id)` to `TelegramAdapter` that cancels
the `_keep_typing` task, mirroring the `_typing_tasks` dict pattern in
`plugins/platforms/discord/adapter.py` (~line 784, 3382-3422).

**Do NOT** restart the gateway for this — restart is manual (per
operating memory) and doesn't fix the no-op. Also note: a slow
`/hmp/send_and_wait` to a peer (30s+ response) legitimately keeps the
typing bubble on for the whole wait — that's normal turn time, not a
hang.
