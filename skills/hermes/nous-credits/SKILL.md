---
name: nous-credits
type: custom
version: 1.0.0
phase: "1"
description: "Use when you need Nous Portal grant/credits data programmatically — subscription cap spent, top-up (purchased) balance, rollover, total usable credits — via the account API, the packaged Hermes helper, or live response headers. Versioned and published in the Local Skill registry (peer70)."
author: peer70 (Fausto)
status: active
license: MIT
changelog:
  - "1.0.0 — initial release: account API endpoint, packaged get_nous_portal_account_info(), x-nous-credits-* live headers, check_credits.py helper, registry registration."
---

# Nous Credits (grant spent / top-up)

## Overview

Reads Nous Portal **grant** data: the subscription monthly cap, how much of it is spent, the top-up (purchased) balance, rollover credits, and total usable credits. This is the data behind the "Grant spent · $X top-up left" bubble Hermes shows.

Three sources, from most authoritative to freshest:

| # | Source | What it gives | Freshness |
|---|--------|---------------|-----------|
| 1 | Portal account API (`/api/oauth/account`) | plan, monthly credits, remaining, rollover, purchased, total usable | On demand, ~1 HTTP call |
| 2 | Packaged Hermes helper `get_nous_portal_account_info(force_fresh=True)` | Same data as dataclass fields | Same (wraps #1) |
| 3 | Live `x-nous-credits-*` response headers | Exact per-response balance snapshot | Every inference call (what the bubble uses) |

Money is USD. The API returns floats (dollars); the live headers return micros (ints) + formatted USD strings.

## When to Use

- User asks "how much grant is left / spent?" on a Nous Portal account
- Building a credits watchdog / alert (e.g. cron that warns when subscription cap is exhausted and top-up is running low)
- Verifying the "Grant spent" bubble numbers programmatically
- Any agent (peer) in the mesh that needs the same data without guessing at auth.json layout

**Don't use for:** non-Nous providers (OpenRouter, Anthropic, etc.) — the API and headers are Nous-specific. For token usage of past sessions use `hermes insights` instead.

## Auth token location

The OAuth access token lives in `~/.hermes/auth.json` (or `$HERMES_HOME/auth.json`):

```json
{
  "providers": {
    "nous": {
      "access_token": "...",
      "portal_base_url": "https://portal.nousresearch.com",
      "inference_base_url": "https://inference-api.nousresearch.com/v1"
    }
  }
}
```

⚠️ Layout varies by Hermes version — older installs used a flat `nous` key, newer ones nest under `providers.nous`. Parse defensively: try `providers.nous`, then top-level `nous`. The token can also be rotated at any time, so always re-read the file, never cache it long-term.

## Source 1 — raw REST (no Hermes imports)

```python
import json, urllib.request

auth = json.load(open("/home/fausto/.hermes/auth.json"))
nous = auth.get("providers", {}).get("nous") or auth.get("nous")
tok = nous["access_token"]

req = urllib.request.Request(
    "https://portal.nousresearch.com/api/oauth/account",
    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"},
)
with urllib.request.urlopen(req, timeout=8) as r:
    p = json.loads(r.read().decode())
```

Key fields in the response:

| Field path | Meaning |
|------------|---------|
| `subscription.plan` / `.tier` | Plan name / tier (e.g. Plus / 2) |
| `subscription.monthly_credits` | Monthly grant cap (USD) |
| `subscription.credits_remaining` | Grant remaining (≈0 or negative → spent) |
| `subscription.rollover_credits` | Rollover from previous periods |
| `subscription.current_period_end` | Billing period end (ISO) |
| `paid_service_access.subscription_credits_remaining` | Same as credits_remaining |
| `paid_service_access.purchased_credits_remaining` | **Top-up balance (USD)** — the "top-up left" number |
| `paid_service_access.total_usable_credits` | grant remaining + rollover + purchased |
| `paid_service_access.member_spend_usd` | Cumulative member spend this period |

**Grant spent** = `monthly_credits - credits_remaining` (when credits_remaining ≤ 0, the grant is fully spent and you're on top-up).

## Source 2 — packaged helper

Same endpoint, normalized dataclass, handles auth layout + cache:

```python
import sys
sys.path.insert(0, "/home/fausto/.hermes/hermes-agent")
from hermes_cli.nous_account import get_nous_portal_account_info

info = get_nous_portal_account_info(force_fresh=True)
sub = info.subscription                     # NousPortalSubscriptionInfo
acc = info.paid_service_access_info         # NousPaidServiceAccessInfo
print(sub.monthly_credits, sub.credits_remaining)      # 22.0, ~0.0
print(acc.purchased_credits_remaining)                  # 32.08
print(acc.total_usable_credits)                          # 32.08
```

- `force_fresh=True` skips the JWT/cache path and always hits the API
- Default path decodes the OAuth JWT locally (fast, but no balance fields)
- On non-Nous setups it returns `logged_in=False` — check `info.logged_in` first

## Source 3 — live headers (what the bubble uses)

Every Nous inference response carries `x-nous-credits-*` headers. Parsed by `agent/credits_tracker.py` into a `CreditsState`:

| Header | Meaning |
|--------|---------|
| `x-nous-credits-remaining-micros` / `-usd` | Total remaining balance |
| `x-nous-credits-subscription-micros` / `-limit-micros` | Subscription balance / cap |
| `x-nous-credits-purchased-micros` / `-usd` | **Top-up balance** |
| `x-nous-credits-rollover-micros` | Rollover |
| `x-nous-credits-denominator-kind` | `subscription_cap` or `none` |
| `x-nous-credits-paid-access` | `"true"` / `"false"` (string!) |

```python
from agent.credits_tracker import parse_credits_headers
state = parse_credits_headers(dict_of_response_headers)
print(state.purchased_usd, state.subscription_limit_usd)
```

Use micros as ints (money-safe); never float-convert large values.

## Helper script

`scripts/check_credits.py` — one-shot CLI: reads auth.json, calls the account API, prints a compact summary (plan, grant cap, remaining, spent, top-up, total usable). Safe to run from cron (no LLM, no tokens consumed).

```bash
python3 ~/.hermes/skills/hermes/nous-credits/scripts/check_credits.py
# Plus | grant $22.00 | remaining $0.00 | spent $22.00 | top-up $32.08 | total $32.08
```

## Common Pitfalls

1. **Wrong auth.json layout** — newer Hermes nests under `providers.nous`, older uses top-level `nous`. Always parse defensively (both), never hardcode one.
2. **Token expiry** — OAuth tokens rotate. If the API returns 401, the token needs refresh; re-run `hermes portal info` / `hermes auth` to re-auth. The account API call itself does NOT auto-refresh.
3. **`credits_remaining` ≈ 0 but `paid_access: true`** — that's normal: grant spent, top-up covering usage. Don't alert on "0 remaining" alone; alert on `purchased_credits_remaining` crossing a floor.
4. **Treating micros as dollars** — headers use micros (1 USD = 1e6 micros); `parse_credits_headers` keeps them as ints. Convert only for display.
5. **Hardcoding `~/.hermes/hermes-agent` for the packaged helper** — path differs per install; prefer the raw REST call (Source 1) when the skill must run on unknown peers, or detect the repo path.

## Verification Checklist

- [ ] `auth.json` parsed defensively (`providers.nous` → fallback `nous`)
- [ ] Account API returns 200 and `subscription.monthly_credits` is a number
- [ ] `grant spent = monthly_credits - credits_remaining` computed correctly (floats)
- [ ] Top-up read from `paid_service_access.purchased_credits_remaining`, not subscription
- [ ] Script exits non-zero + clear message on 401 / network error (no silent pass)
- [ ] Version bumped in frontmatter + `changelog` entry when content changes
