# Session Size Watchdog — Working Implementation

Deployed 2026-07-31 on peer70 (Telegram DM, deepseek-v4-flash via nous,
1M context window). Cron job `session-watchdog-70pct` (`every 30m`,
`no_agent=true`, `deliver=origin`, `script=session_watchdog.py`).

## The script: `~/.hermes/scripts/session_watchdog.py`

```python
#!/usr/bin/env python3
"""Session size watchdog — alerts on Telegram when the active session
exceeds the configured threshold (default 70% of context window).

Watchdog contract: empty stdout = silence; non-empty stdout = delivered
verbatim to the cron job's delivery target (no_agent=true).

Data source: ~/.hermes/sessions/sessions.json → last_prompt_tokens
(updated by the gateway after every turn = real last prompt size).
"""
import json
import os

SESSIONS_JSON = os.path.expanduser("~/.hermes/sessions/sessions.json")
THRESHOLD = 0.70
CONTEXT_LENGTH = 1_000_000  # deepseek-v4-flash (1M window); adjust per model


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def main() -> None:
    try:
        with open(SESSIONS_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"⚠️ Watchdog sessione: impossibile leggere {SESSIONS_JSON}: {exc}")
        return

    # Active platform sessions (DM + topics)
    candidates = {
        k: v for k, v in data.items()
        if k.startswith("agent:main:telegram:")
        and isinstance(v, dict)
        and v.get("session_id")
    }
    if not candidates:
        return  # no active telegram session → silence

    # Most recent session = the one the user is talking to right now
    entry = max(candidates.values(), key=lambda v: v.get("updated_at", ""))
    sid = entry.get("session_id", "?")
    tokens = int(entry.get("last_prompt_tokens") or 0)
    pct = (tokens / CONTEXT_LENGTH) * 100

    if pct >= THRESHOLD * 100:
        print(
            f"⚠️ Sessione Telegram vicina al limite\n"
            f"• Contesto: {_fmt_tokens(tokens)} / {_fmt_tokens(CONTEXT_LENGTH)} token "
            f"({pct:.0f}%)\n"
            f"• Soglia warning: {THRESHOLD:.0%} — compressione automatica: 50%\n"
            f"• Consiglio: /compress ora, oppure /new per ripartire pulito\n"
            f"• Sessione: {sid}"
        )
    # below threshold → no output (silence)


if __name__ == "__main__":
    main()
```

## Cron job creation

```python
cronjob(
    action="create",
    name="session-watchdog-70pct",
    schedule="every 30m",
    deliver="origin",          # back to the originating chat
    no_agent=True,             # zero-LLM watchdog
    script="session_watchdog.py",   # bare filename, NOT a path!
    prompt="Watchdog dimensione sessione Telegram (70%)",  # ignored when no_agent=True
)
```

**Pitfall hit live:** passing the absolute path
`/home/fausto/.hermes/scripts/session_watchdog.py` to `script=` is
REJECTED — "Script path must be relative to ~/.hermes/scripts/".
Use just the filename.

Verify with `cronjob(action='run', job_id=...)` → expect
`last_status: ok`, `execution_success: true`. Output stays silent
while under threshold (correct watchdog behavior).

## Testing the script (importlib override ordering)

The script reads a module-level `SESSIONS_JSON`. To point it at a test
file, the override MUST be set AFTER `exec_module()` — the module body
re-executes and clobbers any pre-set value:

```python
import importlib.util

spec = importlib.util.spec_from_file_location("sw", "session_watchdog.py")
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)          # runs module body → SESSIONS_JSON reset
sw.SESSIONS_JSON = "/tmp/sessions_test.json"   # override AFTER exec
sw.main()
```

Test matrix used:
- Real sessions.json (currently ~2% used) → empty output, exit 0
- Simulated `last_prompt_tokens: 750000` (75%) → warning message with
  token count, percentage, advice, session id

## Tuning notes

- `CONTEXT_LENGTH` must match the model actually serving the session
  (see `agent/model_metadata.py`). deepseek-v4-flash = 1M.
- Threshold 70% sits above the 50% compression threshold: compression
  always fires first, the watchdog is the safety net for dense
  tool-call-heavy conversations where compression alone isn't enough.
- If the user switches models, update CONTEXT_LENGTH (and re-verify the
  compression threshold is still below the watchdog threshold).
