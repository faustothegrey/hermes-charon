# Observe-channel (🔍 custom bubble) — porting to newer Hermes cores (2026-08-14)

Analysis performed when Fausto asked whether the capability-reuse skill 2.4.18
could move to peer141 (Hermes 0.20.1) — and whether the "dangerous" core patch
had to go with it.

## The core question, answered

**NO — the custom bubble 🔍 (observe channel) is NOT upstream, and the plugin
does NOT need it to run.**

- `grep` of the capability-reuse / harness-feedback plugins for
  `get_pre_tool_call_feedback` / `tool.considered` → **zero references**. The
  plugins use only standard hooks (`pre_llm_call` / `pre_tool_call` /
  `post_tool_call`), which exist on every Hermes version.
- The core patch is **display-only**: it renders a 🔍 status line in the
  Telegram progress queue. All registry/retrieval/event logic works without it.
- Verified live: peer141 already runs plugin 2.4.18 with events flowing (4
  `2.4.18` events in `events.jsonl`) despite having NO core patch.

## What Hermes 0.20.1 has (peer141, verified on its checkout)

| Channel | 0.20.1 status |
|---|---|
| `pre_tool_call` hook | ✅ exists (`hermes_cli/plugins.py:157`) |
| Directive `block` / `approve` (+ `rule_key`) | ✅ full support, `_PreToolCallDirective` dataclass at `plugins.py:5788` |
| `get_pre_tool_call_block_message()` | ✅ exists at `plugins.py:5910` |
| `agent.tool_progress_callback` | ✅ exists (`agent/agent_init.py:797`) — rendering channel already there |
| **`observe` directive** | ❌ **silently discarded** — `plugins.py:5868`: `if action not in ("block", "approve"): continue` |
| `tool.considered` event | ❌ absent upstream — rendering branch is part of peer70's local patch |
| `get_pre_tool_call_feedback` collector | ❌ absent |

Key code (0.20.1):
```python
for result in hook_results:
    if not isinstance(result, dict):
        continue
    action = result.get("action")
    if action not in ("block", "approve"):
        continue   # ← "observe" dies here, silently, no error
```

## Consequences

- Skill 2.4.18 + plugin 2.4.18 deploy to any peer: **safe without core patch**.
  The only visible difference is missing 🔍 bubbles.
- The local patch (written against 0.17.0, files 3x smaller) does NOT apply to
  0.20.1 as-is — a port is a real diff, not a copy.
- Upstream's `_PreToolCallDirective` structure is cleaner than the local patch
  → the right porting path is a small upstream-style change (add `"observe"`
  to the allowed actions + a feedback collector + `tool.considered` render).

## peer141's porting constraints (asked via HMP, its own recommendation)

1. **(a)** `plugins.py:5910` — feedback sink on the SAME invoke single-fire
   (never fire the hook twice).
2. **(b)** `agent/tool_executor.py:958` — real gate (NOT the concurrent
   branch): sink → `tool_progress_callback('tool.considered', fb)`.
3. **(c)** `gateway/run.py` — `tool.considered` branch BEFORE `tool.started`
   → `'🔍 ' + fb`.
4. **(d)** plugin in `plugins.enabled` + gateway restart; **fail-open**;
   reviewable diff; Telegram smoke test.

Motivation (peer141): the bubble makes the retriever's **shadow decision
auditable at runtime** — evidence for empirical Phase 0 closure.

## Remote-core comparison technique (pitfall)

When checking whether a remote peer's core has a patch, `grep -c` is
ambiguous: it exits 1 BOTH for "file not found" AND "zero matches". Use:

```bash
if [ -f "$p" ]; then
  echo "$(grep -c 'marker' "$p" 2>/dev/null || echo 0) matches"
else
  echo "file absent"
fi
```

Also compare `wc -l` of the four core files peer70 vs remote — big line-count
gaps (e.g. `plugins.py` 2231 vs 6318) mean the patch target structure changed
and the diff must be re-derived, not copied.

## HMP reply truncation pattern

`/hmp/send_and_wait` truncates long peer answers (peer141's reasoned reply was
cut twice). Ask for a **compact format** ("max 500 chars, bullet form") to get
the full answer in one round.

## OUTCOME — port implemented by peer141 itself (same day, verified)

Fausto decided peer141 should implement the port on its OWN checkout (delegate
via HMP, not push a diff). Results:

- **Files changed** (peer141, 0.20.1): `plugins.py` +19 (feedback sink at
  :5815, observe branch at :5868 on the same single-fire invoke, fail-open,
  pass-through at :5907/:5934/:5961); `tool_executor.py` +11 (sink →
  `tool_progress_callback('tool.considered')` at :545, real non-concurrent
  gate at :569); `gateway/run.py` +8 (`tool.considered` branch BEFORE
  `tool.started` at :3953 → `'🔍 '+fb`). Plugin `harness-feedback` v0.1.0
  created; `HARNESS_FEEDBACK_MODE=dummy`. Smoke **5/5 PASS**.
- **In-band restart blocked**: peer141's gateway restart from inside its own
  gateway session is blocked by the same sandbox guard as peer70 — restart
  must come from an external shell (SSH script, pattern in hermes-hmp skill).
- **Config bug found after first restart**: `plugins.enabled` was written as
  a JSON string `'["hmp", "harness-feedback"]'` → NO plugin registered →
  HMP DOWN with `'hmp' is not a valid Platform` in logs (API :8642 still UP,
  masking it). Fixed to YAML list → HMP/API/Telegram all UP. Full pitfall:
  hermes-hmp `references/plugin-deploy-pitfalls-2026-08-13.md` §0b.
- **Delegation mechanics**: a full implement+test+restart round exceeds
  `send_and_wait` timeouts (300s). Message IS received and processed anyway
  (visible in peer's gateway.log); poll peer state via SSH and re-ask for a
  compact report afterwards. Peer may also reply with a `/busy` redirect
  notice if a run was in flight — just re-ask.
- **Verify plugin actually loaded**: `hermes plugins list` on the peer shows
  `harness-feedback enabled` — grep the gateway log for `tool.considered`
  is NOT a valid check (progress bubbles don't hit the log).
