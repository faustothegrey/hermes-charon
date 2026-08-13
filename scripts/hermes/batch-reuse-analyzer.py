#!/usr/bin/env python3
"""v2.4.4 batch-reuse-analyzer: event-time windows, stream separation, cohort split, nested event payload aware."""
from __future__ import annotations
import json, os, csv
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

EVENTS = Path.home()/".hermes/data/reuse-observer/events.jsonl"
OUT = Path.home()/".hermes/data/reuse-aggregati/latest.json"
REPORT_DIR = Path.home()/".hermes/data/reuse-aggregati"
LABELS = Path.home()/".hermes/data/reuse-observer/review-labels.jsonl"

def load_events():
    evs=[]; bad=0
    if EVENTS.exists():
        for line in EVENTS.read_text().splitlines():
            if not line.strip(): continue
            try: evs.append(json.loads(line))
            except Exception: bad += 1
    return evs,bad

def payload(ev):
    return ev.get("data") if isinstance(ev.get("data"), dict) else ev

def etype(ev):
    return ev.get("event_type") or payload(ev).get("event_type") or "<missing>"

def ev_time(ev):
    d=payload(ev); ts=d.get("timestamp") or ev.get("timestamp") or ""
    try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception: return datetime(1970,1,1,tzinfo=timezone.utc)

def chain_key(d):
    return tuple(d.get(k, "") for k in ("session_id","episode_id","turn_id","task_id","tool_call_id","retrieval_event_id","code_hash"))

def neutralize(v):
    if isinstance(v, str) and v[:1] in ("=","+","-","@"):
        return "'"+v
    return v

def load_labels():
    labels={}
    if LABELS.exists():
        for line in LABELS.read_text().splitlines():
            if not line.strip(): continue
            try:
                d=json.loads(line); labels[d["event_id"]]=d
            except Exception: pass
    return labels

