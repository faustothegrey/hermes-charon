#!/usr/bin/env python3
"""
code-fingerprint.py — Phase 0.4: conservative static post-execution hints.
Static output is a hint, not observed truth.
"""
import ast, hashlib, json, re, sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

WRITE_METHODS = {"post", "put", "patch", "delete", "request"}
READ_METHODS = {"get", "head", "options", "urlopen", "urlretrieve"}
FS_READ_METHODS = {"read", "read_text", "read_bytes"}
FS_WRITE_METHODS = {"write", "write_text", "write_bytes", "touch", "mkdir", "unlink", "rename", "replace"}


def _attr(n):
    parts=[]
    while isinstance(n,ast.Attribute):
        parts.append(n.attr); n=n.value
    if isinstance(n,ast.Name): parts.append(n.id)
    return ".".join(reversed(parts))


def _depth(n,d=0):
    children = [c for c in getattr(n, 'body', []) if hasattr(c, 'body')]
    if not children:
        return d
    return max([d] + [_depth(c, d+1) for c in children])


def _redact_url(u):
    try:
        sp=urlsplit(u)
        netloc=sp.hostname or ""
        if sp.port: netloc += f":{sp.port}"
        return urlunsplit((sp.scheme, netloc, sp.path, "[REDACTED]" if sp.query else "", ""))
    except Exception:
        return "[URL]"


def syntax_fingerprint(code):
    fp = {"imports":[],"calls":[],"control_flow":[],"has_loop":False,"has_conditional":False,
          "has_try_except":False,"has_nested_function":False,"max_depth":0,"total_statements":0,
          "string_literals_count":0,"url_literals":[]}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        fp["parse_error"] = True
        return fp
    fp["total_statements"] = sum(1 for n in ast.walk(tree) if isinstance(n, ast.stmt))
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            fp["max_depth"] = max(fp["max_depth"], _depth(n))
        if isinstance(n,ast.Import): fp["imports"].extend(a.name for a in n.names)
        elif isinstance(n,ast.ImportFrom): fp["imports"].append(f"{n.module}" if n.module else "")
        elif isinstance(n,ast.Call):
            if isinstance(n.func,ast.Name): fp["calls"].append(n.func.id)
            elif isinstance(n.func,ast.Attribute): fp["calls"].append(_attr(n.func))
        elif isinstance(n,(ast.For,ast.While)): fp["has_loop"]=True; fp["control_flow"].append("loop")
        elif isinstance(n,ast.If): fp["has_conditional"]=True; fp["control_flow"].append("conditional")
        elif isinstance(n,ast.Try): fp["has_try_except"]=True; fp["control_flow"].append("try_except")
        elif isinstance(n,ast.FunctionDef) and n.col_offset > 0: fp["has_nested_function"]=True
        elif isinstance(n,ast.Constant) and isinstance(n.value,str):
            fp["string_literals_count"]+=1
            if n.value.startswith(("http://", "https://")): fp["url_literals"].append(_redact_url(n.value)[:120])
    for k in ("imports","calls","url_literals","control_flow"):
        fp[k]=sorted(set(fp[k]))
    return fp


def capability_fingerprint(code):
    fp={"libraries":[],"hermes_tools":[],"protocols":[],"operation_classes":[],"has_json":False,"has_subprocess":False,"has_requests":False,"has_sqlite":False}
    try:
        tree=ast.parse(code)
        for n in ast.walk(tree):
            if isinstance(n,ast.Import): fp["libraries"].extend(a.name.split(".")[0] for a in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module: fp["libraries"].append(n.module.split(".")[0])
    except SyntaxError:
        pass
    for t in ["terminal","read_file","write_file","search_files","web_search","web_extract","execute_code","patch","cronjob","skill_view","memory","session_search","image_generate","text_to_speech","vision_analyze","delegate_task","browser_navigate","clarify"]:
        if t in code: fp["hermes_tools"].append(t)
    l=code.lower()
    if "18643" in code: fp["protocols"].append("hmp")
    if "8642" in code: fp["protocols"].append("hermes_api")
    if "ssh" in l: fp["protocols"].append("ssh")
    if "health" in l or "ping" in l: fp["operation_classes"].append("healthcheck")
    if "/hmp/send" in code: fp["operation_classes"].append("hmp_send")
    if "json.loads" in code or "json.dumps" in code: fp["operation_classes"].append("json_processing")
    if "cronjob" in code: fp["operation_classes"].append("cron")
    if "scp" in code: fp["operation_classes"].append("file_transfer")
    if "broadcast" in l: fp["operation_classes"].append("broadcast")
    if "delete" in l or "rm " in code: fp["operation_classes"].append("delete")
    fp["has_json"]="json." in code; fp["has_subprocess"]="subprocess" in code
    fp["has_requests"]="requests" in fp["libraries"]; fp["has_sqlite"]="sqlite3" in fp["libraries"]
    for k in ("libraries","hermes_tools","protocols","operation_classes"):
        fp[k]=sorted(set(fp[k]))
    return fp


def _call_names(code):
    try: tree=ast.parse(code)
    except SyntaxError: return []
    names=[]
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute): names.append(_attr(n.func).lower())
            elif isinstance(n.func, ast.Name): names.append(n.func.id.lower())
    return names


