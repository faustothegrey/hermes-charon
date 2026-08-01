#!/usr/bin/env python3
"""
HMP Dual-Plane Light — for Pi Agent / lightweight peers (no Hermes Agent)
========================================================================
Same protocol (POST :18644/send {session_id, text}) but without Hermes API.
Uses a local LLM or HMP loopback instead of Hermes Agent sessions.

DIFFERENCES from full version:
  - No SessionStore SQLite (in-memory dict for context)
  - No /api/sessions calls (no Hermes API)
  - No API keys
  - LLM response via HMP loopback (POST to own :18643/hmp/send)
  - Context maintained as simple list of messages per session_id
"""
import json, time, os, uuid
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

VERSION = "2.0.0-light"
MAX_CONTEXT = 20  # max messages kept per session

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def new_id(prefix="msg"):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

# ── In-memory Context Store ──

class ContextStore:
    """Simple in-memory context per session_id. No SQLite, no Hermes API."""

    def __init__(self):
        self._contexts = {}  # session_id → [{"role": ..., "content": ...}]

    def get_context(self, session_id):
        return self._contexts.get(session_id, [])

    def add_message(self, session_id, role, content):
        if session_id not in self._contexts:
            self._contexts[session_id] = []
        self._contexts[session_id].append({"role": role, "content": content})
        # Trim to max context size
        if len(self._contexts[session_id]) > MAX_CONTEXT:
            self._contexts[session_id] = self._contexts[session_id][-MAX_CONTEXT:]
        return self._contexts[session_id]

    def format_prompt(self, session_id, new_text):
        """Format context + new message into a prompt for the LLM."""
        ctx = self.get_context(session_id)
        lines = []
        for msg in ctx:
            prefix = "Utente" if msg["role"] == "user" else "Assistente"
            lines.append(f"{prefix}: {msg['content']}")
        lines.append(f"Utente: {new_text}")
        return "\n".join(lines)

# ── LLM Interface (pluggable) ──

class LLMInterface:
    """
    Interface to get LLM responses.
    Default: HMP loopback (posts to own :18643/hmp/send, polls for response).
    Override for direct pi.dev API or other LLM backends.
    """

    def __init__(self, hmp_port=18643, llm_url=None):
        self.hmp_port = hmp_port
        self.llm_url = llm_url  # Direct LLM endpoint, if available

    def ask(self, prompt, timeout=120):
        """Send prompt to LLM and return response text."""

        # Priority 1: Direct LLM endpoint (if configured)
        if self.llm_url:
            return self._ask_direct(prompt, timeout)

        # Priority 2: HMP loopback (default for Pi Agent)
        return self._ask_hmp(prompt, timeout)

    def _ask_hmp(self, prompt, timeout):
        """Send prompt to own HMP endpoint and poll for response."""
        msg_id = new_id("llm")
        body = json.dumps({
            "hmp_version": "1.0",
            "message_id": msg_id,
            "from": "local",
            "to": "local",
            "type": "request",
            "timeout": timeout,
            "payload": {"text": prompt}
        }).encode()
        try:
            r = urlopen(Request(f"http://127.0.0.1:{self.hmp_port}/hmp/send",
                data=body, headers={"Content-Type": "application/json"}), timeout=10)
            result = json.loads(r.read())
            if not result.get("accepted"):
                return f"Errore LLM: {result.get('error','send_failed')}"
        except Exception as e:
            return f"Errore LLM: {e}"

        # Poll for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = urlopen(f"http://127.0.0.1:{self.hmp_port}/hmp/poll/{msg_id}", timeout=5)
                poll = json.loads(r.read())
                status = poll.get("status")
                if status == "completed":
                    return poll.get("response_text", "")
                if status in ("failed", "timed_out"):
                    return f"Errore LLM: {status}"
            except:
                pass
            time.sleep(3)
        return "Errore LLM: timeout"

    def _ask_direct(self, prompt, timeout):
        """Send prompt directly to an LLM API endpoint."""
        try:
            body = json.dumps({
                "model": os.environ.get("LLM_MODEL", "default"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            }).encode()
            r = urlopen(Request(self.llm_url, data=body,
                headers={"Content-Type": "application/json"}), timeout=timeout)
            result = json.loads(r.read())
            # Try common response formats
            if "choices" in result:
                return result["choices"][0].get("message", {}).get("content", "")
            if "response" in result:
                return result["response"]
            return str(result)[:500]
        except Exception as e:
            return f"Errore LLM: {e}"

# ── Dual-Plane Light Server ──

class LightDualPlaneServer:
    """Lightweight dual-plane server for peers without Hermes Agent."""

    def __init__(self, node_id="peer", llm_url=None):
        self._my_name = node_id or os.environ.get("HMP_NODE_ID", "peer")
        self._context = ContextStore()
        self._llm = LLMInterface(llm_url=llm_url)
        print(f"LightDualPlaneServer starting as {self._my_name}")

    def process_message(self, session_id, text):
        """Process a message: build context prompt, get LLM response, store context."""
        # Build prompt from context + new message
        prompt = self._context.format_prompt(session_id, text)

        # Get LLM response
        response = self._llm.ask(prompt)

        # Store in context
        self._context.add_message(session_id, "user", text)
        self._context.add_message(session_id, "assistant", response)

        return {
            "status": "ok",
            "channel": "llm_local",
            "response": response,
            "session_id": session_id,
            "context_size": len(self._context.get_context(session_id)),
        }

# ── HTTP Server ──

class LightDualPlaneHandler(BaseHTTPRequestHandler):
    server_instance = None

    def log_message(self, format, *args):
        pass

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode() if length else "{}"
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "invalid_request"})
            return

        try:
            if self.path == "/send":
                session_id = body.get("session_id", body.get("peer_pair_id", ""))
                text = body.get("text", body.get("content", ""))
                if not session_id or not text:
                    self._json(400, {"error": "missing session_id or text"})
                    return
                result = self.server_instance.process_message(session_id, text)
                self._json(200, result)
            else:
                self._json(404, {"error": "not_found"})
        except Exception as e:
            self._json(500, {"error": str(e), "trace": "server_error"})

    def do_GET(self):
        srv_name = getattr(self.__class__, 'SERVICE_NAME', 'dual-plane-light')
        srv_ver = getattr(self.__class__, 'SERVICE_VERSION', VERSION)
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": srv_name, "version": srv_ver, "node": self.server_instance._my_name})
        else:
            self._json(404, {"error": "not_found"})

def run_server(host="0.0.0.0", port=18644, node_id=None, llm_url=None):
    """Start the lightweight dual-plane server."""
    server = LightDualPlaneServer(node_id=node_id, llm_url=llm_url)
    LightDualPlaneHandler.server_instance = server
    srv = ThreadingHTTPServer((host, port), LightDualPlaneHandler)
    print(f"Light Dual-Plane Server on {host}:{port} (v{VERSION}, node={server._my_name})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
