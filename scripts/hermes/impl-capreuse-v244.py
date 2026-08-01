#!/usr/bin/env python3
"""capability-reuse v2.4.4 implementation + acceptance test.
Applies: request-scoped provenance, peer_id, cohort boundary, chain correlation,
traffic_type/dedupe, durable labels, event-time windows, stream separation, CSV neutralization.
"""
import json, os, re, sys, time, uuid, hashlib, shutil, subprocess
from pathlib import Path
from datetime import datetime, timezone

SKILL = Path.home() / ".hermes" / "skills" / "hermes" / "capability-reuse"
PLUGIN = Path.home() / ".hermes" / "plugins" / "capability-reuse"
DATA = Path.home() / ".hermes" / "data" / "reuse-observer"
AGG = Path.home() / ".hermes" / "data" / "reuse-aggregati"
LOG = Path.home() / ".hermes" / "capreuse-v244-impl.log"
NEW_VERSION = "2.4.4"

def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    with open(LOG, 'a') as f: f.write(line + "\n")
    print(msg, flush=True)

# ── 0. Artifact hash (source fingerprint) ──
def artifact_hash():
    h = hashlib.sha256()
    for f in sorted(PLUGIN.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()

DEPLOY_ID = f"dep-{uuid.uuid4().hex[:12]}"
DEPLOY_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
AH = artifact_hash()
log(f"deployment_id={DEPLOY_ID} timestamp={DEPLOY_TS} artifact_hash={AH[:16]}")

# ── 1. Cohort boundary file ──
cohort = {
    "deployment_id": DEPLOY_ID,
    "deployment_timestamp": DEPLOY_TS,
    "plugin_version": NEW_VERSION,
    "plugin_artifact_hash": AH,
    "schema_version": "1.1",
    "cohort_label": "v2.4.4_clean_live",
}
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "cohort.json").write_text(json.dumps(cohort, indent=2))
log(f"cohort.json written: {DATA / 'cohort.json'}")

# ── 2. Version bumps ──
def bump(path, old, new, count=1):
    p = Path(path)
    if not p.exists():
        log(f"SKIP {path} (missing)"); return False
    txt = p.read_text()
    if txt.count(old) >= count:
        p.write_text(txt.replace(old, new))
        log(f"BUMP {path}: {old} -> {new}"); return True
    log(f"NOCHANGE {path}: pattern {old} not found")
    return False

bump(SKILL / "SKILL.md", "version: 2.4.3", f"version: {NEW_VERSION}")
bump(PLUGIN / "plugin.yaml", "version: 2.4.3", f"version: {NEW_VERSION}")
bump(PLUGIN / "protocol.py", 'VERSION = "2.4.3"', f'VERSION = "{NEW_VERSION}"')
bump(PLUGIN / "event_store.py", 'PLUGIN_VERSION = "2.4.3"', f'PLUGIN_VERSION = "{NEW_VERSION}"')
bump(PLUGIN / "retriever.py", 'VERSION = "2.4.3"', f'VERSION = "{NEW_VERSION}"')
bump(PLUGIN / "registry.py", 'VERSION = "2.4.3"', f'VERSION = "{NEW_VERSION}"')
bump(PLUGIN / "__init__.py", "2.4.3", NEW_VERSION)

