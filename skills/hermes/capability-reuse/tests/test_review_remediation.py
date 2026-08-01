import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeCtx:
    def __init__(self):
        self.tools = []
        self.hooks = []
    def register_tool(self, **kwargs):
        self.tools.append(kwargs)
    def register_hook(self, name, fn):
        self.hooks.append((name, fn))


class ReviewRemediationTests(unittest.TestCase):
    def test_shadow_register_hides_invoke_capability(self):
        os.environ.pop("CAPABILITY_REUSE_MODE", None)
        plug = importlib.reload(importlib.import_module("plugin"))
        ctx = FakeCtx()
        plug.register(ctx)
        self.assertEqual([], [t["name"] for t in ctx.tools])
        self.assertEqual(["pre_llm_call", "pre_tool_call", "post_tool_call"], [h[0] for h in ctx.hooks])

    def test_invoke_schema_uses_hermes_tool_shape(self):
        protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        schema = protocol.invoke_schema()
        self.assertEqual("invoke_capability", schema["name"])
        self.assertIn("description", schema)
        self.assertEqual("object", schema["parameters"]["type"])
        self.assertFalse(schema["parameters"].get("additionalProperties", True))

    def test_invoke_capability_shadow_returns_error_not_fake_success(self):
        os.environ.pop("CAPABILITY_REUSE_MODE", None)
        protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        result = protocol.invoke_capability({
            "intervention_id":"i", "capability_id":"c", "capability_version":"1.0.0", "inputs":{}
        })
        self.assertFalse(result["success"])
        self.assertEqual("shadow_mode_not_executable", result["error"])

    def test_protocol_retrieve_calls_shadow_retriever_but_never_intervenes(self):
        protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        calls = []
        fake = types.SimpleNamespace(retrieve=lambda **kw: calls.append(kw) or {"intervened": True})
        old = sys.modules.get("plugin.retriever")
        sys.modules["plugin.retriever"] = fake
        try:
            self.assertIsNone(protocol.retrieve(session_id="s", user_message="check hmp"))
            self.assertEqual(1, len(calls))
            self.assertTrue(calls[0]["shadow_mode"])
        finally:
            if old is not None:
                sys.modules["plugin.retriever"] = old

    def test_state_machine_rejects_invalid_transition_and_returns_copy(self):
        protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        store = protocol.InterventionStore()
        store.create_intervention("i", "e", "cap", "1.0.0")
        self.assertFalse(store.transition("i", "resolved_success"))
        snap = store.get_intervention("i")
        snap["state"] = "resolved_success"
        self.assertEqual("open", store.get_intervention("i")["state"])

    def test_fallback_token_is_single_live_token(self):
        protocol = importlib.reload(importlib.import_module("plugin.protocol"))
        store = protocol.InterventionStore()
        store.create_intervention("i", "e", "cap", "1.0.0")
        self.assertTrue(store.claim_intervention("i", "capability", "inv1"))
        first = store.issue_fallback_token("i", "inv1", "clean_failure")
        second = store.issue_fallback_token("i", "inv1", "clean_failure")
        self.assertTrue(first)
        self.assertIsNone(second)

    def test_code_fingerprint_detects_post_as_mutating_and_path_read(self):
        mod = SourceFileLoader("code_fingerprint", str(ROOT / "scripts" / "code-fingerprint.py")).load_module()
        fp = mod.effect_fingerprint('import requests\nrequests.post("http://x", json={"a":1})')
        self.assertTrue(fp["network_write"])
        self.assertNotEqual("read_only", fp["effect_class"])
        fp2 = mod.effect_fingerprint('from pathlib import Path\nPath("/tmp/a").read_text()')
        self.assertTrue(fp2["filesystem_read"])
        self.assertEqual("read_only", fp2["effect_class"])
        self.assertFalse(mod.syntax_fingerprint('def f():\n    return 1')["parse_error"] if "parse_error" in mod.syntax_fingerprint('def f():\n    return 1') else False)

    def test_recurrence_audit_extracts_structured_execute_code(self):
        mod = SourceFileLoader("recurrence_audit", str(ROOT / "scripts" / "recurrence-audit.py")).load_module()
        events = [
            {"tool": "execute_code", "code": "import json\njson.loads('[]')"},
            {"name": "execute_code", "arguments": {"code": "print(1)"}},
            'execute_code({"code":"print(2)"})',
        ]
        extracted = []
        for e in events:
            extracted.extend(mod.extract_execute_code_snippets(e))
        self.assertGreaterEqual(len(extracted), 3)

    def test_redaction_masks_tokens_and_urls(self):
        events = importlib.reload(importlib.import_module("plugin.event_store"))
        text = "Authorization: Bearer abc.def.ghi https://user:pass@example.com/path?token=secret /home/fausto/private"
        redacted = events.redact_preview(text)
        self.assertNotIn("abc.def.ghi", redacted)
        self.assertNotIn("user:pass", redacted)
        self.assertNotIn("token=secret", redacted)
        self.assertNotIn("/home/fausto", redacted)


if __name__ == "__main__":
    unittest.main()
