#!/usr/bin/env python3
"""G0 regression suite — HMP adapter request-unique trace_id (prereq: 2.6.0 ACCEPT).

Covers the acceptance checklist:
  [x] trace_id UUID unico per richiesta
  [x] catena correlabile (retrieval+surface_start+surface_complete stesso trace)
  [x] fallback chat_id/peer non usato per record eleggibili
  [x] 12 casi fail-closed · collector propagation (body/env/absent) OK

Run:  cd ~/.hermes/hermes-agent && ./venv/bin/python ~/.hermes/skills/hermes/capability-reuse/analysis/test_g0_adapter.py
"""
import asyncio
import os
import re
import sys
import uuid

sys.path.insert(0, "/home/fausto/.hermes/plugins")
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/hermes/capability-reuse/plugin"))
sys.path.insert(0, os.getcwd())

import hmp.adapter as adapter
from hmp.adapter import HMPAdapter

# Runtime registers plugin platforms via platform_registry; the test must do
# the same so Platform("hmp") resolves (dynamic enum member).
try:
    from gateway.platform_registry import PlatformEntry, platform_registry
    if not platform_registry.is_registered("hmp"):
        platform_registry.register(
            PlatformEntry(
                name="hmp",
                label="HMP",
                adapter_factory=lambda cfg: HMPAdapter(cfg),
                check_fn=lambda: True,
            )
        )
except Exception as exc:  # pragma: no cover
    print("WARN: platform_registry registration failed:", exc)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


class FakeStore:
    """Minimal stand-in for HMPStatusStore — only what _process_item touches."""

    def __init__(self):
        self.failed = []

    def mark_status(self, mid, status, error=None):
        pass

    def fail(self, mid, error):
        self.failed.append((mid, error))

    def dequeue(self):
        return None


class FakeConfig:
    extra = {}


def make_adapter():
    a = HMPAdapter(FakeConfig())
    a.store = FakeStore()
    return a


# ── capture hooks: record trace_id per emit call ──────────────────────────
captured = {"retrieval": [], "start": [], "complete": []}
orig_emit = {
    "retrieval": adapter.emit_retrieval,
    "start": adapter.emit_surface_execution_start,
    "complete": adapter.emit_surface_execution_complete,
}


def fake_emit_retrieval(**kw):
    captured["retrieval"].append(kw)
    return None


def fake_emit_start(**kw):
    captured["start"].append(kw)
    return "surf_1"


def fake_emit_complete(**kw):
    captured["complete"].append(kw)
    return None


def make_item(mid, from_peer, text, raw=None):
    return {
        "message_id": mid,
        "from_peer": from_peer,
        "chat_id": from_peer,
        "text": text,
        "raw": raw or {},
    }


