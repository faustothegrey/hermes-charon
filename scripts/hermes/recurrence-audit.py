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

# ── Known operation patterns (extend as you discover more) ──
OPERATION_PATTERNS = {
    "hmp_healthcheck": {
        "matches": [
            r"curl.*:18643/health",
            r"urlopen.*18643.*health",
            r"hmp.*health",
            r"peer.*health",
        ],
        "keywords": ["health", "healthcheck", "ping", "status"],
    },
    "hmp_send": {
        "matches": [
            r"curl.*:18643/hmp/send",
            r"/hmp/send",
            r"hmp_send",
        ],
        "keywords": ["hmp/send", "send_to_peer", "hmp_send", "payload"],
    },
    "json_parse": {
        "matches": [
            r"json\.loads",
            r"json\.dumps",
            r"parse_json",
        ],
        "keywords": ["json.loads", "json.dumps", "parse json"],
    },
    "ssh_command": {
        "matches": [
            r"ssh\s+fausto@",
            r"ssh\s+root@",
            r"subprocess.*ssh",
        ],
        "keywords": ["ssh", "scp", "remote"],
    },
    "file_read": {
        "matches": [
            r"read_file",
            r"open\(.*\).*read",
            r"Path\(.*\).*read_text",
        ],
        "keywords": ["read file", "read_file", "cat"],
    },
    "hmp_broadcast": {
        "matches": [
            r"broadcast",
            r"all.*peer",
            r"every.*peer",
        ],
        "keywords": ["broadcast", "all peers"],
    },
    "netboard_display": {
        "matches": [
            r"netboard",
            r"display.*msg",
            r"overlay",
        ],
        "keywords": ["netboard", "display"],
    },
    "cron_management": {
        "matches": [
            r"cronjob",
            r"cron.*job",
            r"schedule",
        ],
        "keywords": ["cron", "schedule"],
    },
}

def find_session_logs(hermes_home):
    """Find available conversation/session files."""
    # Hermes stores session data in:
    # 1. SQLite DB at ~/.hermes/state.db or ~/.hermes/memory_store.db
    # 2. Session transcript files in cache/
    # 3. JSONL event logs
    dbs = [
        hermes_home / "state.db",
        hermes_home / "memory_store.db",
        hermes_home / "response_store.db",
    ]
    session_logs = []
    for db in dbs:
        if db.exists():
            session_logs.append(("sqlite", db))
    
    # Also check cache dirs for .json or .jsonl session logs
    cache_files = list(hermes_home.glob("**/*.jsonl")) + \
                  list(hermes_home.glob("**/*session*.json")) + \
                  list(hermes_home.glob("**/*conversation*.json"))
    for f in cache_files:
        session_logs.append(("jsonl", f))
    
    return session_logs

def explore_sqlite(db_path):
    """Try to extract execute_code records from Hermes SQLite DBs."""
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        results = []
        for table in tables:
            try:
                # Get columns
                cursor.execute(f"PRAGMA table_info({table});")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Look for text/content columns containing execute_code
                text_cols = [c for c in columns if c in ('content', 'text', 'message', 'output', 'input', 'request')]
                for col in text_cols:
                    try:
                        cursor.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE '%execute_code%' LIMIT 200;")
                        for row in cursor.fetchall():
                            if row[0]:
                                results.append((db_path.name, table, col, row[0]))
                    except:
                        pass
            except:
                pass
        
        conn.close()
        return results
    except Exception as e:
        return [("error", str(e), "", "")]

def classify_operation(code_text):
    """Classify a code snippet into an operation type."""
    code_lower = code_text.lower()
    
    scores = {}
    for op_name, patterns in OPERATION_PATTERNS.items():
        score = 0
        for pattern in patterns["matches"]:
            if re.search(pattern, code_text, re.IGNORECASE):
                score += 2
        for kw in patterns["keywords"]:
            if kw.lower() in code_lower:
                score += 1
        if score > 0:
            scores[op_name] = score
    
    if not scores:
        return "unknown/other"
    return max(scores, key=scores.get)

def count_execute_code_in_text(text):
    """Count execute_code occurrences and extract context."""
    if not text:
        return 0, []
    
    # Count execute_code tool calls
    matches = list(re.finditer(
        r'(?:execute_code|terminal)\s*(?:\(|\{)\s*(?:\n\s*)?(?:code|command)\s*[:=]\s*["\']([^"\']+)',
        text
    ))
    
    contexts = []
    for m in matches[:20]:
        code = m.group(1)[:200]
        op = classify_operation(code)
        contexts.append({"code_preview": code[:80], "operation": op})
    
    return len(matches), contexts

