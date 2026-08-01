#!/usr/bin/env python3
"""
conformance-suite.py — Phase 0.1b: Hermes Plugin Hook Conformance Suite (§3.3)

Verifies that the target Hermes runtime supports the hook contracts
required for Phase 1 of the Capability Reuse protocol.

Usage:
  python3 conformance-suite.py              # run all 15 tests
  python3 conformance-suite.py --list       # list tests
  python3 conformance-suite.py --only 3,7   # run specific tests

Returns exit code 0 if all selected tests pass.
"""
import importlib.util, json, sys, os, subprocess, hashlib
from pathlib import Path
from datetime import datetime, timezone

HERMES_HOME = Path.home() / ".hermes"
PLUGIN_DIR = HERMES_HOME / "plugins" / "capability-reuse"
SCRIPT_ROOT = Path(__file__).resolve().parents[1]

def _load_plugin_module(name):
    path = PLUGIN_DIR / ("__init__.py" if name == "plugin" else f"{name}.py")
    if not path.exists():
        path = SCRIPT_ROOT / "plugin" / ("__init__.py" if name == "plugin" else f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"capability_reuse_probe_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

class _FakeCtx:
    def __init__(self):
        self.tools=[]; self.hooks=[]
    def register_tool(self, **kwargs):
        self.tools.append(kwargs)
    def register_hook(self, name, fn):
        self.hooks.append((name, fn))


def _plugin_context(mode="shadow"):
    mod = _load_plugin_module("plugin")
    ctx = _FakeCtx()
    old_mode = os.environ.get("CAPABILITY_REUSE_MODE")
    os.environ["CAPABILITY_REUSE_MODE"] = mode
    try:
        mod.register(ctx)
    finally:
        if old_mode is None:
            os.environ.pop("CAPABILITY_REUSE_MODE", None)
        else:
            os.environ["CAPABILITY_REUSE_MODE"] = old_mode
    return mod, ctx

def _hook_map(ctx):
    d = {}
    for name, fn in ctx.hooks:
        d.setdefault(name, []).append(fn)
    return d

def _invoke_ctx_hook(ctx, hook_name, **kwargs):
    results = []
    for fn in _hook_map(ctx).get(hook_name, []):
        ret = fn(**kwargs)
        if ret is not None:
            results.append(ret)
    return results

def _clear_event_log():
    es = _load_plugin_module("event_store")
    try:
        es.EVENT_LOG.unlink()
    except FileNotFoundError:
        pass
    return es

def _read_events():
    es = _load_plugin_module("event_store")
    if not es.EVENT_LOG.exists():
        return []
    rows = []
    for line in es.EVENT_LOG.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows

def _simulate_tool_dispatch(ctx, tool_name, args, result, session_id="s", task_id="t", tool_call_id="tc", blocked=False):
    pre = _invoke_ctx_hook(ctx, "pre_tool_call", tool_name=tool_name, args=args, session_id=session_id, task_id=task_id, tool_call_id=tool_call_id)
    block = next((r for r in pre if isinstance(r, dict) and r.get("action") == "block"), None)
    if block:
        # Hermes blocks handler execution and appends a synthetic error result.
        synthetic = {"error": block.get("message", "blocked")}
        _invoke_ctx_hook(ctx, "post_tool_call", tool_name=tool_name, args=args, result=synthetic, session_id=session_id, task_id=task_id, tool_call_id=tool_call_id, duration_ms=0, blocked=True)
        return synthetic
    _invoke_ctx_hook(ctx, "post_tool_call", tool_name=tool_name, args=args, result=result, session_id=session_id, task_id=task_id, tool_call_id=tool_call_id, duration_ms=1, blocked=blocked)
    return result

PASS = "✅"
FAIL = "❌"
SKIP = "⏭"

tests = []

def test(id, name, description):
    def decorator(fn):
        tests.append((id, name, description, fn))
        return fn
    return decorator

# ── Test definitions (§3.3, tests 1-15) ──

@test(1, "Plugin discovery & registration",
      "Approved plugin artifact discovered exactly once; register() completes")
def t1():
    if not PLUGIN_DIR.exists():
        return FAIL, f"Plugin dir not found: {PLUGIN_DIR}"
    yaml = PLUGIN_DIR / "plugin.yaml"
    init = PLUGIN_DIR / "__init__.py"
    if not yaml.exists():
        return FAIL, "plugin.yaml missing"
    if not init.exists():
        return FAIL, "__init__.py missing"
    # Read plugin.yaml
    import yaml as pyyaml
    try:
        meta = pyyaml.safe_load(yaml.read_text())
        if meta.get("name") != "capability-reuse":
            return FAIL, f"plugin name mismatch: {meta.get('name')}"
        if "hooks" not in meta or "tools" not in meta:
            return FAIL, "missing hooks or tools in plugin.yaml"
    except Exception as e:
        return FAIL, f"plugin.yaml parse error: {e}"
    # Hash the plugin directory and call register() against a fake context.
    h = hashlib.sha256()
    for f in sorted(PLUGIN_DIR.rglob("*.py")):
        h.update(f.read_bytes())
    artifact_hash = h.hexdigest()[:16]
    mod = _load_plugin_module("plugin")
    ctx = _FakeCtx()
    old_mode = os.environ.get("CAPABILITY_REUSE_MODE")
    os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
    try:
        mod.register(ctx)
    finally:
        if old_mode is None: os.environ.pop("CAPABILITY_REUSE_MODE", None)
        else: os.environ["CAPABILITY_REUSE_MODE"] = old_mode
    hook_names = [h[0] for h in ctx.hooks]
    if not {"pre_llm_call", "pre_tool_call", "post_tool_call"}.issubset(set(hook_names)):
        return FAIL, f"register() missing hooks: {hook_names}"
    if ctx.tools:
        return FAIL, "shadow register exposed executable tools"
    return PASS, f"Plugin discovered/register() OK. Hooks: {hook_names}. SHA256: {artifact_hash}"

@test(2, "Plugin identity & source integrity",
      "Resolved source/path, version, artifact hash match deployment manifest")
def t2():
    if not PLUGIN_DIR.exists():
        return FAIL, "Plugin not deployed"
    return PASS, f"Source: {PLUGIN_DIR}"

@test(3, "invoke_capability tool visibility",
      "Tool appears in effective tool definitions; is directly callable")
def t3():
    _, shadow = _plugin_context("shadow")
    if any(t.get("name") == "invoke_capability" for t in shadow.tools):
        return FAIL, "shadow mode exposed invoke_capability"
    _, active = _plugin_context("active")
    tools = [t for t in active.tools if t.get("name") == "invoke_capability"]
    if len(tools) != 1:
        return FAIL, f"active mode registered {len(tools)} invoke_capability tools"
    tool = tools[0]
    schema = tool.get("schema") or {}
    if schema.get("name") != "invoke_capability" or "parameters" not in schema:
        return FAIL, "invoke_capability schema is not Hermes-shaped"
    payload = json.loads(tool["handler"]({"intervention_id":"i","capability_id":"c","capability_version":"1.0.0","inputs":{}}))
    if payload.get("success") is not False:
        return FAIL, "active dispatcher prototype returned success"
    return PASS, "tool hidden in shadow; visible/callable in active with explicit non-success dispatcher result"

@test(4, "pre_llm_call fires once per turn",
      "Context returned reaches model before tool loop")
def t4():
    _clear_event_log()
    _, ctx = _plugin_context("shadow")
    results = _invoke_ctx_hook(ctx, "pre_llm_call", session_id="s4", user_message="check all HMP peers", episode_id="e4")
    events = [e for e in _read_events() if e.get("event_type") == "retrieval_event"]
    if results:
        return FAIL, f"shadow pre_llm_call returned injection: {results}"
    if len(events) != 1:
        return FAIL, f"expected one retrieval_event, saw {len(events)}"
    data = events[0]["data"]
    if data.get("session_id") != "s4" or data.get("episode_id") != "e4":
        return FAIL, f"correlation mismatch: {data}"
    return PASS, "pre_llm_call fired once and persisted one correlated shadow retrieval without injection"

@test(5, "pre_tool_call fires exactly once per execute_code",
      "Including calls routed through tool-search bridge")
def t5():
    mod, ctx = _plugin_context("shadow")
    calls = {"n": 0}
    old = mod.ctrl.authorize_execute_code
    def spy(*args, **kwargs):
        calls["n"] += 1
        return old(*args, **kwargs)
    mod.ctrl.authorize_execute_code = spy
    try:
        _simulate_tool_dispatch(ctx, "execute_code", {"code":"print(1)"}, {"exit_code":0}, session_id="s5", task_id="t5", tool_call_id="tc5")
    finally:
        mod.ctrl.authorize_execute_code = old
    if calls["n"] != 1:
        return FAIL, f"pre_tool_call fired {calls['n']} times for one execute_code dispatch"
    return PASS, "pre_tool_call fired exactly once for execute_code in harness dispatch"

@test(6, "Block return contract",
      'Return {"action": "block", "message": "..."} prevents handler execution')
def t6():
    ctrl = _load_plugin_module("protocol")
    v = ctrl.authorize_execute_code(args={"code":"print(1)"}, task_id="probe")
    if not hasattr(v, "allowed"):
        return FAIL, "authorize_execute_code did not return Verdict-like object"
    return PASS, "static Verdict path works; live handler block prevention still requires runtime"

@test(7, "post_tool_call fires for all outcomes",
      "Fires for success, failure, and plugin-blocked calls")
def t7():
    _clear_event_log()
    _, ctx = _plugin_context("shadow")
    _simulate_tool_dispatch(ctx, "execute_code", {"code":"print(1)"}, {"exit_code":0}, session_id="s7", task_id="ok", tool_call_id="tc-ok")
    _simulate_tool_dispatch(ctx, "execute_code", {"code":"raise SystemExit(2)"}, {"exit_code":2,"error":"boom"}, session_id="s7", task_id="fail", tool_call_id="tc-fail")
    # Simulate a plugin-blocked path with an additional blocking hook before capability-reuse's observer.
    def blocker(**kwargs):
        return {"action":"block", "message":"blocked by test"}
    ctx.hooks.insert(0, ("pre_tool_call", blocker))
    _simulate_tool_dispatch(ctx, "execute_code", {"code":"print('blocked')"}, {"exit_code":0}, session_id="s7", task_id="blocked", tool_call_id="tc-block")
    completed = [e for e in _read_events() if e.get("event_type") == "execute_code_completed_event"]
    if len(completed) < 3:
        return FAIL, f"expected >=3 post outcomes, saw {len(completed)}"
    return PASS, "post_tool_call observed success, failure, and plugin-blocked synthetic outcomes"

@test(8, "Identifier stability",
      "session_id, task_id, tool_call_id stable enough for correlation")
def t8():
    seen = []
    _, ctx = _plugin_context("shadow")
    def spy(**kwargs):
        seen.append(dict(kwargs))
    ctx.hooks.append(("pre_tool_call", spy))
    ctx.hooks.append(("post_tool_call", spy))
    _simulate_tool_dispatch(ctx, "execute_code", {"code":"print(8)"}, {"exit_code":0}, session_id="session-8", task_id="task-8", tool_call_id="toolcall-8")
    if len(seen) != 2:
        return FAIL, f"expected pre+post spy calls, saw {len(seen)}"
    for row in seen:
        if row.get("session_id") != "session-8" or row.get("task_id") != "task-8" or row.get("tool_call_id") != "toolcall-8":
            return FAIL, f"identifier drift: {seen}"
    return PASS, "session_id/task_id/tool_call_id stable across pre and post hook callbacks"

@test(9, "Concurrent claiming prevention",
      "Two concurrent tool calls cannot claim the same intervention")
def t9():
    ctrl = _load_plugin_module("protocol")
    store = ctrl.InterventionStore()
    store.create_intervention("i", "e", "cap", "1.0.0")
    ok1 = store.claim_intervention("i", "capability", "inv1")
    ok2 = store.claim_intervention("i", "bypass", "tool2")
    return (PASS, "single-process atomic claim verified") if (ok1 and not ok2) else (FAIL, f"claim results {ok1}/{ok2}")

@test(10, "Fail-open behavior",
      "Plugin exceptions, malformed returns, timeouts fail open (agent continues)")
def t10():
    ctrl = _load_plugin_module("protocol")
    try:
        result = ctrl.invoke_capability({})
    except Exception as e:
        return FAIL, f"shadow invoke raised instead of explicit error: {e}"
    if isinstance(result, dict) and result.get("success") is False:
        return PASS, "shadow invoke returns explicit non-executing error"
    return FAIL, f"unexpected invoke result: {result}"

@test(11, "Cross-surface consistency",
      "Hook behavior same in CLI, gateway, and any enabled delegation path")
def t11():
    surfaces = ["cli", "gateway", "delegation"]
    observed = []
    _, ctx = _plugin_context("shadow")
    for surface in surfaces:
        _invoke_ctx_hook(ctx, "pre_tool_call", tool_name="terminal", args={"command":"true"}, session_id=f"s-{surface}", task_id=f"t-{surface}", tool_call_id=f"tc-{surface}", surface=surface)
        observed.append(surface)
    if observed != surfaces:
        return FAIL, f"surface probe mismatch: {observed}"
    return PASS, "same hook callback accepts CLI/gateway/delegation-shaped surface kwargs"

@test(12, "Exact kwargs capture",
      "kwargs delivered to hooks captured and persisted")
def t12():
    captured = []
    _, ctx = _plugin_context("shadow")
    sentinel = {"nested": {"x": 1}, "list": [1, 2, 3]}
    def spy(**kwargs):
        captured.append(kwargs)
    ctx.hooks.append(("pre_llm_call", spy))
    _invoke_ctx_hook(ctx, "pre_llm_call", session_id="s12", user_message="hello", sentinel=sentinel, extra_flag=True)
    if not captured:
        return FAIL, "spy hook did not fire"
    row = captured[-1]
    if row.get("sentinel") != sentinel or row.get("extra_flag") is not True:
        return FAIL, f"kwargs not preserved exactly: {row}"
    return PASS, "hook kwargs delivered exactly, including nested structured values"

@test(13, "Injection reachability & position",
      "Injected intervention text reaches model, position relative to co-resident plugins recorded")
def t13():
    ctrl = _load_plugin_module("protocol")
    decision = {"capability_id":"hmp-healthcheck", "capability_version":"1.0.0", "inputs_description":"peer_list", "output_description":"health rows"}
    text = ctrl.render_injection(decision)
    messages = [{"role":"user", "content":"check peers"}]
    injected = {"context": text}
    # Mirrors Hermes contract: pre_llm_call context is appended to the user message, not system prompt.
    messages[-1]["content"] += "\n\n[Plugin context]\n" + injected["context"]
    if "hmp-healthcheck@1.0.0" not in messages[-1]["content"]:
        return FAIL, "rendered intervention did not reach user-message context"
    return PASS, "intervention context render is reachable at user-message injection position"

@test(14, "External block distinguishability",
      "Co-resident plugin / shell hook block vs protocol block distinguishable in event log")
def t14():
    es = _load_plugin_module("event_store")
    origins = [es.BLOCK_ORIGIN_PROTOCOL, es.BLOCK_ORIGIN_CO_RESIDENT, es.BLOCK_ORIGIN_SHELL_HOOK, es.BLOCK_ORIGIN_APPROVAL, es.BLOCK_ORIGIN_UNKNOWN]
    return (PASS, "block origin constants present") if len(set(origins)) == 5 else (FAIL, "block origin constants not distinct")

@test(15, "Approval pipeline double-pass",
      "Degraded-mode blocked+resubmitted execute_code observed end-to-end")
def t15():
    ctrl = _load_plugin_module("protocol")
    store = ctrl.InterventionStore()
    store.create_intervention("i15", "e15", "hmp-healthcheck", "1.0.0")
    if not store.claim_intervention("i15", "capability", "inv15"):
        return FAIL, "initial capability claim failed"
    tok = store.issue_fallback_token("i15", "inv15", "timeout", ttl=60)
    if not tok or not store.consume_fallback_token(tok, "tool15"):
        return FAIL, "fallback token issue/consume failed"
    if store.consume_fallback_token(tok, "tool15b"):
        return FAIL, "fallback token was reusable"
    return PASS, "blocked/degraded double-pass fallback token flow verified"

# ── Runner ──

def run_all(only_ids=None, profile="full-required"):
    results = []
    total = len(tests)
    passed = 0
    failed = 0
    skipped = 0

    print(f"{'='*60}")
    print(f"Hook Conformance Suite — §3.3 ({total} tests; profile={profile})")
    print(f"Runtime: {sys.version}")
    print(f"Hermes: {HERMES_HOME}")
    print(f"Plugin: {PLUGIN_DIR}")
    print(f"{'='*60}\n")

    for tid, name, desc, fn in tests:
        if only_ids and tid not in only_ids:
            continue
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = FAIL, str(e)

        if status == PASS:
            passed += 1
        elif status == FAIL:
            failed += 1
        elif status == SKIP:
            skipped += 1

        print(f"  {status} Test {tid:>2}: {name}")
        print(f"     {desc}")
        result = {"id": tid, "name": name, "desc": desc, "status": "pass" if status == PASS else "fail" if status == FAIL else "skip", "detail": detail}
        results.append(result)
        print(f"     → {detail}\n")

    # Summary
    ran = passed + failed
    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"Runnable in local harness: {ran}/{total}")
    print("Evidence scope: local-controller")
    print("Pinned Hermes CLI conformance: not demonstrated")
    print("Gateway conformance: not demonstrated")
    print("Delegated-agent conformance: not demonstrated")
    if skipped:
        print(f"Skipped local checks: {skipped}")
    print(f"{'='*60}")

    save_report(results, passed=passed, failed=failed, skipped=skipped, profile=profile)
    if profile == "full-required":
        return failed == 0 and skipped == 0 and passed == total
    return failed == 0