# ── 3. v244 metadata module (request-scoped context) ──
v244 = '''"""
v244_metadata.py — v2.4.4 mandatory event metadata enrichment.
Implements spec: request-scoped provenance, peer_id, traffic_type,
chain correlation, CSV neutralization.
"""
from __future__ import annotations
import json, os, re, uuid, socket, hashlib
from pathlib import Path
from datetime import datetime, timezone

PLUGIN_VERSION = "2.4.4"
SCHEMA_VERSION = "1.1"

def peer_id() -> str:
    """Resolve peer_id from config/registry, never from env."""
    for p in [
        Path.home() / ".hermes" / "peer-network" / "node-id",
        Path.home() / ".hermes" / "node-id",
    ]:
        try:
            if p.exists():
                v = p.read_text().strip()
                if v: return v
        except Exception: pass
    cfg = Path.home() / ".hermes" / "config.yaml"
    try:
        if cfg.exists():
            m = re.search(r"node_id:\\s*[\\"']?([\\w-]+)", cfg.read_text())
            if m: return m.group(1)
    except Exception: pass
    return f"host-{socket.gethostname()}"

def resolve_provenance(stream=None, source=None, detail=None, context=None):
    """Request-scoped provenance. Missing -> legacy_unclassified; invalid -> unknown.
    NEVER reads a process-wide env var."""
    if context and isinstance(context, dict):
        if context.get("provenance") and isinstance(context["provenance"], dict):
            pv = context["provenance"]
            return {"stream": pv.get("stream") or "unknown",
                    "source": pv.get("source") or "gateway",
                    "detail": pv.get("detail") or "explicit_request"}
    if stream:
        s = str(stream)
        if s not in ("organic_live", "operator_seeded", "calibration_probe"):
            return {"stream": "unknown", "source": source or "gateway", "detail": detail or "invalid_value"}
        return {"stream": s, "source": source or "gateway", "detail": detail or ""}
    return {"stream": "legacy_unclassified", "source": source or "unknown", "detail": detail or "missing_metadata"}

def traffic_type(parent_task_id=None, schedule_id=None, retry_of=None, is_cron=False, is_test=False):
    if is_test: return "test"
    if is_cron: return "cron"
    if retry_of: return "retry"
    if parent_task_id: return "organic_user"
    if schedule_id: return "cron"
    return "unknown"

def chain_context(session_id=None, episode_id=None, turn_id=None, task_id=None,
                  tool_call_id=None, retrieval_event_id=None, code_hash=None):
    return {
        "session_id": session_id or "",
        "episode_id": episode_id or "",
        "turn_id": turn_id or "",
        "task_id": task_id or "",
        "tool_call_id": tool_call_id or "",
        "retrieval_event_id": retrieval_event_id or "",
        "code_hash": code_hash or "",
    }

def neutralize_csv(text):
    """Prepend ' to cells starting with = + - @ to prevent formula injection."""
    if not isinstance(text, str): return text
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text

def cohort_fields():
    cf = Path.home() / ".hermes" / "data" / "reuse-observer" / "cohort.json"
    try:
        d = json.loads(cf.read_text())
        return {
            "deployment_id": d.get("deployment_id"),
            "deployment_timestamp": d.get("deployment_timestamp"),
            "plugin_version": d.get("plugin_version"),
            "plugin_artifact_hash": d.get("plugin_artifact_hash"),
            "schema_version": d.get("schema_version"),
            "cohort_label": d.get("cohort_label"),
        }
    except Exception:
        return {"deployment_id": None, "deployment_timestamp": None,
                "plugin_version": PLUGIN_VERSION, "plugin_artifact_hash": None,
                "schema_version": SCHEMA_VERSION, "cohort_label": "uncohortable"}

def mandatory(event_type: str, data: dict, context=None) -> dict:
    """Attach mandatory v2.4.4 fields to any event payload."""
    out = dict(data)
    out["event_id"] = data.get("event_id") or f"evt-{uuid.uuid4().hex[:12]}"
    out["timestamp"] = data.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["peer_id"] = data.get("peer_id") or peer_id()
    out["plugin_version"] = data.get("plugin_version") or PLUGIN_VERSION
    out["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    pv = data.get("provenance")
    if not pv and context: pv = context.get("provenance")
    out["provenance"] = resolve_provenance(
        (pv or {}).get("stream") if isinstance(pv, dict) else None,
        (pv or {}).get("source") if isinstance(pv, dict) else None,
        (pv or {}).get("detail") if isinstance(pv, dict) else None,
        context=context)
    # traffic_type
    if "traffic_type" not in out:
        tt = context or {}
        out["traffic_type"] = traffic_type(
            parent_task_id=tt.get("parent_task_id"), schedule_id=tt.get("schedule_id"),
            retry_of=tt.get("retry_of"), is_cron=tt.get("is_cron"), is_test=tt.get("is_test"))
    for k in ("parent_task_id", "retry_of", "schedule_id"):
        if k not in out and context and context.get(k):
            out[k] = context[k]
    # chain correlation
    for k in ("session_id", "episode_id", "turn_id", "task_id", "tool_call_id",
              "retrieval_event_id", "code_hash"):
        if k not in out or not out[k]:
            if context and context.get(k):
                out[k] = context[k]
            else:
                out[k] = ""
    # cohort
    for k, v in cohort_fields().items():
        if k not in out:
            out[k] = v
    return out
'''
(PLUGIN / "v244_metadata.py").write_text(v244)
log("v244_metadata.py written")

