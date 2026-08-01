# Plugin Deployment via API Delegation

Deploy a Hermes plugin from the orchestrator (peer70) to a remote peer
when SCP/SSH is unavailable or the remote peer has its own Hermes agent
that can do the installation.

## Pattern: Base64 Tar.gz in Chat Completion Prompt

The orchestrator packages the plugin directory into a base64 tar.gz,
sends it via the remote peer's chat completions API (`:8642/v1/chat/completions`),
and asks the remote agent to extract, install, and enable it.

### Why Not SCP/SSH

| Method | Limitation |
|--------|------------|
| SCP/SSH | Requires SSH credentials + key/password on orchestrator |
| HMP send | Cannot carry binary files; text-only messages |
| Web server | Requires running a file server on orchestrator |
| **API delegation** | **No SSH needed; uses remote peer's own Hermes agent** |

### Steps

1. **Tar+gz the plugin directory** on the orchestrator:
   ```python
   import tarfile, io, base64, os

   buf = io.BytesIO()
   with tarfile.open(fileobj=buf, mode="w:gz") as tar:
       for fname in os.listdir(PLUGIN_SRC):
           if fname == "__pycache__":
               continue
           fpath = os.path.join(PLUGIN_SRC, fname)
           if os.path.isfile(fpath):
               tar.add(fpath, arcname=fname)
   b64 = base64.b64encode(buf.getvalue()).decode()
   ```

2. **Send via chat completions API** — the prompt includes the base64 blob
   and step-by-step instructions:
   ```python
   prompt = f"""Deploy the XYZ Hermes plugin to this machine.
   1. Extract this base64 tar.gz to ~/.hermes/plugins/xyz/:
   {b64}
   2. Use Python:
      data = base64.b64decode(THE_BASE64_ABOVE)
      with tarfile.open(fileobj=io.BytesIO(data)) as tar:
          tar.extractall(path=os.path.expanduser("~/.hermes/plugins/xyz/"))
   3. Verify files: list ~/.hermes/plugins/xyz/
   4. In ~/.hermes/config.yaml, add "xyz" to plugins.enabled (preserve existing plugins)
   5. Restart gateway
   6. Verify /hmp/health still OK
   Report the verification output."""
   
   payload = json.dumps({"model": "hermes-agent",
       "messages": [{"role": "user", "content": prompt}],
       "max_tokens": 2000}).encode()
   req = urllib.request.Request(f"http://{peer_host}:8642/v1/chat/completions",
       data=payload, headers={"Authorization": f"Bearer {api_key}",
       "Content-Type": "application/json"})
   with urllib.request.urlopen(req, timeout=300) as resp:
       body = json.loads(resp.read())
       print(body["choices"][0]["message"]["content"])
   ```

### Critical Rules

- **Preserve existing plugins** — instruct the remote peer NEVER to remove
  or modify the HMP plugin. Add-only.
- **Timeout >= 300s** — macOS peers are slow (30-90s per LLM call), plus
  gateway restart + verification. 5 minutes minimum.
- **max_tokens: 2000** — enough for the response payload without costing
  too many tokens.
- **ask for verification output** — the remote agent's final response should
  include the /hmp/health output so you can confirm the deployment didn't
  break HMP connectivity.
- **Base64 limits** — base64 expands binary by ~33%. A 30KB plugin dir
  becomes ~40KB of base64 text. The prompt can handle this, but very large
  plugins (>100KB) may hit message size limits. For those, split into
  multiple smaller transfers.

### When to Use vs. SCP

| Factor | API delegation | SCP/SSH |
|--------|---------------|---------|
| Auth | API key (already have) | SSH credentials (may not have) |
| Speed | 2-5 min (LLM inference) | ~1s (file copy) |
| Reliability | Depends on remote agent | Direct file transfer |
| Complex deploy | Agent handles config changes | Requires manual config steps |
| Plugin depends on other files | Can bundle multiple files | Also works with tar |

**Prefer API delegation when:** the remote peer has Hermes agent running
and you don't have (or don't want to manage) SSH credentials.

**Prefer SCP when:** the plugin is large (>100KB) or you need to deploy
to many peers quickly.

### Verification Checklist

After the remote agent reports success:
1. Check `/hmp/health` on the peer — must still return `{"status": "ok"}`
2. Optionally check the plugin's own health endpoint if it has one
3. Confirm the HMP plugin was NOT removed (enabled state preserved)

### Known Failures

- **macOS App Nap**: If the Mac is idle, the agent may take 60s+ to
  respond. Use 300s timeout.
- **Gateway restart loop**: If config.yaml has a syntax error after
  modification, the gateway may crash-loop. The remote agent should
  report this in its response.
- **`every 1m` cron jobs don't fire**: If using cron to run the deploy
  script, use `every 2m` or `every 5m` instead — the scheduler may skip
  `every 1m` intervals on some gateway versions.
