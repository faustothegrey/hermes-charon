#!/usr/bin/env python3
"""v2.4.18 functional cases — Case A, Case A reversed, Case B.

Implements the three v2.4.18 functional cases from the release spec:
  Case A:        peer106 → check HMP health for peer58   (expect ACCEPT/exact_match)
  Case A rev:    peer58  → check HMP health for peer106  (expect ACCEPT/exact_match)
  Case B:        peer106 → check peer58 health and restart it if unhealthy
                 (expect candidate recognized + REJECT/partial_coverage)

Run:  python3 tests/test_v2418_cases.py
"""
from __future__ import annotations
import json, sys, os
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugin"
sys.path.insert(0, str(PLUGIN_DIR))
# Import as package so relative imports in retriever.py resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugin.retriever import retrieve, _extract_request_effect, _coverage_reason
from plugin.registry import list_capabilities


def run_case(name: str, query: str, requester: str, processor: str, target: str,
             expect_covered: bool | None, expect_reason: str | None):
    print(f"\n=== {name} ===")
    print(f"query: {query}")
    caps = list_capabilities()
    hmp = next((c for c in caps if (c.get("retrieval_metadata") or {}).get("capability_id") == "hmp-healthcheck"), None)
    if hmp is None:
        print("  FAIL ❌ hmp-healthcheck non registrata")
        return False

    hook_context = {
        "platform": "hmp",
        "requester_peer_id": requester,
        "processing_peer_id": processor,
        "target_peer_id": target,
        "traffic_type": "organic_peer",
        "producer_surface": "hmp_ingress",
        "session_id": f"{requester}_{processor}_v2418",
        "trace_id": f"{requester}_{processor}_v2418",
    }

    result = retrieve(
        session_id=hook_context["session_id"],
        user_message=query,
        hook_context=hook_context,
        intervention_threshold=0.3,
        minimum_margin=0.02,
        retrieval_threshold=0.05,
    )
    # The retrieval event carries the semantics — reload it from the log.
    log = Path.home() / ".hermes/data/reuse-observer/events.jsonl"
    retrieval_data = None
    if log.exists():
        for line in reversed(log.read_text(errors="replace").splitlines()):
            if hook_context["session_id"] not in line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event_type") == "retrieval_event" and ev.get("data", {}).get("session_id") == hook_context["session_id"]:
                retrieval_data = ev["data"]
                break

    if retrieval_data is None:
        print("  FAIL ❌ nessun retrieval_event trovato")
        return False

    cand_count = retrieval_data.get("candidate_count", 0)
    top_cap = retrieval_data.get("top_capability", "")
    covered = retrieval_data.get("whole_request_covered")
    reason = retrieval_data.get("eligibility_reason", "")
    effect = retrieval_data.get("request_effect", "")
    cap_effect = retrieval_data.get("capability_effect", "")
    stages = retrieval_data.get("retrieval_stages", {})
    trace_id = retrieval_data.get("trace_id", "")

    print(f"  candidate_count: {cand_count}")
    print(f"  top_capability: {top_cap}")
    print(f"  request_effect: {effect} | capability_effect: {cap_effect}")
    print(f"  whole_request_covered: {covered} | eligibility_reason: {reason}")
    print(f"  retrieval_stages: {json.dumps(stages)}")
    print(f"  trace_id: {trace_id}")
    print(f"  retriever_executed: {retrieval_data.get('retriever_executed')}")
    print(f"  producer: {retrieval_data.get('producer')}")

    ok = True
    if trace_id != hook_context["session_id"]:
        print(f"  FAIL ❌ trace_id non propagato"); ok = False
    if retrieval_data.get("retriever_executed") is not True:
        print(f"  FAIL ❌ retriever_executed non True"); ok = False
    if cand_count == 0:
        print(f"  FAIL ❌ candidate_count=0 (il candidato deve essere riconosciuto)"); ok = False
    if top_cap != "hmp-healthcheck@1.0.0":
        print(f"  FAIL ❌ top_capability atteso hmp-healthcheck@1.0.0, got {top_cap}"); ok = False
    if expect_covered is not None and covered != expect_covered:
        print(f"  FAIL ❌ whole_request_covered atteso {expect_covered}, got {covered}"); ok = False
    if expect_reason is not None:
        if reason != expect_reason:
            print(f"  FAIL ❌ eligibility_reason atteso {expect_reason}, got {reason}"); ok = False
    elif reason in ("partial_coverage", "effect_mismatch"):
        print(f"  FAIL ❌ eligibility_reason non atteso: {reason}"); ok = False
    print(f"  {'PASS ✅' if ok else 'FAIL ❌'}")
    return ok


def main():
    results = []
    # Case A: exact match healthcheck
    results.append(("Case A", run_case(
        "Case A", "check HMP health for peer58",
        "peer106", "peer106", "peer58",
        expect_covered=True, expect_reason=None,
    )))
    # Case A reversed: identity hardcoding check
    results.append(("Case A rev", run_case(
        "Case A reversed", "check HMP health for peer106",
        "peer58", "peer58", "peer106",
        expect_covered=True, expect_reason=None,
    )))
    # Case B: composite — candidate recognized + structured rejection
    results.append(("Case B", run_case(
        "Case B", "check peer58 health and restart it if unhealthy",
        "peer106", "peer106", "peer58",
        expect_covered=False, expect_reason="partial_coverage",
    )))

    print("\n=== RIEPILOGO ===")
    passed = sum(1 for _, r in results if r)
    for name, r in results:
        print(f"  {name}: {'PASS ✅' if r else 'FAIL ❌'}")
    print(f"\n{passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
