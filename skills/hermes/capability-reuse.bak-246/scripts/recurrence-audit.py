#!/usr/bin/env python3
"""
recurrence-audit.py — Phase 0.0: Audit historical execute_code usage.
Standalone. No side effects. No behavioral changes to Hermes.

Output:
  - Total execute_code episodes (by session, by day)
  - Top recurring operation clusters
  - Estimated avoidable generation volume
"""
import json, re, os, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

HERMES_HOME = Path.home() / ".hermes"
CACHE_DIR = HERMES_HOME / "cache"
OUTPUT_FILE = HERMES_HOME / "cache" / "recurrence-audit-report.json"

# ── Known operation patterns ──
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

def find_session_logs(home):
    dbs = [home / "state.db", home / "memory_store.db", home / "response_store.db"]
    logs = [(d,) for d in dbs if d.exists()]
    logs += [("jsonl", f) for f in list(home.glob("**/*.jsonl")) + list(home.glob("**/*session*.json")) + list(home.glob("**/*conversation*.json"))]
    return logs

def explore_sqlite(db_path):
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path)); c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in c.fetchall()]
        results = []
        for t in tables:
            c.execute(f"PRAGMA table_info({t});")
            cols = [r[1] for r in c.fetchall()]
            for col in [c for c in cols if c in ('content','text','message','output','input','request')]:
                try:
                    c.execute(f"SELECT {col} FROM {t} WHERE {col} LIKE '%execute_code%' LIMIT 200;")
                    for row in c.fetchall():
                        if row[0]: results.append((db_path.name, t, col, row[0]))
                except: pass
        conn.close(); return results
    except: return []

def classify(code):
    lower = code.lower(); scores = {}
    for name, p in OPERATION_PATTERNS.items():
        score = sum(2 for pat in p["matches"] if re.search(pat, code, re.I)) + sum(1 for kw in p["keywords"] if kw in lower)
        if score: scores[name] = score
    if not scores: return "unknown/other"
    return max(scores, key=scores.get)

def extract_execute_code_snippets(obj):
    """Extract execute_code code strings from structured events or text."""
    snippets = []
    if isinstance(obj, dict):
        tool = str(obj.get("tool") or obj.get("name") or obj.get("tool_name") or obj.get("function") or "")
        if tool == "execute_code":
            for key in ("code", "input", "content"):
                if isinstance(obj.get(key), str): snippets.append(obj[key])
            args = obj.get("arguments") or obj.get("args") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except Exception: pass
            if isinstance(args, dict) and isinstance(args.get("code"), str): snippets.append(args["code"])
        for v in obj.values():
            if isinstance(v, (dict, list)):
                snippets.extend(extract_execute_code_snippets(v))
            elif isinstance(v, str) and "execute_code" in v:
                snippets.extend(extract_execute_code_snippets(v))
        return snippets
    if isinstance(obj, list):
        for item in obj: snippets.extend(extract_execute_code_snippets(item))
        return snippets
    text = obj if isinstance(obj, str) else str(obj or "")
    if not text: return []
    patterns = [
        r'execute_code\s*\(\s*\{\s*["\']code["\']\s*:\s*["\'](.+?)["\']\s*\}',
        r'execute_code\s*\(\s*code\s*=\s*["\'](.+?)["\']\s*\)',
        r'execute_code\s*[:=]\s*["\'](.+?)["\']',
    ]
    for pat in patterns:
        snippets.extend(m.group(1) for m in re.finditer(pat, text, re.S))
    return snippets

def count_in(text):
    if not text: return 0, []
    snippets = extract_execute_code_snippets(text)
    contexts = [{"code_preview": code[:80], "operation": classify(code)} for code in snippets[:20]]
    return len(snippets), contexts

def analyze(logs):
    stats = {"total": 0, "by_op": Counter(), "by_src": Counter(), "sessions": 0, "per_session": []}
    for entry in logs:
        if len(entry) == 2:
            typ, path = entry
        else:
            typ, path = "sqlite", entry[0]
        path = Path(path) if isinstance(path, str) else path[0] if isinstance(path, tuple) else path
        if not path.exists(): continue
        if typ == "sqlite":
            for src, table, col, txt in explore_sqlite(path):
                cnt, ctxs = count_in(txt); stats["total"] += cnt
                for c in ctxs: stats["by_op"][c["operation"]] += 1
                stats["by_src"][f"{path.name}:{table}.{col}"] += cnt
                if cnt: stats["per_session"].append({"source": path.name, "execute_code_count": cnt})
        elif typ == "jsonl":
            try:
                with open(path) as f:
                    for line in f:
                        if not line.strip(): continue
                        try:
                            try:
                                obj = json.loads(line)
                            except Exception:
                                obj = line
                            cnt, ctxs = count_in(obj); stats["total"] += cnt
                            for c in ctxs: stats["by_op"][c["operation"]] += 1
                            if cnt: stats["per_session"].append({"source": path.name, "execute_code_count": cnt})
                        except: pass
            except: pass
        stats["sessions"] += 1
    return stats

def report(stats):
    lines = [f"RECURRENCE AUDIT — Phase 0.0\nSources analyzed: {stats['sessions']}\nTotal execute_code: {stats['total']}\n"]
    top = stats["by_op"].most_common(15)
    lines.append("TOP OPERATIONS:")
    for i, (op, cnt) in enumerate(top, 1):
        pct = (cnt/stats["total"]*100) if stats["total"] else 0
        lines.append(f"  {i}. {op}: {cnt} ({pct:.1f}%)")
    hv = [(op,cnt) for op,cnt in top if cnt>=3 and op!="unknown/other"]
    if hv: lines.append("\nHigh-value reusable clusters (≥3):\n  " + "\n  ".join(f"✅ {op}: {cnt}x" for op,cnt in hv))
    else: lines.append("\nNo high-value clusters yet.")
    avoidable = sum(c for _,c in hv)
    if stats["total"]: lines.append(f"\nAvoidable: {avoidable}/{stats['total']} ({(avoidable/stats['total']*100):.1f}%)")
    return "\n".join(lines)

def main():
    print("Phase 0.0 — Recurrence Audit")
    logs = find_session_logs(HERMES_HOME)
    if not logs: print("No session DB found at expected paths.")
    else:
        for entry in logs:
            typ = entry[0] if len(entry)==2 else "sqlite"
            p = entry[1] if len(entry)==2 else entry[0]
            print(f"  [{typ}] {(Path(p) if isinstance(p,str) else p).name if isinstance(p,(str,Path)) else p}")
    stats = analyze(logs)
    print(f"\nFound: {stats['total']} execute_code in {stats['sessions']} sources")
    print(report(stats))
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    json.dump({"version":"1.2","phase":"0.0","total":stats["total"],"by_operation":[{"op":o,"count":c} for o,c in stats["by_op"].most_common(20)]}, open(OUTPUT_FILE,"w"), indent=2)
    print(f"Saved: {OUTPUT_FILE}")

if __name__ == "__main__": main()
