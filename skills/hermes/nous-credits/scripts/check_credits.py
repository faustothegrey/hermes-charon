#!/usr/bin/env python3
"""check_credits.py — Nous Portal grant/top-up one-shot CLI.

Reads ~/.hermes/auth.json (defensively: providers.nous -> nous), calls the
Portal account API, prints a compact one-line summary. Exit 0 on success,
1 on auth/network errors. Safe for cron (no LLM).

Usage:
  python3 check_credits.py [--json]
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
AUTH_JSON = HERMES_HOME / "auth.json"
ACCOUNT_URL = "https://portal.nousresearch.com/api/oauth/account"


def load_token() -> str:
    if not AUTH_JSON.exists():
        sys.exit(f"ERROR: no auth file at {AUTH_JSON}")
    auth = json.loads(AUTH_JSON.read_text())
    nous = auth.get("providers", {}).get("nous") or auth.get("nous")
    if not nous:
        sys.exit("ERROR: no 'nous' provider in auth.json")
    tok = nous.get("access_token")
    if not tok:
        sys.exit("ERROR: no access_token for nous provider")
    return tok


def fetch_account(tok: str) -> dict:
    req = urllib.request.Request(
        ACCOUNT_URL,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR: account API {e.code} — token may need refresh (hermes auth)")
    except OSError as e:
        sys.exit(f"ERROR: network: {e}")


def main() -> None:
    tok = load_token()
    p = fetch_account(tok)
    sub = p.get("subscription") or {}
    acc = p.get("paid_service_access") or {}

    plan = sub.get("plan", "?")
    cap = sub.get("monthly_credits")
    remaining = sub.get("credits_remaining")
    topup = acc.get("purchased_credits_remaining")
    total = acc.get("total_usable_credits")

    def f(v, nd=2):
        return "n/a" if v is None else f"{v:.{nd}f}"

    spent = None if (cap is None or remaining is None) else cap - remaining

    if "--json" in sys.argv:
        print(json.dumps({
            "plan": plan,
            "monthly_credits": cap,
            "credits_remaining": remaining,
            "grant_spent": spent,
            "topup_remaining": topup,
            "total_usable": total,
            "period_end": sub.get("current_period_end"),
        }))
    else:
        print(f"{plan} | grant ${f(cap)} | remaining ${f(remaining)} | "
              f"spent ${f(spent)} | top-up ${f(topup)} | total ${f(total)}")


if __name__ == "__main__":
    main()
