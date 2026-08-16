---
name: nous-portal-api
description: "Query Nous Portal account state programmatically — grant/credits spent, subscription, tool entitlement — via REST endpoint, Hermes wrapper, or x-nous-credits-* headers. Use for scripts, cron watchdogs, diagnostics."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [nous, portal, credits, grant, subscription, api, usage]
    related_skills: [hermes-agent, cron-operations]
---

# Nous Portal Account API

## When to use
- Need "grant spent", credits remaining, subscription plan, or tool-gateway entitlement for Nous Portal, programmatically (cron watchdog, script, diagnostics).
- The UI bubble ("Grant spent · $X top-up left", "⚠ Credits 90% used") is fed from the same data — a script can reproduce it.

## Three sources (wrapper → raw REST → live headers)

### 1. Packaged wrapper (preferred)
`hermes_cli/nous_account.py` (importable from the Hermes venv / source tree):
```python
from hermes_cli.nous_account import get_nous_portal_account_info
info = get_nous_portal_account_info(force_fresh=True)   # bypasses JWT fast-path + cache
info.subscription                       # NousPortalSubscriptionInfo
info.subscription.monthly_credits       # grant per period
info.subscription.credits_remaining
info.paid_service_access_info           # purchased_credits_remaining, total_usable_credits, member_spend_usd…
info.is_paid / .is_free_tier / .tool_gateway_entitled_for("firecrawl")
```
Default path decodes the OAuth JWT locally (fast, cached, no network); `force_fresh=True` calls the account API.

### 2. Raw REST (no Hermes imports — scripts, curl)
```
GET {portal_base_url}/api/oauth/account
Authorization: Bearer <access_token>
Accept: application/json
```
- base: `https://portal.nousresearch.com` (or `providers.nous.portal_base_url` in auth.json)
- Token: `~/.hermes/auth.json` → `providers.nous.access_token`
- Top-level response keys: `organisation, paid_service_access, purchased_credits_remaining, subscription, tool_access, user`
- `subscription`: plan, tier, monthly_charge, monthly_credits, current_period_end, credits_remaining, rollover_credits
- `paid_service_access`: subscription_credits_remaining, purchased_credits_remaining, total_usable_credits, member_spend_usd, has_active_subscription, …

### 3. Live response headers (what the bubble actually uses)
Every Nous inference response carries `x-nous-credits-*` headers: `-remaining-micros/-usd`, `-subscription-micros/-usd/-limit-*`, `-rollover-micros`, `-purchased-micros/-usd`, `-denominator-kind` (`subscription_cap`|`none`), `-paid-access` (STRING "true"/"false"), `-as-of-ms`. Tool-pool uses a separate `x-nous-tool-pool-*` prefix. Parsed by `parse_credits_headers()` in `agent/credits_tracker.py` → `CreditsState`; the "Grant spent" / usage-band `AgentNotice`s are generated in the same module (state kept per-session in `run_agent`, hydrated at session start via `seed_credits_at_session_start`).

## Semantics
- "Grant spent" = subscription cap exhausted (`credits_remaining` ≈ 0) while purchased top-up balance is live → notice `"• Grant spent · $X top-up left"` where X = top-up balance.
- Usage-band warnings ("⚠ Credits 90% used · $20.00 cap") are **suppressed** when purchased top-up > 0 — the cap gauge is the wrong denominator then.
- Depletion keys off `paid_access == false`, NOT `remaining == 0`.

## Pitfalls
- **auth.json shape**: top-level = `version, providers, active_provider, updated_at, credential_pool`. `providers.nous` is a plain dict (NOT a list, NOT `auth["nous"]`) with keys: access_token, refresh_token, client_id, portal_base_url, inference_base_url, agent_key, agent_key_expires_at, tls{insecure,ca_bundle}, …
- Money in headers is **micros ints** — parse with `int()` directly, never `int(float(…))` (float precision loss above 2^53). `*_usd` values are verbatim strings, never re-parsed.
- `credits_remaining` can be `-1e-22` (~0 / debt edge case) — use threshold comparisons (`<= 0.001`), not `== 0`.
- The account API is authoritative; the JWT fast-path may be stale (short cache) — use `force_fresh=True` when the answer matters.

## References
- `references/account-payload.md` — verified sample payload + field map + curl one-liner (Plus plan, Aug 2026).