async def test_trace_id_unique_and_chained():
    print("\n[T1] trace_id: 2 richieste → diversi; stessa richiesta → stessa catena")
    adapter.emit_retrieval = fake_emit_retrieval
    adapter.emit_surface_execution_start = fake_emit_start
    adapter.emit_surface_execution_complete = fake_emit_complete
    captured["retrieval"].clear()
    captured["start"].clear()
    captured["complete"].clear()

    a = make_adapter()
    # stub handle_message so we don't run a real agent turn
    async def fake_handle(event):
        return None
    a.handle_message = fake_handle

    r1 = await a._process_item(make_item("m1", "peer141", "test uno", {"provenance": "organic_live"}))
    r2 = await a._process_item(make_item("m2", "peer58", "test due", {"traffic_type": "registry_sync"}))

    t1, t2 = r1["trace_id"], r2["trace_id"]
    check("UUID v4 shape", bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", t1)), t1)
    check("2 richieste → trace_id diversi", t1 != t2, f"{t1} vs {t2}")
    check("stesso trace in retrieval e start (r1)", captured["retrieval"][0]["trace_id"] == captured["start"][0]["trace_id"] == t1)
    check("stesso trace in complete (r1)", captured["complete"][0]["trace_id"] == t1)
    check("stesso trace in retrieval e start (r2)", captured["retrieval"][1]["trace_id"] == captured["start"][1]["trace_id"] == t2)
    check("stesso trace in complete (r2)", captured["complete"][1]["trace_id"] == t2)
    check("trace_id != chat_id (r1)", t1 != "peer141", f"{t1} vs peer141")
    check("trace_id != chat_id (r2)", t2 != "peer58", f"{t2} vs peer58")
    check("outcome success", r1["outcome"] == "success" and r2["outcome"] == "success")


async def test_fail_closed_12():
    print("\n[T2] 12 casi fail-closed (classificazione provenance)")
    a = make_adapter()
    cases = [
        # (body, from_peer, atteso traffic_type)
        ({"scheduled": True}, "peer141", "scheduled_protocol"),
        ({"cron": True}, "peer141", "scheduled_protocol"),
        ({"traffic_type": "scheduled"}, "peer141", "scheduled_protocol"),
        ({"calibration": True}, "peer141", "calibration"),
        ({"traffic_type": "calibration"}, "peer141", "calibration"),
        ({"is_test": True}, "peer141", "test"),
        ({"acceptance": True}, "peer141", "test"),
        ({"operator_solicited": True}, "peer141", "operator_solicited"),
        ({"operator_seeded": True}, "peer141", "operator_seeded"),
        ({"traffic_type": "organic_peer"}, "peer141", "organic_peer"),
        ({"provenance": "organic_live"}, "peer141", "organic_peer"),
        ({}, "peer141", "unknown"),           # from_peer da solo → fail-closed unknown
        ({}, "", "unknown"),                   # nessun peer, nessuna prov → unknown
        ({"traffic_type": "registry_sync"}, "peer58", "registry_sync"),
    ]
    for body, peer, expected in cases:
        got = a._classify_traffic(body, peer)
        check(f"fail-closed {body or '{}'} / from={peer or '∅'} → {expected}",
              got[0] == expected, f"got {got[0]}")
    check("≥12 casi eseguiti", len(cases) >= 12, str(len(cases)))


def test_collector():
    print("\n[T3] collector_peer_id: body > env > absent")
    a = make_adapter()
    # absent
    old_env = os.environ.pop("CAPABILITY_REUSE_COLLECTOR_PEER_ID", None)
    check("absent → ''", a._extract_collector({}) == "")
    # env
    os.environ["CAPABILITY_REUSE_COLLECTOR_PEER_ID"] = "peer70"
    check("env → peer70", a._extract_collector({}) == "peer70")
    # body wins over env
    check("body > env", a._extract_collector({"collector_peer_id": "peer141"}) == "peer141")
    check("collector alias", a._extract_collector({"collector": "peer58"}) == "peer58")
    if old_env is None:
        os.environ.pop("CAPABILITY_REUSE_COLLECTOR_PEER_ID", None)
    else:
        os.environ["CAPABILITY_REUSE_COLLECTOR_PEER_ID"] = old_env


async def test_no_chat_id_fallback():
    print("\n[T4] nessun record eleggibile usa chat_id/peer come trace_id")
    adapter.emit_retrieval = fake_emit_retrieval
    adapter.emit_surface_execution_start = fake_emit_start
    adapter.emit_surface_execution_complete = fake_emit_complete
    captured["retrieval"].clear()
    captured["start"].clear()
    captured["complete"].clear()
    a = make_adapter()

    async def fake_handle(event):
        return None
    a.handle_message = fake_handle

    await a._process_item(make_item("m3", "peer141", "x", {"provenance": "organic_live"}))
    all_traces = [c["trace_id"] for c in captured["retrieval"] + captured["start"] + captured["complete"]]
    check("tutti UUID v4 (nessun chat_id/peer)", all(bool(re.fullmatch(r"[0-9a-f-]{36}", t)) for t in all_traces), str(all_traces))
    check("nessun trace == 'peer141'", "peer141" not in all_traces)


async def main():
    print("=" * 60)
    print("G0 REGRESSION — HMP adapter trace_id (Charon 0.17.0)")
    print("=" * 60)
    await test_trace_id_unique_and_chained()
    await test_fail_closed_12()
    test_collector()
    await test_no_chat_id_fallback()
    print("\n" + "=" * 60)
    print(f"RISULTATO: {PASS} PASS / {FAIL} FAIL")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
