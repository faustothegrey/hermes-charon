#!/usr/bin/env python3
"""
code-fingerprint.py — Phase 0.4: Post-execution fingerprint extraction.
Extracts three fingerprints from generated code:
  1) syntax_fingerprint  — normalized AST structure
  2) capability_fingerprint — libraries, tools, protocols
  3) effect_fingerprint  — observed side effects

Standalone. No behavioral changes. Input: code string. Output: fingerprint dict.
"""
import ast, re, json, sys
from pathlib import Path
from collections import Counter

def syntax_fingerprint(code):
    """Normalized AST: imports, control flow, tool calls, variable patterns."""
    fp = {
        "imports": [],
        "calls": [],
        "control_flow": [],
        "has_loop": False,
        "has_conditional": False,
        "has_try_except": False,
        "has_nested_function": False,
        "max_depth": 0,
        "total_statements": 0,
        "string_literals_count": 0,
        "url_literals": [],
    }
    try:
        tree = ast.parse(code)
    except SyntaxError:
        fp["parse_error"] = True
        return fp

    fp["total_statements"] = sum(1 for _ in ast.walk(tree) if isinstance(_, ast.stmt))

    for node in ast.walk(tree):
        depth = _depth(node) if hasattr(node, 'body') else 0
        fp["max_depth"] = max(fp["max_depth"], depth)

        if isinstance(node, ast.Import):
            fp["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            fp["imports"].append(f"{node.module}.{node.names[0].name}" if node.names else node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fp["calls"].append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                fp["calls"].append(f"{_attr_chain(node.func)}")
        elif isinstance(node, ast.For) or isinstance(node, ast.While):
            fp["has_loop"] = True
            fp["control_flow"].append("loop")
        elif isinstance(node, ast.If):
            fp["has_conditional"] = True
            fp["control_flow"].append("conditional")
        elif isinstance(node, ast.Try):
            fp["has_try_except"] = True
            fp["control_flow"].append("try_except")
        elif isinstance(node, ast.FunctionDef):
            fp["has_nested_function"] = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            fp["string_literals_count"] += 1
            # Detect URLs
            if re.match(r'https?://', node.value):
                fp["url_literals"].append(node.value[:100])

    fp["imports"] = list(set(fp["imports"]))
    fp["calls"] = list(set(fp["calls"]))
    fp["url_literals"] = list(set(fp["url_literals"]))
    fp["control_flow"] = list(set(fp["control_flow"]))
    return fp

def _depth(node, d=0):
    if not hasattr(node, 'body') or not node.body:
        return d
    return max(_depth(child, d+1) for child in node.body if hasattr(child, 'body'))

def _attr_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))

def capability_fingerprint(code):
    """Extract libraries, tools, protocols, and operation classes."""
    fp = {
        "libraries": [],
        "hermes_tools": [],
        "protocols": [],
        "operation_classes": [],
        "has_json": False,
        "has_subprocess": False,
        "has_requests": False,
        "has_sqlite": False,
    }
    lower = code.lower()

    # Libraries from imports
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    fp["libraries"].append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    fp["libraries"].append(node.module.split(".")[0])
    except SyntaxError:
        pass

    # Hermes tools
    for tool in ["terminal", "read_file", "write_file", "search_files", "web_search",
                 "web_extract", "execute_code", "patch", "cronjob", "skill_view",
                 "memory", "session_search", "image_generate", "text_to_speech",
                 "vision_analyze", "delegate_task", "browser_navigate", "clarify"]:
        if tool in code:
            fp["hermes_tools"].append(tool)

    # Protocols
    if "http://" in code or "https://" in code: fp["protocols"].append("http")
    if "18643" in code: fp["protocols"].append("hmp")
    if "8642" in code: fp["protocols"].append("hermes_api")
    if "ssh" in lower: fp["protocols"].append("ssh")

    # Operation classes
    if "health" in lower or "ping" in lower: fp["operation_classes"].append("healthcheck")
    if "hmp/send" in code or "hmp.send" in code: fp["operation_classes"].append("hmp_send")
    if "json.loads" in code or "json.dumps" in code: fp["operation_classes"].append("json_processing")
    if "cronjob" in code: fp["operation_classes"].append("cron_management")
    if "scp" in code: fp["operation_classes"].append("file_transfer")
    if "broadcast" in lower: fp["operation_classes"].append("broadcast")
    if "search" in lower: fp["operation_classes"].append("search")
    if "write" in lower: fp["operation_classes"].append("write")
    if "delete" in lower or "rm " in lower: fp["operation_classes"].append("delete")

    fp["has_json"] = "json.loads" in code or "json.dumps" in code
    fp["has_subprocess"] = "subprocess" in code
    fp["has_requests"] = "requests." in code
    fp["has_sqlite"] = "sqlite3" in code

    fp["libraries"] = list(set(fp["libraries"]))
    return fp

