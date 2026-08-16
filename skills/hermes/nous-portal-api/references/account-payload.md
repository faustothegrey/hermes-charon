# Verified /api/oauth/account payload — Plus plan (Aug 2026)

Live-verified against a real account on 2026-08-16. Field names here are
exactly what the endpoint returns and what `nous_account.py` maps them to.

## auth.json layout (where the token lives)

```json
{
  "version": 1,
  "providers": {
    "nous": {
      "access_token": "<jwt>",
      "refresh_token": "<rt>",
      "client_id": "<id>",
      "portal_base_url": "https://portal.nousresearch.com",
      "inference_base_url": "https://inference-api.nousresearch.com/v1",
      "token_type": "Bearer",
      "scope": "...",
      "obtained_at": "...",
      "expires_at": "...",
      "agent_key": "<key or null>",
      "agent_key_expires_at": "...",
      "agent_key_id": null,
      "agent_key_reused": false,
      "tls": { "insecure": false, "ca_bundle": null }
    }
  },
  "active_provider": "nous",
  "updated_at": "...",
  "credential_pool": { "nous": ... }
}
```

Path: `~/.hermes/auth.json` → `providers.nous.access_token` (plain dict — no
array index, no top-level `nous` key).

## Sample response

```json
{
  "organisation": { "id": "nas_organisation:...", "slug": "...", "name": "..." },
  "subscription": {
    "plan": "Plus",
    "tier": 2,
    "monthly_charge": 20,
    "monthly_credits": 22,
    "current_period_end": "2026-08-17T10:40:35.000Z",
    "credits_remaining": -1e-22,
    "rollover_credits": 0
  },
  "paid_service_access": {
    "allowed": true,
    "paid_access": true,
    "reason": "usable_credits",
    "organisation_id": "nas_organisation:...",
    "effective_at_ms": 1786860206968,
    "member_spend_cap_exceeded": false,
    "member_spend_cap_usd": null,
    "member_spend_usd": "26.359848035936",
    "member_spend_cap_remaining_usd": null,
    "has_active_subscription": true,
    "active_subscription_is_paid": true,
    "subscription_tier": 2,
    "subscription_monthly_charge": 20,
    "subscription_credits_remaining": -1e-22,
    "purchased_credits_remaining": 32.0836345329777,
    "total_usable_credits": 32.0836345329777
  },
  "purchased_credits_remaining": 32.0836345329777,
  "tool_access": null,
  "user": { "email": "...", "privy_did": "..." }
}
```

## Field map → Hermes dataclasses (`hermes_cli/nous_account.py`)

| API field | Dataclass field |
|---|---|
| `subscription.plan/tier/monthly_charge/monthly_credits/current_period_end/credits_remaining/rollover_credits` | `NousPortalSubscriptionInfo` (`.subscription`) |
| `paid_service_access.*` (allowed, paid_access, reason, organisation_id, effective_at_ms, has_active_subscription, active_subscription_is_paid, subscription_tier, subscription_monthly_charge, subscription_credits_remaining, purchased_credits_remaining, total_usable_credits) | `NousPaidServiceAccessInfo` (`.paid_service_access_info`) |
| `tool_access.{enabled, coverage{firecrawl, fal, ...}}` | `NousToolAccessInfo` (`.tool_access`) |
| `user.email`, `user.privy_did` | `.email`, `.privy_did` |

## Interpretation of the sample (grant spent case)

- Grant: $22/month (Plus, $20 charge + rollover 0) — fully consumed (`credits_remaining` ≈ 0, `-1e-22`).
- Top-up (purchased) balance: $32.08 — still live, funds everything.
- `total_usable_credits` == purchased when the subscription cap is exhausted.
- `member_spend_usd` ($26.36) > `monthly_charge` ($20) — overage covered by top-up.
- UI bubble rendered: `"• Grant spent · $32.08 top-up left"` (notice key `credits.grant_spent`, kind from `agent/credits_tracker.py`).

## Quick curl (no Hermes imports)

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.hermes/auth.json'))['providers']['nous']['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" \
  https://portal.nousresearch.com/api/oauth/account | python3 -m json.tool
```

Timeout: the Hermes fetcher uses 8s. Response is small (~1-2 KB).