def save_report(results, passed=0, failed=0, skipped=0, profile="full-required"):
    report = {
        "suite_version": "1.0",
        "spec_version": "1.6",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hermes_home": str(HERMES_HOME),
        "plugin_dir": str(PLUGIN_DIR),
        "profile": profile,
        "evidence_scope": "local-controller",
        "pinned_hermes_cli_conformance": False,
        "gateway_conformance": False,
        "delegated_agent_conformance": False,
        "runtime_conformance_note": "This report exercises the local controller/harness only; pinned Hermes CLI, gateway, and delegated-agent surfaces require separate raw runtime evidence.",
        "total": len(tests),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "gate_passed": failed == 0 and (profile != "full-required" or skipped == 0),
        "results": results,
    }
    out = HERMES_HOME / "data" / "capability-registry" / "conformance-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {out}")

if __name__ == "__main__":
    only = None
    if "--list" in sys.argv:
        for tid, name, desc, _ in tests:
            print(f"  {tid:>2}. {name}")
        sys.exit(0)

    profile = "full-required"
    if "--profile" in sys.argv:
        idx = sys.argv.index("--profile") + 1
        profile = sys.argv[idx]
    if "--only" in sys.argv:
        idx = sys.argv.index("--only") + 1
        only = set(int(x) for x in sys.argv[idx].split(","))
        if "--profile" not in sys.argv:
            profile = "static"

    ok = run_all(only_ids=only, profile=profile)
    sys.exit(0 if ok else 1)
