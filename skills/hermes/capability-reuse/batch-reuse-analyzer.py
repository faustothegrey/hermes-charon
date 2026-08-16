#!/usr/bin/env python3
"""v2.4.6 batch-reuse-analyzer: event-time windows, stream separation, cohort split, nested event payload aware."""
from __future__ import annotations
import json, os, csv, hashlib
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
    if isinstance(v, str) and v.lstrip(" \t\r\n")[:1] in ("=","+","-","@"):
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


# Compatibility API restored in v2.4.6 for legacy analyzer tests.
def parse_utc(text):
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))

def atomic_write_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def _sanitize_peer_id(peer_id):
    return "".join(c if c.isalnum() or c in ("-","_") else "_" for c in str(peer_id)).strip("_") or "unknown"

def read_delta(events_path, cursor_path):
    events_path=Path(events_path); cursor_path=Path(cursor_path)
    size=events_path.stat().st_size if events_path.exists() else 0
    inode=events_path.stat().st_ino if events_path.exists() else 0
    offset=0
    try:
        c=json.loads(cursor_path.read_text())
        if c.get("inode") == inode and isinstance(c.get("offset"), int) and c.get("offset",0) >= 0:
            offset=c.get("offset",0)
    except Exception:
        offset=0
    parsed=[]; bad=0; good_end=offset
    with events_path.open('rb') as f:
        f.seek(offset)
        pos=offset
        for raw in f:
            pos += len(raw)
            try:
                parsed.append(json.loads(raw.decode('utf-8'))); good_end=pos
            except Exception:
                bad += 1
                break
    return parsed, bad, {"inode": inode, "offset": good_end}, size

def initial_stats(peer_id, now):
    return {"generated_at": now, "peer_id": peer_id, "total_events": 0, "anomalies": [],
            "by_type": {}, "safety": {"read_only_mutating_candidate_sets": 0},
            "retrieval": {"total": 0, "by_provenance": {}, "review_queue": []}}

def _norm_effect(v):
    t=str(v or "").replace('-', '_')
    return "read_only" if t.startswith('read') else ("mutating" if t.startswith('mutat') else t)

def _prov(d):
    p=d.get('provenance') if isinstance(d.get('provenance'), dict) else {}
    s=p.get('stream')
    if not s:
        return 'legacy_unclassified', 'missing_provenance'
    if s not in ('organic_live','operator_seeded','calibration_probe','legacy_unclassified'):
        return 'unknown', 'invalid_provenance'
    return s, ''

def _cap_name(c):
    cid=c.get('capability') or c.get('capability_id') or c.get('id') or ''
    ver=c.get('capability_version') or c.get('version') or ''
    return cid if '@' in str(cid) or not ver else f"{cid}@{ver}"

def add_event(stats, event, labels):
    stats['total_events'] += 1
    t=etype(event); stats['by_type'][t]=stats['by_type'].get(t,0)+1
    if t != 'retrieval_event': return
    d=payload(event); stats['retrieval']['total'] += 1
    prov, anomaly=_prov(d)
    stats['retrieval']['by_provenance'][prov]=stats['retrieval']['by_provenance'].get(prov,0)+1
    if anomaly and anomaly not in stats['anomalies']: stats['anomalies'].append(anomaly)
    candidates=d.get('candidates') if isinstance(d.get('candidates'), list) else []
    effects={_norm_effect(c.get('effect_class')) for c in candidates}
    if 'read_only' in effects and 'mutating' in effects:
        stats['safety']['read_only_mutating_candidate_sets'] += 1
        if 'read_only_mutating_candidates_seen_together' not in stats['anomalies']:
            stats['anomalies'].append('read_only_mutating_candidates_seen_together')
    top=candidates[0] if candidates else {}
    eid=event.get('event_id') or d.get('event_id') or d.get('retrieval_event_id') or ''
    lab=labels.get(eid,{}) if isinstance(labels, dict) else {}
    row={"timestamp": d.get('timestamp') or event.get('timestamp') or stats['generated_at'],
         "event_id": eid, "peer_id": d.get('peer_id') or stats['peer_id'], "provenance": prov,
         "capability": _cap_name(top), "candidate": _cap_name(top), "score": top.get('score', d.get('top_score','')),
         "shadow_mode": d.get('shadow_mode', True), "redacted_request": d.get('user_message_preview',''),
         "label": lab.get('label',''), "review_notes": lab.get('review_notes','')}
    stats['retrieval']['review_queue'].append(row)