def analyze_session_files(session_logs):
    """Analyze all available session data for execute_code frequency."""
    stats = {
        "total_execute_code_calls": 0,
        "by_operation": Counter(),
        "by_source": Counter(),
        "sessions_analyzed": 0,
        "per_session_counts": [],
    }
    
    for log_type, path in session_logs:
        if log_type == "sqlite":
            records = explore_sqlite(path)
            for source, table, col, text in records:
                if source == "error":
                    continue
                count, contexts = count_execute_code_in_text(text)
                stats["total_execute_code_calls"] += count
                for ctx in contexts:
                    stats["by_operation"][ctx["operation"]] += 1
                stats["by_source"][f"{path.name}:{table}.{col}"] += count
                if count > 0:
                    stats["per_session_counts"].append({
                        "source": path.name,
                        "table": table,
                        "execute_code_count": count,
                    })
        
        elif log_type == "jsonl":
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            text = json.dumps(data)
                            count, contexts = count_execute_code_in_text(text)
                            if count > 0:
                                stats["total_execute_code_calls"] += count
                                for ctx in contexts:
                                    stats["by_operation"][ctx["operation"]] += 1
                                stats["by_source"][path.name] += count
                                stats["per_session_counts"].append({
                                    "source": path.name,
                                    "execute_code_count": count,
                                })
                        except:
                            pass
            except:
                pass
        
        stats["sessions_analyzed"] += 1
    
    return stats

def generate_report(stats):
    """Generate the audit report."""
    total = stats["total_execute_code_calls"]
    top_ops = stats["by_operation"].most_common(15)
    
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("RECURRENCE AUDIT REPORT — Phase 0.0")
    report_lines.append(f"Generated: {datetime.now().isoformat()}")
    report_lines.append(f"Sources analyzed: {stats['sessions_analyzed']}")
    report_lines.append("=" * 70)
    report_lines.append("")
    
    report_lines.append(f"📊 TOTAL execute_code CALLS FOUND: {total}")
    report_lines.append("")
    
    report_lines.append("🏆 TOP 15 OPERATION CLUSTERS:")
    report_lines.append(f"  {'#':<3} {'Operation':<25} {'Count':<8} {'% of total':<12}")
    report_lines.append(f"  {'-'*3} {'-'*25} {'-'*8} {'-'*12}")
    for i, (op, cnt) in enumerate(top_ops, 1):
        pct = (cnt / total * 100) if total > 0 else 0
        report_lines.append(f"  {i:<3} {op:<25} {cnt:<8} {pct:.1f}%")
    
    report_lines.append("")
    report_lines.append("📂 BY SOURCE:")
    for src, cnt in stats["by_source"].most_common(10):
        report_lines.append(f"  {src}: {cnt} calls")
    
    # Recurrence analysis
    report_lines.append("")
    report_lines.append("🔄 RECURRENCE ANALYSIS:")
    high_value = [(op, cnt) for op, cnt in top_ops if cnt >= 3 and op != "unknown/other"]
    high_value.sort(key=lambda x: -x[1])
    
    if high_value:
        report_lines.append(f"  High-value reusable clusters (≥3 occurrences):")
        for op, cnt in high_value:
            report_lines.append(f"    ✅ {op}: {cnt} occurrences — good harness candidate")
    else:
        report_lines.append("  ⚠️  No high-value reusable clusters yet (need ≥3 occurrences)")
    
    report_lines.append("")
    report_lines.append("🎯 ESTIMATED AVOIDABLE GENERATION:")
    avoidable = sum(cnt for op, cnt in top_ops if cnt >= 3 and op != "unknown/other")
    if total > 0:
        avoidable_pct = (avoidable / total * 100)
        report_lines.append(f"  {avoidable}/{total} calls ({avoidable_pct:.1f}%) could potentially")
        report_lines.append(f"  be served by registered capabilities repeating ≥3 times.")
    else:
        report_lines.append("  N/A — no execute_code calls found in available sources.")
    
    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 70)
    
    return "\n".join(report_lines)

def main():
    print("🔍 Phase 0.0 — Recurrence Audit")
    print(f"   Hermes home: {HERMES_HOME}")
    print()
    
    # 1. Discover sources
    print("📁 Discovering session data sources...")
    logs = find_session_logs(HERMES_HOME)
    if not logs:
        print("   ⚠️  No Hermes DB or session logs found at expected paths.")
        print("   Hermes stores sessions in an internal format not directly")
        print("   queryable from disk. Consider these approaches:")
        print("   1. Use session_search() via Hermes API to query past conversations")
        print("   2. Enable session JSONL logging in Hermes config")
        print("   3. Run this script periodically as forward-collection starts")
    else:
        print(f"   Found {len(logs)} source(s):")
        for typ, path in logs:
            size = path.stat().st_size if path.exists() else 0
            print(f"     [{typ}] {path.name} ({size:,} bytes)")
    
    print()
    print("🔬 Analyzing for execute_code patterns...")
    stats = analyze_session_files(logs)
    
    print(f"   Total execute_code calls found: {stats['total_execute_code_calls']}")
    print(f"   Sessions analyzed: {stats['sessions_analyzed']}")
    
    # 2. Generate report
    report = generate_report(stats)
    print()
    print(report)
    
    # 3. Save report
    report_data = {
        "version": "1.2",
        "phase": "0.0",
        "generated_at": datetime.now().isoformat(),
        "total_execute_code_calls": stats["total_execute_code_calls"],
        "sessions_analyzed": stats["sessions_analyzed"],
        "by_operation": [{"operation": op, "count": cnt} for op, cnt in stats["by_operation"].most_common(20)],
        "by_source": [{"source": src, "count": cnt} for src, cnt in stats["by_source"].most_common(10)],
        "high_value_clusters": [
            {"operation": op, "count": cnt}
            for op, cnt in stats["by_operation"].most_common(20)
            if cnt >= 3 and op != "unknown/other"
        ],
    }
    
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"📝 Report saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
