#!/usr/bin/env python3
"""Run a narrow Phase 1B active canary burn-in for hmp-healthcheck.

Default target is peer128. The script exercises positive prompts, negative prompts,
clean fallback, unclean continuation, and event-chain correlation. It is intended
for capability-reuse validation after protocol/retriever/dispatcher changes.

Usage:
  python3 scripts/active-canary-burnin.py [peer128]
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PEER = sys.argv[1] if len(sys.argv) > 1 else "peer128"

os.environ["CAPABILITY_REUSE_MODE"] = "active"
os.environ["CAPABILITY_REUSE_ACTIVE_CAPABILITIES"] = "hmp-healthcheck"
os.environ["CAPABILITY_REUSE_PERMISSIONS"] = "hmp.network.read"
os.environ["CAPABILITY_REUSE_AVAILABLE_CAPABILITIES"] = "hmp_client_installed"
os.environ.setdefault("CAPABILITY_REUSE_INTERVENTION_THRESHOLD", "0.65")
os.environ.setdefault("CAPABILITY_REUSE_MINIMUM_MARGIN", "0.10")

protocol = importlib.reload(importlib.import_module("plugin.protocol"))
dispatcher = importlib.reload(importlib.import_module("plugin.dispatcher"))
events_mod = importlib.reload(importlib.import_module("plugin.event_store"))
protocol._store = protocol.InterventionStore()

run_id = "%s-burnin-%d" % (PEER, int(time.time()))
positive_prompts = [
    "check HMP health for %s" % PEER,
    "ping HMP status for %s" % PEER,
    "show %s HMP gateway health" % PEER,
    "verify %s hmp health endpoint" % PEER,
    "healthcheck %s via HMP" % PEER,
]
negative_prompts = [
    "send a message to %s" % PEER,
    "deploy plugin to %s" % PEER,
    "restart HMP on %s" % PEER,
    "ssh to %s and run uptime" % PEER,
    "copy registry to %s" % PEER,
]
report = {
    "run_id": run_id,
    "scope": {
        "peer": PEER,
        "active_allowlist": ["hmp-healthcheck"],
        "permissions": ["hmp.network.read"],
        "available_capabilities": ["hmp_client_installed"],
    },
    "positive": [],
    "negative": [],
    "fallback": {},
    "unclean": {},
    "event_audit": {},
    "errors": [],
}

for idx, prompt in enumerate(positive_prompts, 1):
    sess = "%s-pos-%02d" % (run_id, idx)
    ep = "%s-ep" % sess
    turn = "turn-%02d" % idx
    decision = protocol.retrieve(session_id=sess, user_message=prompt, hook_context={"episode_id": ep, "turn_id": turn})
    item = {"prompt": prompt, "session_id": sess, "episode_id": ep, "turn_id": turn, "decision": bool(decision)}
    if not decision:
        item["error"] = "no_decision"
        report["errors"].append(item)
        report["positive"].append(item)
        continue
    protocol.persist_intervention(decision)
    injection = protocol.render_injection(decision)
    full_block = protocol.authorize_execute_code(
        {"code": "print('raw should block')"},
        "task-%02d" % idx,
        {"session_id": sess, "episode_id": ep, "turn_id": turn, "tool_call_id": "tc-full-%02d" % idx},
    )
    session_only_block = protocol.authorize_execute_code(
        {"code": "print('raw should block too')"},
        "task-session-%02d" % idx,
        {"session_id": sess, "turn_id": turn, "tool_call_id": "tc-session-%02d" % idx},
    )
    result = protocol.invoke_capability({
        "intervention_id": decision["intervention_id"],
        "capability_id": "hmp-healthcheck",
        "capability_version": "1.0.0",
        "inputs": {"peer_list": [PEER], "timeout_seconds": 3},
    })
    first_row = (result.get("output") or [{}])[0] if result.get("success") else {}
    item.update({
        "intervention_id": decision["intervention_id"],
        "retrieval_event_id": decision.get("retrieval_event_id"),
        "score": decision.get("retrieval_score"),
        "injection_has_intervention_id": decision["intervention_id"] in injection,
        "full_hook_blocked": not full_block.allowed,
        "session_only_hook_blocked": not session_only_block.allowed,
        "invoke_success": result.get("success"),
        "invocation_id": result.get("invocation_id"),
        "peer_status": first_row.get("status"),
        "node_id": (first_row.get("detail") or {}).get("node_id"),
        "state": protocol._store.get_intervention(decision["intervention_id"]).get("state"),
    })
    if not (item["injection_has_intervention_id"] and item["full_hook_blocked"] and item["session_only_hook_blocked"] and item["invoke_success"] and item["state"] == "resolved_success"):
        report["errors"].append(item)
    report["positive"].append(item)

for idx, prompt in enumerate(negative_prompts, 1):
    sess = "%s-neg-%02d" % (run_id, idx)
    decision = protocol.retrieve(session_id=sess, user_message=prompt, hook_context={"episode_id": "%s-ep" % sess, "turn_id": "turn-neg-%02d" % idx})
    item = {"prompt": prompt, "session_id": sess, "decision": bool(decision), "capability_id": decision.get("capability_id") if isinstance(decision, dict) else None}
    if decision:
        report["errors"].append({"negative_false_positive": item})
    report["negative"].append(item)

safe_peer_label = run_id.replace("-", "_")
iid_timeout = "int_%s_timeout" % safe_peer_label
protocol._store.create_intervention(iid_timeout, "%s-fallback-ep" % run_id, "hmp-healthcheck", "1.0.0", session_id="%s-fallback" % run_id, turn_id="turn-fallback")
old_probe = dispatcher._probe_hmp_health
dispatcher._probe_hmp_health = lambda peer, timeout: {"peer": peer, "status": "timeout", "latency_ms": None, "error": "timeout"}
try:
    fb_res = protocol.invoke_capability({"intervention_id": iid_timeout, "capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "inputs": {"peer_list": [PEER], "timeout_seconds": 1}})
finally:
    dispatcher._probe_hmp_health = old_probe
fb_token = fb_res.get("fallback_authorization_id")
fb_bypass = {
    "intervention_id": iid_timeout,
    "capability_id": "hmp-healthcheck",
    "capability_version": "1.0.0",
    "reason_code": "harness_failure",
    "prior_invocation_id": fb_res.get("invocation_id"),
    "failure_code": "timeout",
    "fallback_authorization_id": fb_token,
}
fb_allowed = protocol.authorize_execute_code({"code": "print('fallback after timeout')", "capability_reuse_bypass": fb_bypass}, "task-fallback", {"session_id": "%s-fallback" % run_id, "episode_id": "%s-fallback-ep" % run_id, "turn_id": "turn-fallback", "tool_call_id": "tc-fallback"})
report["fallback"] = {"invoke_success": fb_res.get("success"), "error": fb_res.get("error"), "token_issued": bool(fb_token), "structured_bypass_allowed": fb_allowed.allowed, "fallback_allowed": fb_allowed.allowed, "state": protocol._store.get_intervention(iid_timeout).get("state")}
if not (fb_res.get("error") == "timeout" and fb_token and fb_allowed.allowed and report["fallback"]["state"] == "fallback_consumed"):
    report["errors"].append({"fallback_failed": report["fallback"]})

iid_unclean = "int_%s_unclean" % safe_peer_label
protocol._store.create_intervention(iid_unclean, "%s-unclean-ep" % run_id, "hmp-healthcheck", "1.0.0", session_id="%s-unclean" % run_id, turn_id="turn-unclean")
old_dispatch = dispatcher.dispatch
dispatcher.dispatch = lambda *a, **k: {"success": False, "error": "malformed_response", "output": None}
try:
    un_res = protocol.invoke_capability({"intervention_id": iid_unclean, "capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "inputs": {"peer_list": [PEER], "timeout_seconds": 1}})
finally:
    dispatcher.dispatch = old_dispatch
bypass = {"intervention_id": iid_unclean, "capability_id": "hmp-healthcheck", "capability_version": "1.0.0", "reason_code": "harness_failure_unclean", "prior_invocation_id": un_res.get("invocation_id"), "failure_code": "malformed_response", "detail": "simulated malformed response"}
un_allowed = protocol.authorize_execute_code({"code": "print('manual after unclean failure')", "capability_reuse_bypass": bypass}, "task-unclean", {"session_id": "%s-unclean" % run_id, "episode_id": "%s-unclean-ep" % run_id, "turn_id": "turn-unclean", "tool_call_id": "tc-unclean"})
report["unclean"] = {"invoke_success": un_res.get("success"), "error": un_res.get("error"), "state_after_invoke": un_res.get("state"), "structured_continuation_allowed": un_allowed.allowed, "final_state": protocol._store.get_intervention(iid_unclean).get("state")}
if not (un_res.get("state") == "failed_unclean_read_only" and un_allowed.allowed and report["unclean"]["final_state"] == "unclean_fallback_recorded"):
    report["errors"].append({"unclean_failed": report["unclean"]})

known_iids = {i.get("intervention_id") for i in report["positive"] if i.get("intervention_id")}
known_iids.update([iid_timeout, iid_unclean])
all_events = []
if events_mod.EVENT_LOG.exists():
    for line in events_mod.EVENT_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        data = ev.get("data") or {}
        text = json.dumps(ev, default=str)
        if run_id in text or data.get("intervention_id") in known_iids:
            all_events.append(ev)
counts = {}
for ev in all_events:
    counts[ev.get("event_type")] = counts.get(ev.get("event_type"), 0) + 1
correlation_errors = []
by_session = {}
for ev in all_events:
    data = ev.get("data") or {}
    sess = data.get("session_id") or ""
    if sess:
        by_session.setdefault(sess, []).append(ev)
for item in report["positive"]:
    if not item.get("decision"):
        continue
    sess = item["session_id"]
    evs = by_session.get(sess, [])
    retrievals = [e for e in evs if e.get("event_type") == "retrieval_event"]
    starts = [e for e in evs if e.get("event_type") == "execute_code_started_event"]
    interventions = [e for e in evs if e.get("event_type") == "intervention_event"]
    invocations = [e for e in all_events if e.get("event_type") == "capability_invocation_event" and (e.get("data") or {}).get("intervention_id") == item.get("intervention_id")]
    if not retrievals or not starts or not interventions or not invocations:
        correlation_errors.append({"session_id": sess, "missing": {"retrieval": not bool(retrievals), "start": not bool(starts), "intervention": not bool(interventions), "invocation": not bool(invocations)}})
        continue
    rid = retrievals[-1].get("event_id")
    for started in starts:
        data = started.get("data") or {}
        if data.get("retrieval_event_id") != rid or data.get("session_id") != sess or data.get("turn_id") != item.get("turn_id"):
            correlation_errors.append({"session_id": sess, "bad_start": data})
    if invocations[-1].get("data", {}).get("invocation_id") != item.get("invocation_id"):
        correlation_errors.append({"session_id": sess, "bad_invocation_id": invocations[-1].get("data")})
report["event_audit"] = {"event_count": len(all_events), "counts": counts, "correlation_errors": correlation_errors}
if correlation_errors:
    report["errors"].append({"correlation_errors": correlation_errors})

out = Path("/tmp/%s-report.json" % run_id)
out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(report, indent=2, sort_keys=True))
print("REPORT_PATH=%s" % out)
raise SystemExit(1 if report["errors"] else 0)
