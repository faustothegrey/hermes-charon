#!/usr/bin/env python3
"""Verify protocol.py: import, state machine, fallback token, unclean continuation."""
import sys, json, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/hermes/capability-reuse/plugin"))
from protocol import (
    InterventionStore, Verdict, invoke_schema, get_store_stats
)
from protocol import _store as store

errors = []; passes = 0
def check(name, ok, detail=""):
    global passes, errors
    if ok: passes += 1; print(f"  ✅ {name}")
    else: errors.append((name, detail)); print(f"  ❌ {name}: {detail}")

s = invoke_schema()
check("invoke_schema() returns dict", isinstance(s, dict) and "properties" in s)
v = Verdict(allowed=False, message="test")
check("Verdict(allowed=False)", not v.allowed)
check("Store exists", store is not None)

store.create_intervention("int_001","ep_001","hmp-healthcheck","1.0.0")
inv = store.get_intervention("int_001")
check("Intervention created", inv and inv["state"] == "open")

ok = store.claim_intervention("int_001","capability","inv_001")
check("First claim succeeds", ok)
ok = store.claim_intervention("int_001","bypass","tc_001")
check("Second claim fails (atomic)", not ok)
inv = store.get_intervention("int_001")
check("State = claimed_by_capability", inv["state"] == "claimed_by_capability")

store.create_intervention("int_002","ep_001","peer-heartbeat","1.0.0")
ok = store.claim_intervention("int_002","bypass","tc_002")
check("Bypass claim succeeds", ok)
inv = store.get_intervention("int_002")
check("State = claimed_by_bypass", inv["state"] == "claimed_by_bypass")

store.create_intervention("int_003","ep_001","hmp-send","1.0.0")
store.claim_intervention("int_003","capability","inv_003")
tid = store.issue_fallback_token("int_003","inv_003","timeout")
check("Fallback token issued", tid and str(tid).startswith("fbt_"))
inv = store.get_intervention("int_003")
check("State = fallback_authorized", inv["state"] == "fallback_authorized")

ok = store.consume_fallback_token(tid,"tc_003")
check("Fallback token consumed", ok)
inv = store.get_intervention("int_003")
check("State = fallback_consumed", inv["state"] == "fallback_consumed")

ok = store.consume_fallback_token(tid,"tc_003b")
check("Second consume fails", not ok)

store.create_intervention("int_004","ep_001","hmp-healthcheck","1.0.0")
store.claim_intervention("int_004","capability","inv_004")
store.transition("int_004","failed_unclean_read_only",failure_code="invalid_response")
ok = store.record_unclean_continuation("int_004","inv_004","invalid_response","tc_004")
check("Unclean continuation recorded", ok)
inv = store.get_intervention("int_004")
check("State = unclean_fallback_recorded", inv["state"] == "unclean_fallback_recorded")
ok = store.record_unclean_continuation("int_004","inv_004","invalid_response","tc_004b")
check("Second unclean fails", not ok)

store.create_intervention("int_005","ep_001","hmp-send","1.0.0")
store.claim_intervention("int_005","capability","inv_005")
tid2 = store.issue_fallback_token("int_005","inv_005","timeout",ttl=0)
import time; time.sleep(0.01)
ok = store.consume_fallback_token(tid2,"tc_005")
check("Expired token fails", not ok)
inv = store.get_intervention("int_005")
check("State = fallback_expired on TTL", inv["state"] == "fallback_expired")

stats = get_store_stats()
check("Stats returns dict", isinstance(stats, dict))
check("Stats.count >= 5", stats["total_interventions"] >= 5)

print(f"\n{'='*50}")
print(f"{passes}/{passes+len(errors)} tests passed")
sys.exit(0 if len(errors)==0 else 1)