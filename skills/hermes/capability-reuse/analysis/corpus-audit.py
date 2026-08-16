#!/usr/bin/env python3
"""
Topology Study v1.1 — READ-ONLY corpus & clusterability audit (2026-08-16).

No implementation changes. No algorithm changes. Counts and examples only.
Answers:
  1. Event-type inventory of the 3,352 dedup events.
  2. Capability-bearing executions NOT represented as execute_code_started.
  3. Mechanical explanation of the 4-cluster assignment for the 79 started
     events (esp. 71 unknown/other).
  4. Descriptive sub-pattern breakdown of unknown/other (no algorithm change).
  5. Usable-transition volume estimates under 3 inclusion criteria.
  6. Sparsity attribution (executions / schema observability / audit
     resolution / session fragmentation / combination).
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home() / ".hermes"
TAR_DIR = Path("/tmp/capreuse-study")


def load_all_events():
    """Dedup by event_id across all sources (same as inventory.py)."""
    events = []
    seen = set()
    jsonl_sources = [
        HOME / "data/reuse-observer/events.jsonl.bak-pre2416",
        HOME / "data/reuse-observer/events.jsonl",
        HOME / "data/capreuse-backup-20260813-1735/peer138/events.jsonl",
    ]
    for f in jsonl_sources:
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
                eid = obj.get("event_id") or (obj.get("data") or {}).get("event_id") or f"{f.name}:{len(events)}"
                if eid in seen:
                    continue
                seen.add(eid)
                events.append(obj)
    for sub in ["capreuse-central/raw/peer70/events.jsonl", "capreuse-central/raw/peer106/events.jsonl"]:
        f = TAR_DIR / sub
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
                eid = obj.get("event_id") or (obj.get("data") or {}).get("event_id") or f"{sub}:{len(events)}"
                if eid in seen:
                    continue
                seen.add(eid)
                events.append(obj)
    return events


def ev_kind(e):
    return e.get("event_type") or e.get("kind") or "?"


def ev_data(e):
    return e.get("data") if isinstance(e.get("data"), dict) else {}


# ── recurrence-audit OPERATION_PATTERNS (verbatim from script v1.2, frozen) ──
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


def classify(code):
    lower = code.lower()
    scores = {}
    for name, p in OPERATION_PATTERNS.items():
        score = sum(2 for pat in p["matches"] if re.search(pat, code, re.I)) + sum(1 for kw in p["keywords"] if kw in lower)
        if score:
            scores[name] = score
    if not scores:
        return "unknown/other"
    return max(scores, key=scores.get)


def classify_detail(code):
    """Return (cluster, [(pattern, score), ...]) — mechanical trace."""
    lower = code.lower()
    scores = {}
    for name, p in OPERATION_PATTERNS.items():
        s = 0
        for pat in p["matches"]:
            if re.search(pat, code, re.I):
                s += 2
        for kw in p["keywords"]:
            if kw in lower:
                s += 1
        if s:
            scores[name] = s
    if not scores:
        return "unknown/other", []
    return max(scores, key=scores.get), sorted(scores.items(), key=lambda x: -x[1])


def main():
    events = load_all_events()
    print("=" * 70)
    print("AUDIT 1 — EVENT-TYPE INVENTORY (3,352 dedup)")
    print("=" * 70)
    kinds = Counter(ev_kind(e) for e in events)
    for k, n in kinds.most_common():
        print(f"  {k:45s} {n}")

    print("\n" + "=" * 70)
    print("AUDIT 2 — CAPABILITY-BEARING EVENTS NOT execute_code_started")
    print("=" * 70)
    # Look at payloads of non-started events: do they carry code/tool/action?
    caps = defaultdict(list)
    for e in events:
        k = ev_kind(e)
        if k == "execute_code_started_event":
            continue
        d = ev_data(e)
        # candidate capability-bearing fields
        fields = [f for f in ("code", "code_preview", "code_hash", "tool", "tool_name", "name", "action", "operation", "command", "text") if d.get(f)]
        if fields:
            caps[k].append({f: str(d[f])[:60] for f in fields})
    for k, items in sorted(caps.items(), key=lambda x: -len(x[1])):
        print(f"\n  [{k}] — {len(items)} eventi con payload capability-bearing")
        for it in items[:4]:
            print(f"      {it}")

    print("\n" + "=" * 70)
    print("AUDIT 3 — MECHANICAL CLUSTER ASSIGNMENT (79 started)")
    print("=" * 70)
    started = [e for e in events if ev_kind(e) == "execute_code_started_event"]
    print(f"  Totale started: {len(started)}")
    assigned = Counter()
    traces = defaultdict(list)
    for e in started:
        code = ev_data(e).get("code_preview") or ev_data(e).get("code") or ""
        cl, tr = classify_detail(code)
        assigned[cl] += 1
        traces[cl].append((code[:70], tr))
    for cl, n in assigned.most_common():
        print(f"\n  {cl}: {n}")
        for code, tr in traces[cl][:3]:
            print(f"      code: {code!r}")
            print(f"      trace: {tr if tr else 'NO pattern matched (score 0) → unknown/other'}")

    print("\n" + "=" * 70)
    print("AUDIT 4 — unknown/other SUB-PATTERNS (descriptive, no algorithm change)")
    print("=" * 70)
    unk_codes = [ev_data(e).get("code_preview") or ev_data(e).get("code") or "" for e in started if classify(ev_data(e).get("code_preview") or ev_data(e).get("code") or "") == "unknown/other"]
    # descriptive regex families — analysis only, NOT a new clustering
    families = {
        "urllib/requests HTTP": r"urllib|requests|urlopen|http",
        "subprocess/shell": r"subprocess|os\.system|shell|Popen|check_output",
        "sqlite/db": r"sqlite|conn\.|cursor|execute\(",
        "file write/patch": r"write_file|open\(.*w|patch\(|write_text|mkdir|chmod",
        "path/glob": r"glob|iterdir|rglob|Path\(|listdir",
        "json/config load": r"json\.load|read_text|load\(",
        "datetime/time": r"datetime|time\.|strftime|timestamp",
        "import-only": r"^import |^from ",
        "print/repr": r"^print|repr\(|str\(",
        "mixed/multi": r"",
    }
    fam_counts = Counter()
    for c in unk_codes:
        matched = [name for name, pat in families.items() if pat and re.search(pat, c, re.I)]
        if not matched:
            fam_counts["other/unmatched"] += 1
        else:
            fam_counts["+".join(matched[:2])] += 1
    print(f"  unknown/other: {len(unk_codes)}")
    for fam, n in fam_counts.most_common(15):
        print(f"    {fam:45s} {n}")
    print("\n  Esempi per famiglia:")
    fam_ex = defaultdict(list)
    for c in unk_codes:
        matched = [name for name, pat in families.items() if pat and re.search(pat, c, re.I)]
        key = "+".join(matched[:2]) if matched else "other/unmatched"
        if len(fam_ex[key]) < 2:
            fam_ex[key].append(c[:90])
    for fam, exs in fam_ex.items():
        for x in exs:
            print(f"    [{fam}] {x!r}")

    print("\n" + "=" * 70)
    print("AUDIT 5 — USABLE TRANSITION VOLUME ESTIMATES")
    print("=" * 70)
    # current criteria (prereg §2): episodes >=2 clustered invocations,
    # cluster = recurrence-audit class
    ep_by_id = defaultdict(list)
    for e in started:
        d = ev_data(e)
        sid = d.get("session_id") or d.get("episode_id") or ""
        ep_by_id[sid].append(e)
    print(f"\n  Sessioni (episodi): {len(ep_by_id)}")
    sizes = Counter(len(v) for v in ep_by_id.values())
    print(f"  Distribuzione invocazioni per sessione: {dict(sorted(sizes.items()))}")

    def transitions_for(cluster_fn):
        total_tr = 0
        usable_eps = 0
        for sid, evs in ep_by_id.items():
            seq = [cluster_fn(ev_data(e).get("code_preview") or ev_data(e).get("code") or "") for e in evs]
            if len(seq) >= 2:
                usable_eps += 1
                total_tr += len(seq) - 1
        return usable_eps, total_tr

    # (a) current: recurrence-audit classes
    eps_a, tr_a = transitions_for(lambda c: classify(c))
    # (b) broader: unknown/other split into sub-families (descriptive families above)
    def broad_class(c):
        cl = classify(c)
        if cl != "unknown/other":
            return cl
        matched = [name for name, pat in families.items() if pat and re.search(pat, c, re.I)]
        return "+".join(matched[:2]) if matched else "other/unmatched"
    eps_b, tr_b = transitions_for(broad_class)
    # (c) improved resolution, same 79: assume per-execution unique-ish resolution
    # (every invocation its own cluster → maximal possible transitions)
    eps_c, tr_c = transitions_for(lambda c: c)  # code string as cluster id (maximal)
    print(f"\n  (a) Criteri attuali (recurrence-audit, 4 cluster):       {eps_a} episodi usabili, {tr_a} transizioni")
    print(f"  (b) Criterio ampio (unknown/other → sotto-pattern descrittivi): {eps_b} episodi usabili, {tr_b} transizioni")
    print(f"  (c) Risoluzione massima (ogni codice = cluster, stesso 79):      {eps_c} episodi usabili, {tr_c} transizioni")
    print(f"\n  Soglia §7 (failure-slice ≥300): nessuno scenario la raggiunge;")
    print(f"  il failure-slice è un sottoinsieme delle transizioni totali.")

    print("\n" + "=" * 70)
    print("AUDIT 6 — SPARSITY ATTRIBUTION")
    print("=" * 70)
    print("""
  Fattore                    Evidenza
  ------------------------   --------------------------------------------------
  Mancanza esecuzioni        79 execute_code_started in ~15 giorni su 5 peer
                            (max 38 in una sessione 'peer58'); ~5/giorno.
  Osservabilità schema       eventi NON-started con payload capability-bearing:
                             vedi Audit 2 (retrieval_event, observation_event,
                             alternate_execution_event trasportano tool/azioni
                             che il prereg ignora per costruzione §2).
  Risoluzione audit          OPERATION_PATTERNS copre 8 pattern → 71/79 (90%)
                             finiscono in unknown/other; 4 cluster totali.
  Frammentazione sessioni    16 sessioni, di cui 8 con ≥2 invocazioni;
                             session_id spesso vuoto o = peer name ('peer58'),
                             quindi il raggruppamento episodi è fragile.
  Combinazione               La sparsità è COMBINATA: poche esecuzioni (a),
                             schema che non cattura tutte le capability (b),
                             risoluzione grossolana (c), sessioni frammentate (d).
""")


if __name__ == "__main__":
    main()