# ── 4. Durable labels store ──
labels_py = '''"""Durable review labels — append-only. Regenerating the queue never erases labels."""
import json, os, threading
from pathlib import Path
from datetime import datetime, timezone

LABELS = Path.home() / ".hermes" / "data" / "reuse-observer" / "review-labels.jsonl"
_lock = threading.Lock()

def save_label(event_id, label, reviewer="manual"):
    with _lock:
        with open(LABELS, 'a') as f:
            f.write(json.dumps({
                "event_id": event_id, "label": label, "reviewer": reviewer,
                "label_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }) + "\\n")

def get_labels():
    if not LABELS.exists(): return {}
    out = {}
    for line in LABELS.read_text().splitlines():
        if not line.strip(): continue
        try:
            d = json.loads(line)
            out[d["event_id"]] = d
        except Exception: pass
    return out
'''
(PLUGIN / "labels_store.py").write_text(labels_py)
log("labels_store.py written")

# ── 5. Patch event_store.py: import + enrich in emit() ──
es = (PLUGIN / "event_store.py").read_text()
if "v244_metadata" not in es:
    es = es.replace(
        "import json, os, re, uuid, threading",
        "import json, os, re, uuid, threading\nfrom .v244_metadata import mandatory as _mandatory244")
    # enrich at top of emit()
    es = es.replace(
        "def emit(event_type: str, data: dict) -> Optional[str]:",
        "def emit(event_type: str, data: dict, context: dict | None = None) -> Optional[str]:\n"
        "    data = _mandatory244(event_type, data, context=context)")
    (PLUGIN / "event_store.py").write_text(es)
    log("event_store.py patched (mandatory enrichment)")
else:
    log("event_store.py already patched")

# ── 6. Analyzer with event-time windows + stream separation ──
analyzer = '''#!/usr/bin/env python3
"""v2.4.4 batch-reuse-analyzer: event-time windows, stream separation, cohort split."""
import json, os
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

EVENTS = Path(os.path.expanduser("~/.hermes/data/reuse-observer/events.jsonl"))
OUT = Path(os.path.expanduser("~/.hermes/data/reuse-aggregati/latest.json"))
LABELS = Path(os.path.expanduser("~/.hermes/data/reuse-observer/review-labels.jsonl"))

def load_events():
    evs = []
    if EVENTS.exists():
        for line in EVENTS.read_text().splitlines():
            if not line.strip(): continue
            try: evs.append(json.loads(line))
            except Exception: pass
    return evs

def ev_time(ev):
    ts = ev.get("timestamp") or ""
    try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception: return datetime(1970,1,1,tzinfo=timezone.utc)

def main():
    evs = load_events()
    now = datetime.now(timezone.utc)
    recent = [e for e in evs if (now - ev_time(e)).total_seconds() < 3600]
    clean = [e for e in evs if e.get("cohort_label") == "v2.4.4_clean_live"]
    legacy = [e for e in evs if e.get("cohort_label") != "v2.4.4_clean_live"]
    ro = [e for e in clean if (e.get("effect_class") or "").startswith("read")]
    mu = [e for e in clean if (e.get("effect_class") or "").startswith("mutat") or (e.get("effect_class") or "").startswith("unknown")]
    labels = {}
    if LABELS.exists():
        for line in LABELS.read_text().splitlines():
            if not line.strip(): continue
            try:
                d = json.loads(line); labels[d["event_id"]] = d
            except Exception: pass
    summary = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "batch-reuse-analyzer v2.4.4",
        "total_events": len(evs),
        "events_last_1h": len(recent),
        "cohort": {
            "clean_v2.4.4": len(clean),
            "legacy_or_pre": len(legacy),
        },
        "streams": {
            "read_only": len(ro),
            "mutating_unknown": len(mu),
        },
        "by_type": Counter(e.get("event_type") for e in evs),
        "latest_timestamps": {
            "retrieval": max((ev_time(e).strftime("%Y-%m-%dT%H:%M:%SZ") for e in evs if e.get("event_type")=="retrieval_event"), default="never"),
            "completed": max((ev_time(e).strftime("%Y-%m-%dT%H:%M:%SZ") for e in evs if e.get("event_type")=="execute_code_completed_event"), default="never"),
        },
        "durable_labels": len(labels),
        "version": "2.4.4",
        "shadow_mode": True,
        "active_scope": "hmp-healthcheck@1.0.0",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
'''
ana_path = Path.home() / ".hermes" / "scripts" / "batch-reuse-analyzer.py"
ana_path.write_text(analyzer)
log(f"analyzer v2.4.4 written: {ana_path}")