def finalize_stats(stats):
    return stats

def acquire_lock(lock, stale_seconds=600):
    lock=Path(lock); lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        if lock.exists() and (datetime.now().timestamp()-lock.stat().st_mtime)>stale_seconds:
            lock.unlink()
    except Exception: pass
    return os.open(str(lock), os.O_CREAT|os.O_RDWR)

def _load_existing_review_labels(outdir):
    p=Path(outdir)/'review'/'queue-latest.jsonl'; labels={}
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                d=json.loads(line); labels[d.get('event_id')]=d
            except Exception: pass
    return labels

def export_review_queue(events_path, outdir, labels, limit=100):
    events,_bad,_cur,_size=read_delta(events_path, Path(outdir)/'dummy-cursor.json')
    merged={**_load_existing_review_labels(outdir), **(labels or {})}
    stats=initial_stats('peer-test', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    for ev in events: add_event(stats, ev, merged)
    rows=stats['retrieval']['review_queue'][:limit]
    review=Path(outdir)/'review'; review.mkdir(parents=True, exist_ok=True)
    with (review/'queue-latest.jsonl').open('w') as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False)+'\n')
    fields=['timestamp','event_id','peer_id','provenance','capability','score','redacted_request','label','review_notes']
    with (review/'queue-latest.csv').open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader();
        for r in rows: w.writerow({k: neutralize(r.get(k,'')) for k in fields})
    return {'rows': len(rows)}

def _write_rollups(outdir, stats, now_dt):
    roll=Path(outdir)/'rollups'; roll.mkdir(parents=True, exist_ok=True)
    rows=stats['retrieval']['review_queue']
    recent=[]
    for r in rows:
        try:
            if (now_dt-parse_utc(r['timestamp'])).total_seconds() <= 86400: recent.append(r)
        except Exception: pass
    data={'window_basis':'event_timestamp','totals':{'retrieval_total':len(recent)},
          'retrieval':{'by_provenance':dict(Counter(r['provenance'] for r in recent)),
                       'candidate_counts':dict(Counter(r['capability'] for r in recent)),
                       'review_candidates':[{'candidate': r['capability']} for r in recent]}}
    atomic_write_json(roll/'24h.json', data)
    return {'24h': data}

def build_rollups(outdir, now_dt=None):
    now_dt=now_dt or datetime.now(timezone.utc)
    stats=initial_stats('aggregate', now_dt.strftime('%Y-%m-%dT%H:%M:%SZ'))
    for run in (Path(outdir)/'runs').glob('*.json'):
        try:
            d=json.loads(run.read_text()); stats['retrieval']['review_queue'].extend(d.get('retrieval',{}).get('review_queue',[]))
        except Exception: pass
    return _write_rollups(outdir, stats, now_dt)

def analyze(events_path, outdir, cursor_path, peer_id='unknown', now=None):
    now=now or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    events,bad,new_cursor,_size=read_delta(events_path, cursor_path)
    stats=initial_stats(peer_id, now); stats['bad_json_lines']=bad
    labels=_load_existing_review_labels(outdir)
    for ev in events: add_event(stats, ev, labels)
    finalize_stats(stats)
    outdir=Path(outdir); outdir.mkdir(parents=True, exist_ok=True); (outdir/'runs').mkdir(exist_ok=True)
    atomic_write_json(cursor_path, new_cursor); atomic_write_json(outdir/'latest.json', stats)
    safe=_sanitize_peer_id(peer_id); atomic_write_json(outdir/'runs'/f"{safe}-{now.replace(':','').replace('-','')}.json", stats)
    export_review_queue(events_path, outdir, labels)
    _write_rollups(outdir, stats, parse_utc(now))
    return stats

def cohort_filter(rows, filter_version, filter_dep, expected_hash, expected_schema, excluded_traffic=None):
    """v2.5.0 (spec 14): cohort-specific analyzer filtering.

    rows: list of (event, payload_dict, event_type, timestamp).
    Returns (clean, legacy, excluded_by_version, excluded_by_traffic, excluded_by_producer).
    Clean = events matching deployment_id + plugin_version + artifact hash +
    schema, minus excluded traffic classes. Everything else is legacy.
    """
    excluded_traffic = set(excluded_traffic or [])
    clean = [r for r in rows
             if r[1].get("deployment_id") == filter_dep
             and r[1].get("plugin_version") == filter_version
             and (not expected_hash or r[1].get("plugin_artifact_hash") == expected_hash)
             and (r[1].get("schema_version") or r[0].get("schema_version")) == expected_schema
             and (not excluded_traffic or r[1].get("traffic_type") not in excluded_traffic)]
    legacy = [r for r in rows if r not in clean]
    excluded_by_version = Counter((r[1].get("plugin_version") or "missing") for r in legacy)
    excluded_by_traffic = Counter((r[1].get("traffic_type") or "missing") for r in legacy)
    excluded_by_producer = Counter(((r[1].get("producer") or {}).get("surface") or "missing") for r in legacy)
    return clean, legacy, excluded_by_version, excluded_by_traffic, excluded_by_producer