def effect_fingerprint(code, execution_trace=None):
    """Estimate side effects from code analysis."""
    fp = {
        "filesystem_read": False,
        "filesystem_write": False,
        "network_read": False,
        "network_write": False,
        "process_spawn": False,
        "remote_mutation": False,
        "unknown_effects": False,
        "effect_class": "unknown",
        "observation_coverage": {
            "filesystem": "code_pattern",
            "process": "code_pattern",
            "network": "code_pattern",
            "remote_mutation": "none"
        }
    }

    lower = code.lower()
    # Filesystem
    if "read_file" in code or "open(" in code: fp["filesystem_read"] = True
    if "write_file" in code or ".write(" in code: fp["filesystem_write"] = True

    # Network
    if "urlopen" in code or "curl" in code or "requests." in code: fp["network_read"] = True
    if "POST" in code or "send" in lower: fp["network_write"] = True
    if "scp" in code or "sftp" in code: fp["remote_mutation"] = True

    # Process
    if "subprocess" in code or "Popen" in code: fp["process_spawn"] = True
    if "terminal(" in code: fp["process_spawn"] = True

    # Unknown
    if "exec(" in code or "eval(" in code: fp["unknown_effects"] = True

    # Overall class
    if fp["remote_mutation"]:
        fp["effect_class"] = "mutating"
    elif fp["filesystem_write"] or fp["process_spawn"]:
        fp["effect_class"] = "likely_mutating"
    elif fp["network_read"] or fp["filesystem_read"]:
        fp["effect_class"] = "read_only"
    else:
        fp["effect_class"] = "unknown"

    return fp

def extract(code, execution_trace=None):
    """Extract all three fingerprints from a code string."""
    return {
        "syntax": syntax_fingerprint(code),
        "capability": capability_fingerprint(code),
        "effect": effect_fingerprint(code, execution_trace),
    }

def format_report(fp):
    """Human-readable fingerprint report."""
    lines = []
    lines.append("━" * 50)
    lines.append("CODE FINGERPRINT REPORT")
    lines.append("━" * 50)

    lines.append(f"\n📦 CAPABILITY FINGERPRINT:")
    lines.append(f"  Libraries:    {', '.join(fp['capability']['libraries']) or '(none)'}")
    lines.append(f"  Hermes tools: {', '.join(fp['capability']['hermes_tools']) or '(none)'}")
    lines.append(f"  Protocols:    {', '.join(fp['capability']['protocols']) or '(none)'}")
    lines.append(f"  Operations:   {', '.join(fp['capability']['operation_classes']) or '(none)'}")

    lines.append(f"\n⚡ EFFECT FINGERPRINT:")
    lines.append(f"  Class:        {fp['effect']['effect_class']}")
    lines.append(f"  FS read:      {'✅' if fp['effect']['filesystem_read'] else '⬜'}")
    lines.append(f"  FS write:     {'✅' if fp['effect']['filesystem_write'] else '⬜'}")
    lines.append(f"  Network r/w:  {'✅' if fp['effect']['network_read'] else '⬜'}/{'✅' if fp['effect']['network_write'] else '⬜'}")
    lines.append(f"  Process:      {'✅' if fp['effect']['process_spawn'] else '⬜'}")
    lines.append(f"  Remote mut:   {'✅' if fp['effect']['remote_mutation'] else '⬜'}")

    lines.append(f"\n📐 SYNTAX FINGERPRINT:")
    lines.append(f"  Statements:   {fp['syntax']['total_statements']}")
    lines.append(f"  Max depth:    {fp['syntax']['max_depth']}")
    lines.append(f"  Loop:         {'✅' if fp['syntax']['has_loop'] else '⬜'}")
    lines.append(f"  Try/except:   {'✅' if fp['syntax']['has_try_except'] else '⬜'}")
    lines.append(f"  Imports:      {', '.join(fp['syntax']['imports'][:8]) or '(none)'}")
    lines.append(f"  Calls:        {', '.join(fp['syntax']['calls'][:10]) or '(none)'}")
    if fp['syntax']['url_literals']:
        lines.append(f"  URLs:         {', '.join(fp['syntax']['url_literals'][:3])}")

    lines.append("\n" + "━" * 50)
    return "\n".join(lines)

def main():
    if len(sys.argv) > 1:
        # Read code from file argument
        path = Path(sys.argv[1])
        if path.exists():
            code = path.read_text()
        else:
            code = sys.argv[1]
    else:
        # Read from stdin
        code = sys.stdin.read()

    if not code.strip():
        print("Usage: python3 code-fingerprint.py <file_or_code>")
        print("   or: echo 'code' | python3 code-fingerprint.py")
        sys.exit(1)

    fp = extract(code)
    print(format_report(fp))

    # Also save
    out_dir = Path.home() / ".hermes" / "data" / "reuse-observer" / "fingerprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"fp_{abs(hash(code))}.json"
    out_path.write_text(json.dumps(fp, indent=2))
    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    main()