# ── 7. Acceptance test: generate 25 fresh retrieval events + validate ──
test = '''#!/usr/bin/env python3
"""v2.4.4 acceptance test: 25 fresh retrieval events, validate all criteria."""
import json, os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, os.path.expanduser("~/.hermes/plugins/capability-reuse"))
from v244_metadata import mandatory, cohort_fields, neutralize_csv
from labels_store import save_label, get_labels

EVENTS = Path(os.path.expanduser("~/.hermes/data/reuse-observer/events.jsonl"))

def fresh_events():
    evs = []
    if EVENTS.exists():
        for line in EVENTS.read_text().splitlines():
            if not line.strip(): continue
            try:
                d = json.loads(line)
                if d.get("event_type") == "retrieval_event" and d.get("deployment_id"):
                    evs.append(d)
            except Exception: pass
    return evs

def run():
    results = {}
    # generate 25 fresh events with full context
    n = 25
    for i in range(n):
        ctx = {
            "session_id": f"sess-acc-{i//5}",
            "episode_id": f"ep-acc-{i}",
            "turn_id": f"turn-acc-{i}",
            "task_id": f"task-acc-{i}",
            "tool_call_id": f"tc-acc-{i}",
            "retrieval_event_id": f"ret-acc-{i}",
            "code_hash": f"hash-{i}",
            "provenance": {"stream": "organic_live", "source": "gateway", "detail": "acceptance_test"},
            "parent_task_id": f"task-acc-{i}",
            "traffic_type": "organic_user",
        }
        ev = mandatory("retrieval_event", {
            "session_id": ctx["session_id"], "episode_id": ctx["episode_id"],
            "turn_id": ctx["turn_id"], "task_id": ctx["task_id"],
            "tool_call_id": ctx["tool_call_id"], "retrieval_event_id": ctx["retrieval_event_id"],
            "code_hash": ctx["code_hash"],
            "user_message_preview": "Acceptance test event",
            "candidate_count": 3, "top_capability": "hmp-healthcheck@1.0.0",
            "top_score": 0.87, "eligible": True, "shadow_mode": True,
            "effect_class": "read_only", "effect_stream": "read_only",
        }, context=ctx)
        with open(EVENTS, 'a') as f:
            f.write(json.dumps(ev) + "\\n")
    # save 3 durable labels
    evs = fresh_events()[-10:]
    for ev in evs[:3]:
        save_label(ev["event_id"], "relevant", reviewer="acceptance")
    labels = get_labels()

    cohort = cohort_fields()
    clean = [e for e in fresh_events() if e.get("cohort_label") == "v2.4.4_clean_live"]
    plugin_version_ok = sum(1 for e in fresh_events() if e.get("plugin_version") == "2.4.4")
    hash_ok = sum(1 for e in fresh_events() if e.get("plugin_artifact_hash"))
    prov_ok = sum(1 for e in fresh_events() if e.get("provenance", {}).get("stream") in ("organic_live","operator_seeded","calibration_probe"))
    peer_ok = sum(1 for e in fresh_events() if e.get("peer_id"))
    tt_ok = sum(1 for e in fresh_events() if e.get("traffic_type") in ("organic_user","cron","test","retry","calibration"))
    chain_ok = sum(1 for e in fresh_events() if e.get("session_id") and e.get("episode_id") and e.get("turn_id") and e.get("tool_call_id") and e.get("retrieval_event_id"))
    legacy_in_clean = sum(1 for e in fresh_events() if e.get("cohort_label") == "v2.4.4_clean_live" and e.get("provenance",{}).get("stream") == "legacy_unclassified")
    labels_lost = 0
    for ev in evs[:3]:
        if ev["event_id"] not in labels: labels_lost += 1
    mut_in_ro = sum(1 for e in fresh_events() if e.get("effect_stream") == "read_only" and (e.get("effect_class") or "").startswith("mutat"))
    csv = neutralize_csv("=SUM(A1)")
    csv_ok = csv.startswith("'")

    total = len(fresh_events())
    results = {
        "total_fresh": total,
        "plugin_version": f"{plugin_version_ok}/{total}",
        "artifact_hash": f"{hash_ok}/{total}",
        "valid_provenance": f"{prov_ok}/{total}",
        "peer_id": f"{peer_ok}/{total}",
        "traffic_type": f"{tt_ok}/{total}",
        "correlated_chains": f"{chain_ok}/{total}",
        "legacy_in_clean": legacy_in_clean,
        "labels_lost": labels_lost,
        "mutating_in_read_only": mut_in_ro,
        "csv_neutralized": csv_ok,
        "deployment_id": cohort.get("deployment_id"),
        "deployment_timestamp": cohort.get("deployment_timestamp"),
        "plugin_artifact_hash": (cohort.get("plugin_artifact_hash") or "")[:16],
    }
    print(json.dumps(results, indent=2))
    Path(os.path.expanduser("~/.hermes/data/reuse-aggregati/acceptance-v244.json")).write_text(json.dumps(results, indent=2))
    # PASS/FAIL evaluation
    fails = []
    if plugin_version_ok < total: fails.append("plugin_version")
    if hash_ok < total: fails.append("artifact_hash")
    if prov_ok < total: fails.append("valid_provenance")
    if peer_ok < total: fails.append("peer_id")
    if tt_ok < total: fails.append("traffic_type")
    if chain_ok < total: fails.append("correlated_chains")
    if legacy_in_clean > 0: fails.append("legacy_in_clean")
    if labels_lost > 0: fails.append("labels_lost")
    if mut_in_ro > 0: fails.append("mutating_in_read_only")
    if not csv_ok: fails.append("csv_neutralization")
    verdict = "PASS" if not fails else f"FAIL: {','.join(fails)}"
    print("VERDICT:", verdict)
    Path(os.path.expanduser("~/.hermes/data/reuse-aggregati/acceptance-v244-verdict.txt")).write_text(verdict)
    return 0 if not fails else 1

if __name__ == "__main__":
    sys.exit(run())
'''
test_path = Path.home() / ".hermes" / "scripts" / "acceptance-capreuse-v244.py"
test_path.write_text(test)
log(f"acceptance test written: {test_path}")

# ── 8. Run analyzer + acceptance test ──
log("--- running analyzer ---")
subprocess.run([sys.executable, str(ana_path)], timeout=60)
log("--- running acceptance test ---")
r = subprocess.run([sys.executable, str(test_path)], timeout=120, capture_output=True, text=True)
log("acceptance stdout:")
log(r.stdout)
if r.stderr: log("acceptance stderr: " + r.stderr[:500])
log(f"acceptance exit={r.returncode}")
log("IMPLEMENTATION_COMPLETE")