def validate_report(report, events_path):
    """v2.5.0 (spec 13): consumers reject stale analyzer reports.

    A report must carry input_event_log_sha256, input_event_count,
    input_min_timestamp, input_max_timestamp, analyzer_version, generated_at.
    Rejection when:
      - the fingerprint hash != current event-log hash, or
      - the covered timestamp range excludes the latest event in the log.
    Returns (ok: bool, reasons: list[str]).
    """
    reasons = []
    if not isinstance(report, dict):
        return False, ["report_not_object"]
    fp = report.get("input_event_log_sha256")
    if not fp:
        reasons.append("missing_input_fingerprint")
    if not report.get("input_event_count"):
        reasons.append("missing_input_event_count")
    if not report.get("analyzer_version"):
        reasons.append("missing_analyzer_version")
    if not report.get("generated_at"):
        reasons.append("missing_generated_at")
    if not report.get("input_min_timestamp") or not report.get("input_max_timestamp"):
        reasons.append("missing_input_time_range")
    elif report["input_min_timestamp"] > report["input_max_timestamp"]:
        reasons.append("inverted_time_range")
    try:
        log_bytes = Path(events_path).read_bytes()
    except FileNotFoundError:
        return False, reasons + ["event_log_missing"]
    cur = hashlib.sha256(log_bytes).hexdigest()
    if fp and fp != cur:
        reasons.append("event_log_hash_mismatch")
    lines = [l for l in log_bytes.decode("utf-8", "replace").splitlines() if l.strip()]
    if lines and report.get("input_max_timestamp"):
        try:
            last = json.loads(lines[-1])
            last_ts = last.get("timestamp") or (last.get("data") or {}).get("timestamp") or ""
            if last_ts and report["input_max_timestamp"] < last_ts:
                reasons.append("range_excludes_latest_event")
        except Exception:
            pass
    return (len(reasons) == 0), reasons


