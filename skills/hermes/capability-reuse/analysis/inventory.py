#!/usr/bin/env python3
"""
Topology Study v1.1 — §2/§3/§7 inventory script (frozen prereg).

Read-only. No registry writes, no retriever changes, no graph service,
no skill creation. Computes the §7 power/inventory counts from the
historical execute_code event log.

Data sources (all read-only):
  1. reuse-observer/events.jsonl.bak-pre2416  (pre-2.4.16 log, 1–14 Aug)
  2. reuse-observer/events.jsonl              (current v2.5.0 live log)
  3. capreuse-central/raw/peer70/events.jsonl (collector raw, 29–30 Jul)
  4. capreuse-central/raw/peer106/events.jsonl
  5. capreuse-backup-20260813-1735/peer138/events.jsonl

Node identity per §2: recurrence-audit OPERATION_PATTERNS classes.
NOTE (finding, pre-data): recurrence-audit.py v1.2 does NOT emit confidence
tiers {low, medium, high} — only pattern classes + "high-value (>=3)" flag.
Tier stratification is therefore NOT executable as preregistered; this is
recorded in the report as a prerequisite gap, not redesigned here.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home() / ".hermes"

SOURCES = {
    "bak-pre2416": HOME / "data/reuse-observer/events.jsonl.bak-pre2416",
    "live-v250": HOME / "data/reuse-observer/events.jsonl",
    "raw-peer70": HOME / "data/capreuse-backup-20260813-1735/capreuse-data.tar.gz",  # extracted under /tmp by study
    "raw-peer138": HOME / "data/capreuse-backup-20260813-1735/peer138/events.jsonl",
}

# recurrence-audit.py OPERATION_PATTERNS (imported logic, frozen)
import re
OPERATION_PATTERNS = {
    "hmp_healthcheck": {"matches": [r"curl.*:18643/health", r"urlopen.*18643.*health", r"hmp.*health", r"peer.*health"], "keywords": ["health", "healthcheck", "ping", "status"]},
    "hmp_send": {"matches": [r"curl.*:18643/hmp/send", r"/hmp/send", r"hmp_send"], "keywords": ["hmp/send", "send_to_peer", "payload"]},
    "json_parse": {"matches": [r"json\.loads", r"json\.dumps", r"parse_json"], "keywords": ["json.loads", "json.dumps", "parse json"]},
    "ssh_command": {"matches": [r"ssh\s+fausto@", r"ssh\s+root@", r"subprocess.*ssh"], "keywords": ["ssh", "scp", "remote"]},
    "file_read": {"matches": [r"read_file", r"open\(.*\).*read", r"Path\(.*\).*read_text"], "keywords": ["read file", "read_file", "cat"]},
    "hmp_broadcast": {"matches": [r"broadcast", r"all.*peer", r"every.*peer"], "keywords": ["broadcast", "all peers"]},
    "netboard_display": {"matches": [r"netboard", r"display.*msg", r"overlay"], "keywords": ["netboard", "display"]},
    "cron_management": {"matches": [r"cronjob", r"cron.*job", r"schedule"], "keywords": ["cron", "schedule"]},
}

def classify(code: str) -> str:
    lower = code.lower()
    scores = {}
    for name, p in OPERATION_PATTERNS.items():
        score = sum(2 for pat in p["matches"] if re.search(pat, code, re.I)) + sum(1 for kw in p["keywords"] if kw in lower)
        if score:
            scores[name] = score
    if not scores:
        return "unknown/other"
    return max(scores, key=scores.get)

def load_events():
    """Load all events from available sources, dedup by event_id."""
    events = []
    seen = set()
    # jsonl sources
    for name in ["bak-pre2416", "live-v250", "raw-peer138"]:
        f = SOURCES[name]
        if not f.exists():
            continue
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                eid = obj.get("event_id") or obj.get("data", {}).get("event_id") or f"{name}:{len(events)}"
                if eid in seen:
                    continue
                seen.add(eid)
                events.append(obj)
    # extracted tar.gz sources (peer70, peer106)
    tar_dir = Path("/tmp/capreuse-study")
    for sub in ["capreuse-central/raw/peer70/events.jsonl", "capreuse-central/raw/peer106/events.jsonl"]:
        f = tar_dir / sub
        if not f.exists():
            continue
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                eid = obj.get("event_id") or obj.get("data", {}).get("event_id") or f"{sub}:{len(events)}"
                if eid in seen:
                    continue
                seen.add(eid)
                events.append(obj)
    return events

def event_ts(e) -> str:
    return e.get("timestamp") or (e.get("data") or {}).get("timestamp") or ""

def event_kind(e) -> str:
    return e.get("event_type") or e.get("kind") or "?"

def main():
    events = load_events()
    started = [e for e in events if event_kind(e) == "execute_code_started_event"]
    completed = [e for e in events if event_kind(e) == "execute_code_completed_event"]

    # Episode grouping: session/episode id from data
    ep_by_id = defaultdict(list)
    for e in started:
        d = e.get("data") or {}
        sid = d.get("session_id") or d.get("episode_id") or ""
        ep_by_id[sid].append(e)

    episodes = []
    for sid, evs in sorted(ep_by_id.items(), key=lambda kv: min(event_ts(e) for e in kv[1])):
        # order by timestamp, cluster each invocation
        seq = []
        for e in sorted(evs, key=event_ts):
            d = e.get("data") or {}
            code = d.get("code_preview") or d.get("code") or ""
            seq.append({"ts": event_ts(e), "code": code, "cluster": classify(code)})
        episodes.append({"session_id": sid, "n": len(seq), "seq": seq})

    # Transitions per §2: (x, c1..ct) -> c(t+1), episodes with >=2 clustered invocations
    usable = [ep for ep in episodes if ep["n"] >= 2]
    transitions = []
    for ep in usable:
        for i in range(1, ep["n"]):
            transitions.append({"session": ep["session_id"], "from": ep["seq"][i-1]["cluster"], "to": ep["seq"][i]["cluster"]})

    # Cluster inventory
    cluster_counts = Counter()
    for ep in episodes:
        for s in ep["seq"]:
            cluster_counts[s["cluster"]] += 1
    n_clusters = len(cluster_counts)

    # Cutoffs §3: 50/65/80% episode quantiles by timestamp (min episode ts)
    ep_ts = sorted(min(s["ts"] for s in ep["seq"]) for ep in episodes)
    n_ep = len(ep_ts)
    cutoffs = {}
    if n_ep:
        for q, label in [(0.50, "T1"), (0.65, "T2"), (0.80, "T3")]:
            idx = min(n_ep - 1, int(q * n_ep))
            cutoffs[label] = ep_ts[idx]

    # Failure slice per cutoff: transitions where true c(t+1) absent from M1 top-5.
    # M1 = popularity? No — §5: M1 = embedding retriever. Not runnable here (no retriever
    # invocation in inventory). For §7 counts, we report transitions per cutoff; the
    # embedding-failure slice needs M1, which is out of scope for the power check per
    # prereg §7 ("computed before fitting") — we report the upper bound: all usable
    # transitions per cutoff, and note M1 slice is a subset.
    per_cutoff = {}
    for label, cutoff_ts in cutoffs.items():
        # transitions whose session min-ts < cutoff
        by_session = defaultdict(list)
        for t in transitions:
            by_session[t["session"]].append(t)
        n_tr = 0
        for sid, trs in by_session.items():
            ep_sid = next((e for e in episodes if e["session_id"] == sid), None)
            if ep_sid and min(s["ts"] for s in ep_sid["seq"]) < cutoff_ts:
                n_tr += len(trs)
        per_cutoff[label] = n_tr

    # Tier counts: NOT AVAILABLE (recurrence-audit emits no tiers) — report gap.
    print("=" * 60)
    print("TOPOLOGY STUDY v1.1 — §7 INVENTORY (pre-fit, frozen)")
    print("=" * 60)
    print(f"Eventi totali (dedup):            {len(events)}")
    print(f"execute_code_started:             {len(started)}")
    print(f"execute_code_completed:           {len(completed)}")
    print(f"Episodi totali (sessioni):        {n_ep}")
    print(f"Episodi >= 2 invocazioni:         {len(usable)}")
    print(f"Episodi esclusi (<2):             {n_ep - len(usable)}")
    print(f"Transizioni utilizzabili:         {len(transitions)}")
    print(f"Cluster distinti:                 {n_clusters}")
    print("Distribuzione cluster (occurrences):")
    for c, n in cluster_counts.most_common():
        print(f"    {c:20s} {n}")
    print("\nCutoffs temporali (min-ts episodio, quantile):")
    for label, ts in cutoffs.items():
        print(f"    {label}: {ts}")
    print("\nTransizioni per cutoff (sessione con min-ts < cutoff):")
    for label, n in per_cutoff.items():
        print(f"    {label}: {n}")
    print("\nTier counts: NON DISPONIBILI — recurrence-audit.py v1.2 non emette")
    print("confidence tiers {low, medium, high} (gap prerequisito vs §2).")
    print("\nSoglie §7: >=300 failure-slice transitions pooled; >=100 high-conf tier.")
    print("Nota: failure-slice e' un sottoinsieme delle transizioni (serve M1).")

if __name__ == "__main__":
    main()