def main():
    evs,bad=load_events(); now=datetime.now(timezone.utc); labels=load_labels()
    rows=[(e,payload(e),etype(e),ev_time(e)) for e in evs]
    recent=[r for r in rows if (now-r[3]).total_seconds()<3600]
    cohort=json.loads((Path.home()/".hermes/data/reuse-observer/cohort.json").read_text())
    current_dep=cohort.get("deployment_id")
    cohort_label=cohort.get("cohort_label") or "v2.4.4_clean_live"
    cohort_ver=cohort.get("plugin_version") or "2.4.4"
    clean=[r for r in rows if r[1].get("cohort_label")==cohort_label and r[1].get("plugin_version")==cohort_ver and r[1].get("deployment_id")==current_dep]
    legacy=[r for r in rows if r not in clean]
    clean_retr=[r for r in clean if r[2]=="retrieval_event"]
    ro=[r for r in clean_retr if str(r[1].get("effect_stream") or r[1].get("effect_class") or "").startswith("read")]
    mu=[r for r in clean_retr if str(r[1].get("effect_stream") or r[1].get("effect_class") or "").startswith("mutat")]
    # chain errors for clean cohort
    starts=defaultdict(int); comps=defaultdict(int); retrieval_keys=set(); chain_errors=[]
    for _,d,t,_ in clean:
        k=chain_key(d)
        if t=="retrieval_event": retrieval_keys.add(k)
        elif t=="execute_code_started_event": starts[k]+=1
        elif t=="execute_code_completed_event": comps[k]+=1
    for k in retrieval_keys:
        if not all(k): chain_errors.append({"type":"identifier_mismatch","key":k})
        if starts.get(k,0)!=1: chain_errors.append({"type":"start_count","key":k,"count":starts.get(k,0)})
        if comps.get(k,0)!=1: chain_errors.append({"type":"completion_count","key":k,"count":comps.get(k,0)})
    for k,c in starts.items():
        if k not in retrieval_keys: chain_errors.append({"type":"start_without_retrieval","key":k,"count":c})
    for k,c in comps.items():
        if k not in starts: chain_errors.append({"type":"completion_without_start","key":k,"count":c})
        if c>1: chain_errors.append({"type":"duplicate_completion","key":k,"count":c})
    independent=len(set((d.get("session_id"),d.get("peer_id"),d.get("task_id")) for _,d,_,_ in clean_retr))
    by_cap=Counter((d.get("top_capability") or (d.get("candidates") or [{}])[0].get("capability") or "<missing>") for _,d,_,_ in clean_retr)
    summary={
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "batch-reuse-analyzer v2.4.4",
        "bad_json_lines": bad,
        "total_events": len(evs),
        "events_last_1h_event_time": len(recent),
        "cohort": {"current_deployment_id": current_dep, "v2.4.4_clean_live_events": len(clean), "legacy_or_pre_events": len(legacy), "v2.4.4_clean_live_retrievals": len(clean_retr)},
        "streams": {"read_only_retrievals": len(ro), "mutating_retrievals": len(mu), "mutating_in_read_only": sum(1 for _,d,_,_ in ro if str(d.get("effect_class","")).startswith("mutat"))},
        "recurrence": {"raw_occurrences": len(clean_retr), "independent_occurrences": independent, "by_top_capability": dict(by_cap)},
        "by_type": dict(Counter(t for _,_,t,_ in rows)),
        "clean_by_type": dict(Counter(t for _,_,t,_ in clean)),
        "latest_timestamps": {
            "retrieval": max((r[3].strftime("%Y-%m-%dT%H:%M:%SZ") for r in rows if r[2]=="retrieval_event"), default="never"),
            "completed": max((r[3].strftime("%Y-%m-%dT%H:%M:%SZ") for r in rows if r[2]=="execute_code_completed_event"), default="never"),
        },
        "chain_correlation": {"errors": len(chain_errors), "sample": chain_errors[:5]},
        "durable_labels": len(labels),
        "version": "2.4.4",
        "shadow_mode": True,
        "active_scope": "hmp-healthcheck@1.0.0",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    # review CSV with neutralization for user controlled text
    csv_path=REPORT_DIR/"review"/"queue-v244-clean.csv"; csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields=["event_id","redacted_request","top_candidate","top_score","second_candidate","second_score","score_margin","eligibility_result","filter_rejection_reasons","request_effect","capability_effect","whole_request_coverage","provenance","peer_id","session_id","traffic_type","human_label","reviewer","review_timestamp"]
    with csv_path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for _,d,_,_ in clean_retr:
            eid=d.get("event_id") or d.get("retrieval_event_id")
            lab=labels.get(eid,{})
            w.writerow({
                "event_id": neutralize(eid),
                "redacted_request": neutralize(d.get("user_message_preview","")),
                "top_candidate": neutralize(d.get("top_capability","")),
                "top_score": d.get("top_score",""),
                "second_candidate": neutralize(d.get("second_capability","")),
                "second_score": d.get("second_score",""),
                "score_margin": d.get("score_margin",""),
                "eligibility_result": neutralize(d.get("eligibility_result","")),
                "filter_rejection_reasons": neutralize(json.dumps(d.get("filter_rejection_reasons",[]))),
                "request_effect": neutralize(d.get("request_effect","")),
                "capability_effect": neutralize(d.get("capability_effect","")),
                "whole_request_coverage": d.get("whole_request_coverage",""),
                "provenance": neutralize(json.dumps(d.get("provenance",{}))),
                "peer_id": neutralize(d.get("peer_id","")),
                "session_id": neutralize(d.get("session_id","")),
                "traffic_type": neutralize(d.get("traffic_type","")),
                "human_label": neutralize(lab.get("label","")),
                "reviewer": neutralize(lab.get("reviewer","")),
                "review_timestamp": neutralize(lab.get("label_timestamp","")),
            })
    print(json.dumps(summary, indent=2))
if __name__ == "__main__": main()