def main():
    import argparse
    parser = argparse.ArgumentParser(description="v2.5.0 cohort-filtered reuse analyzer")
    parser.add_argument("--plugin-version", default=None, help="Only analyze events with this plugin_version")
    parser.add_argument("--deployment-id", default=None, help="Only analyze events with this deployment_id")
    parser.add_argument("--exclude-traffic", nargs="*", default=None,
                        help="Exclude these traffic classes (e.g. registry_sync cron)")
    args = parser.parse_args()

    evs,bad=load_events(); now=datetime.now(timezone.utc); labels=load_labels()
    rows=[(e,payload(e),etype(e),ev_time(e)) for e in evs]
    recent=[r for r in rows if (now-r[3]).total_seconds()<3600]
    cohort=json.loads((Path.home()/".hermes/data/reuse-observer/cohort.json").read_text())
    current_dep=cohort.get("deployment_id")
    expected_version=cohort.get("plugin_version")
    expected_hash=cohort.get("plugin_artifact_hash")
    expected_schema=cohort.get("schema_version", "1.3")

    # v2.5.0: cohort-specific filtering (--plugin-version / --deployment-id)
    # plus optional traffic-class exclusion. Defaults to the active cohort.
    filter_version = args.plugin_version or expected_version
    filter_dep = args.deployment_id or current_dep
    excluded_traffic = set(args.exclude_traffic or [])

    clean, legacy, excluded_by_version, excluded_by_traffic, excluded_by_producer = cohort_filter(
        rows, filter_version, filter_dep, expected_hash, expected_schema, excluded_traffic)
    clean_retr=[r for r in clean if r[2]=="retrieval_event"]

    # v2.5.0: event-log fingerprint so consumers reject stale reports.
    log_bytes = Path.home().joinpath(".hermes/data/reuse-observer/events.jsonl").read_bytes()
    log_sha256 = hashlib.sha256(log_bytes).hexdigest()
    all_ts = [r[3] for r in rows]
    input_min = min(all_ts).strftime("%Y-%m-%dT%H:%M:%SZ") if all_ts else None
    input_max = max(all_ts).strftime("%Y-%m-%dT%H:%M:%SZ") if all_ts else None

    ro=[r for r in clean_retr if str(r[1].get("request_effect") or r[1].get("effect_stream") or r[1].get("effect_class") or "").startswith("read")]
    mu=[r for r in clean_retr if str(r[1].get("request_effect") or r[1].get("effect_stream") or r[1].get("effect_class") or "").startswith("mutat")]
    # chain errors for clean cohort. Capability invocations and execute_code chains are separate:
    # active reuse retrievals correlate through intervention/invocation/outcome; only actual execute_code
    # starts require execute_code completions. Do not require execute_code for dispatch=none or capability success.
    starts=defaultdict(int); comps=defaultdict(int); chain_errors=[]
    retrieval_ids=set(); intervention_by_rid=defaultdict(int); invocation_by_rid=defaultdict(int); outcome_by_rid=defaultdict(int)
    for _,d,t,_ in clean:
        rid=d.get("retrieval_event_id") or d.get("event_id") or ""
        if t=="retrieval_event": retrieval_ids.add(rid)
        elif t=="intervention_event": intervention_by_rid[d.get("retrieval_event_id","")]+=1
        elif t=="capability_invocation_event": invocation_by_rid[d.get("retrieval_event_id","")]+=1
        elif t=="outcome_event": outcome_by_rid[d.get("retrieval_event_id","")]+=1
        elif t=="execute_code_started_event" and d.get("code_hash") and d.get("retrieval_event_id"):
            starts[chain_key(d)] += 1
        elif t=="execute_code_completed_event" and d.get("code_hash") and d.get("retrieval_event_id"):
            comps[chain_key(d)] += 1
    retrieval_by_id={ (d.get("retrieval_event_id") or d.get("event_id") or ""): d for _,d,t,_ in clean if t=="retrieval_event" }
    for rid,d in retrieval_by_id.items():
        if d.get("intervened") is True:
            if intervention_by_rid.get(rid,0)!=1: chain_errors.append({"type":"retrieval_without_single_intervention","retrieval_event_id":rid,"count":intervention_by_rid.get(rid,0)})
            if invocation_by_rid.get(rid,0)!=1: chain_errors.append({"type":"intervention_without_single_completion","retrieval_event_id":rid,"count":invocation_by_rid.get(rid,0)})
            if outcome_by_rid.get(rid,0)!=1: chain_errors.append({"type":"completion_without_outcome","retrieval_event_id":rid,"count":outcome_by_rid.get(rid,0)})
    for k,c in starts.items():
        if comps.get(k,0)==0: chain_errors.append({"type":"start_without_completion","key":k,"count":c})
    for k,c in comps.items():
        if starts.get(k,0)==0: chain_errors.append({"type":"completion_without_start","key":k,"count":c})
        if c>1: chain_errors.append({"type":"duplicate_completion","key":k,"count":c})
    independent=len(set((d.get("session_id"),d.get("peer_id"),d.get("task_id")) for _,d,_,_ in clean_retr))
    by_cap=Counter((d.get("top_capability") or (d.get("candidates") or [{}])[0].get("capability") or "<missing>") for _,d,_,_ in clean_retr)
    summary={
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "batch-reuse-analyzer v2.5.0",
        "bad_json_lines": bad,
        "total_events": len(evs),
        "events_last_1h_event_time": len(recent),
        # v2.5.0: input fingerprint so consumers reject stale reports.
        "input_event_log_sha256": log_sha256,
        "input_event_count": len(evs),
        "input_min_timestamp": input_min,
        "input_max_timestamp": input_max,
        "analyzer_version": "2.5.0",
        "cohort_filter": {
            "plugin_version": filter_version,
            "deployment_id": filter_dep,
            "excluded_traffic_classes": sorted(excluded_traffic),
            "included_events": len(clean),
            "excluded_legacy_events": len(legacy),
            "excluded_by_version": dict(excluded_by_version),
            "excluded_by_traffic": dict(excluded_by_traffic),
            "excluded_by_producer_surface": dict(excluded_by_producer),
        },
        "cohort": {"current_deployment_id": current_dep, "expected_plugin_version": expected_version, "expected_plugin_artifact_hash": expected_hash, "current_clean_events": len(clean), "legacy_or_pre_events": len(legacy), "current_clean_retrievals": len(clean_retr)},
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
        "version": "2.5.0",
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
