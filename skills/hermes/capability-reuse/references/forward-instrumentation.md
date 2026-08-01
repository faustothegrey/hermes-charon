# Forward Instrumentation Pattern

Non-blocking event collection for Hermes agent behavior analysis. Used in Capability Reuse Phase 0.3.

## Principle

Wrap a tool call to capture request, code, and outcome events *without* altering behavior. The wrapper is:
- **Non-blocking**: file I/O errors are silently caught — never interfere with execution
- **Append-only**: JSONL format, never mutates past events
- **Kill-switched**: env var `HERMES_OBSERVER_DISABLE=1` disables entirely
- **Zero dependencies**: standard library only (`json`, `os`, `uuid`, `pathlib`)

## Architecture

```
before_call:
  capture context (session_id, episode_id, last_user_request)
  fingerprint code (imports, tool calls, URLs, operation patterns)
  emit execute_code_started event

after_call:
  emit execute_code_completed event (outcome, duration_ms, error)
```

## Fingerprint Types

| Type | Extracts | Use |
|------|----------|-----|
| **Syntax** | Imports, tool calls (`terminal()`, `read_file()`, `web_search()`), URL patterns | Identify operation class |
| **Pattern** | Curl, subprocess, JSON, SSH, HMP, cron, broadcast detection | Recurrence clustering |
| **Effect** | Observation source + confidence, `unknown` for unobservable | Effect classification |

## Event Log Format (JSONL)

```jsonl
{"event_id":"a1b2c3","event_type":"execute_code_started","schema_version":"1.0","timestamp":"...","seq":1,"data":{...}}
{"event_id":"d4e5f6","event_type":"execute_code_completed","schema_version":"1.0","timestamp":"...","seq":2,"data":{...}}
```

## Output Location

`~/.hermes/data/reuse-observer/events.jsonl`

## Kill Switch

```bash
export HERMES_OBSERVER_DISABLE=1
```

## Revert

```bash
rm -rf ~/.hermes/data/reuse-observer/
rm ~/.hermes/scripts/execute_code_observer.py
```
