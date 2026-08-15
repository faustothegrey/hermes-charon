"""v2.5.0 — capability-reuse usa il canale observe (bubble 🔍).

Vincoli del review gate (APPROVE FOR IMPLEMENTATION):
  1. same session + same turn -> required (match FORTE, niente fallback)
  2. single observe per retrieval envelope -> required (consume-on-observe)
  3. ordinary/no-current retrieval -> None -> required
  4. existing block/approve semantics unchanged -> required
  5. observe failure remains fail-open -> required
  6. real gateway observe -> tool.considered proof -> covered dal
     driver observe-channel-skill-runtime-proof.py (evidence bundle)
"""
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CAPABILITY_REUSE_MODE", "shadow")


class _Result:
    """RetrievalResult-like con __dict__ (come il retriever reale)."""

    def __init__(self, capability="hmp-healthcheck", score=0.71, turn="t1",
                 session="s1", episode="ep1", latency=4.0, intervened=True):
        self.retrieval_event_id = f"rev_{capability}_{turn}"
        self.session_id = session
        self.episode_id = episode
        self.turn_id = turn
        self.capability_id = capability
        self.capability_version = "1.0.0"
        self.retrieval_score = score
        self.latency_ms = latency
        self.intervened = intervened


class ObserveChannelSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proto = importlib.import_module("plugin.protocol")
        cls.pkg = importlib.import_module("plugin")

    def setUp(self):
        self.proto._latest_retrieval_by_scope.clear()

    # ── vincolo 1: same session + same turn ──────────────────────────────
    def test_observe_when_active_envelope_same_turn(self):
        self.proto._remember_retrieval(_Result())
        feedback = self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t1")
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["kind"], "retrieval")
        self.assertIn("hmp-healthcheck", feedback["text"])
        self.assertIn("0.71", feedback["text"])
        self.assertEqual(feedback["duration_ms"], 4.0)

    def test_no_observe_when_turn_differs(self):
        self.proto._remember_retrieval(_Result())
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t2"))

    def test_no_observe_when_session_differs(self):
        self.proto._remember_retrieval(_Result())
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s9", episode_id="ep1", turn_id="t1"))

    def test_no_observe_without_turn(self):
        self.proto._remember_retrieval(_Result())
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s1", turn_id=""))

    # ── vincolo 2: single observe per envelope (consume-on-observe) ──────
    def test_single_fire_per_envelope(self):
        self.proto._remember_retrieval(_Result())
        self.assertIsNotNone(self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t1"))
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t1"))

    def test_hook_single_fire(self):
        self.proto._remember_retrieval(_Result())
        r1 = self.pkg.on_pre_tool_call(
            "web_search", {"q": "x"}, task_id="t1",
            session_id="s1", episode_id="ep1", turn_id="t1")
        self.assertEqual(r1["action"], "observe")
        self.assertIn("hmp-healthcheck", r1["feedback"]["text"])
        r2 = self.pkg.on_pre_tool_call(
            "web_search", {"q": "x"}, task_id="t1",
            session_id="s1", episode_id="ep1", turn_id="t1")
        self.assertIsNone(r2)

    # ── vincolo 3: ordinary / no-current retrieval -> None ───────────────
    def test_none_without_envelope(self):
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t1"))

    def test_hook_none_without_envelope(self):
        r = self.pkg.on_pre_tool_call(
            "web_search", {"q": "x"}, task_id="t1",
            session_id="s1", episode_id="ep1", turn_id="t1")
        self.assertIsNone(r)

    # ── vincolo 4: block/approve semantics unchanged ─────────────────────
    def test_execute_code_block_preserved(self):
        os.environ["CAPABILITY_REUSE_MODE"] = "active"
        try:
            importlib.reload(self.proto)
            # senza intervento attivo: execute_code passa (None = allow)
            verdict = self.pkg.on_pre_tool_call(
                "execute_code", {"code": "print(1)"}, task_id="t1",
                session_id="s1", episode_id="ep1", turn_id="t1")
            # in shadow/reload la modalita' attiva senza allowlist env:
            # authorize_execute_code decide; nessun crash, mai observe
            self.assertIn(verdict, (None, {"action": "block"}))
            if isinstance(verdict, dict):
                self.assertEqual(verdict["action"], "block")
        finally:
            os.environ["CAPABILITY_REUSE_MODE"] = "shadow"
            importlib.reload(self.proto)

    # ── vincolo 5: observe fail-open ─────────────────────────────────────
    def test_fail_open_no_capability(self):
        self.proto._remember_retrieval(_Result(capability="", score=0.0))
        self.assertIsNone(self.proto.consume_retrieval_observe(
            session_id="s1", episode_id="ep1", turn_id="t1"))
        # envelope NON consumato: un retrieval valido successivo emette ancora
        env = self.proto._latest_retrieval_by_scope.get(
            self.proto._scope("s1", "ep1", "t1"))
        self.assertIsNotNone(env)
        self.assertFalse(env.get("observe_shown"))

    def test_fail_open_hook_never_raises(self):
        # hook senza kwargs: nessun crash, None
        r = self.pkg.on_pre_tool_call("web_search", {"q": "x"}, task_id="")
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