def effect_fingerprint(code):
    fp={"declared_effect":"unknown","static_effect_hint":"unknown","observed_effect":"not_observed","observation_coverage":{"static_ast": True},
        "filesystem_read":False,"filesystem_write":False,"network_read":False,"network_write":False,
        "process_spawn":False,"remote_mutation":False,"unknown_effects":False,"effect_class":"unknown"}
    l=code.lower(); calls=_call_names(code)
    if any(c.endswith('.'+m) or c == m for c in calls for m in FS_READ_METHODS) or "read_file" in code or "open(" in code:
        fp["filesystem_read"]=True
    if any(c.endswith('.'+m) or c == m for c in calls for m in FS_WRITE_METHODS) or "write_file" in code or ".write(" in code:
        fp["filesystem_write"]=True
    if "urlopen" in l or "curl" in l or any(c.endswith('.'+m) or c == m for c in calls for m in READ_METHODS | WRITE_METHODS):
        fp["network_read"]=True
    if "/hmp/send" in code or " -x post" in l or "method=\"post\"" in l or "method='post'" in l or any(c.endswith('.'+m) or c == m for c in calls for m in WRITE_METHODS):
        fp["network_write"]=True
    if "scp" in l or "sftp" in l: fp["remote_mutation"]=True
    if "subprocess" in code or "terminal(" in code: fp["process_spawn"]=True
    if "exec(" in code or "eval(" in code: fp["unknown_effects"]=True
    if fp["network_write"] or fp["remote_mutation"] or fp["filesystem_write"]:
        fp["effect_class"] = fp["static_effect_hint"] = "mutating"
    elif fp["process_spawn"] or fp["unknown_effects"]:
        fp["effect_class"] = fp["static_effect_hint"] = "unknown"
    elif fp["network_read"] or fp["filesystem_read"]:
        fp["effect_class"] = fp["static_effect_hint"] = "read_only"
    return fp


def extract(code):
    return {"syntax":syntax_fingerprint(code),"capability":capability_fingerprint(code),"effect":effect_fingerprint(code)}


def stable_fingerprint_id(code):
    normalized = code.strip().encode("utf-8", "replace")
    return hashlib.sha256(normalized).hexdigest()[:24]


def format_report(fp):
    c=fp["capability"]; e=fp["effect"]; s=fp["syntax"]
    return (f"\n{'='*50}\nCODE FINGERPRINT\n{'='*50}\n\nCAPABILITY:\n"
            f"  Libs: {', '.join(c['libraries'][:8]) or '(none)'}\n"
            f"  Tools: {', '.join(c['hermes_tools'][:10]) or '(none)'}\n"
            f"  Protocols: {', '.join(c['protocols']) or '(none)'}\n"
            f"  Ops: {', '.join(c['operation_classes']) or '(none)'}\n\nEFFECT HINT: {e['effect_class']}\n"
            f"  FS r/w: {'Y' if e['filesystem_read'] else '-'}/{'Y' if e['filesystem_write'] else '-'}\n"
            f"  Net r/w: {'Y' if e['network_read'] else '-'}/{'Y' if e['network_write'] else '-'}\n"
            f"  Process: {'Y' if e['process_spawn'] else '-'}  Mutate: {'Y' if e['remote_mutation'] else '-'}\n\nSYNTAX:\n"
            f"  Stmts: {s['total_statements']}  Depth: {s['max_depth']}\n"
            f"  Loop: {'Y' if s['has_loop'] else '-'}  Try: {'Y' if s['has_try_except'] else '-'}\n"
            f"  Calls: {', '.join(s['calls'][:10]) or '(none)'}")

def main():
    code = Path(sys.argv[1]).read_text() if len(sys.argv)>1 else sys.stdin.read()
    if not code.strip(): print("Usage: python3 code-fingerprint.py <file_or_code>"); sys.exit(1)
    fp = extract(code); print(format_report(fp))
    out = Path.home()/".hermes"/"data"/"reuse-observer"/"fingerprints"
    out.mkdir(parents=True,exist_ok=True)
    fid = stable_fingerprint_id(code)
    (out/f"fp_{fid}.json").write_text(json.dumps(fp,indent=2))
    print(f"\nSaved: {out}/fp_{fid}.json")
if __name__ == "__main__": main()
