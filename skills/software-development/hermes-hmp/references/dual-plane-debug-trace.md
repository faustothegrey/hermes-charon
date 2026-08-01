# Dual-Plane Server Debug Trace (2026-07-23)

## Scenario

Test of `hmp_dual_plane.py` v2.0.0 server-side architecture:

```
POST /send {"session_id": "peer70_peer106", "text": "Server-side test v2. Funziona?"}
```

## Attempt 1 — Schema mismatch

**Symptom:** `Remote end closed connection without response`

**Server log:**
```
Exception occurred during processing of request from ('127.0.0.1', 55704)
Traceback (most recent call last):
  File ".../socketserver.py", line 650, in process_request_thread
    self.finish_request(request, client_address)
  ...
  File "hmp_dual_plane.py", line 209, in do_POST
    result = self.server_instance.process_message(session_id, text, max_tk)
  File "hmp_dual_plane.py", line 144, in process_message
    api_session = self._get_or_create_session(session_id)
  File "hmp_dual_plane.py", line 113, in _get_or_create_session
    self._store.save(session_id, sid)
  File "hmp_dual_plane.py", line 80, in save
    self._conn.execute("""INSERT OR REPLACE INTO sessions
sqlite3.IntegrityError: NOT NULL constraint failed: sessions.local_peer
```

**Root cause:** Old SQLite DB from a previous schema version. The DB had a `sessions` table without the `local_peer` column, but the new code expected it.

**Fix:** Delete old DB and let it recreate from scratch.

## Attempt 2 — Silent exception drop

**Symptom:** Same `Remote end closed connection without response`, but server log shows NO traceback.

**Diagnosis:** The DB was recreated, but `process_message()` encountered a different error that was NOT logged. The `do_POST` handler had no catch-all try/except, so any exception in `process_message()` propagates up through `BaseHTTPRequestHandler` which silently closes the connection.

**Python stdlib behavior:** When `do_POST` raises an unhandled exception:
1. `BaseHTTPRequestHandler.handle_one_request()` calls `self.handle()` 
2. `handle()` calls `self.do_POST()` which raises
3. The exception propagates through `ThreadingHTTPServer.process_request_thread()`
4. `socketserver.BaseServer.process_request()` logs the traceback (but `log_message` was silenced!)
5. The connection is closed without any HTTP response

## Fix applied

Wrapped `do_POST` body in try-except that returns `500 {"error": str(e), "trace": "server_error"}`:

```python
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
            ...
            result = self.server_instance.process_message(session_id, text, max_tk)
            self._json(200, result)
        else:
            self._json(404, {"error": "not_found"})
    except Exception as e:
        self._json(500, {"error": str(e), "trace": "server_error"})
```

## Attempt 3 — Script run directly (no __main__)

**Symptom:** After fix applied, server was killed. New server started with:
```bash
python3 /home/fausto/.hermes/scripts/hmp_dual_plane.py
```
Exit code: 0 (success). But `curl -s http://127.0.0.1:18644/health` → connection refused.

**Root cause:** `hmp_dual_plane.py` is a **library** — it only defines classes and functions. Running it directly just imports everything and exits. There is no `if __name__ == "__main__": run_server()` block.

**Correct invocation:** Import and call `run_server()` explicitly.
