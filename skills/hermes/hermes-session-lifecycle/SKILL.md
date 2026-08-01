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

## Pitfalls

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
