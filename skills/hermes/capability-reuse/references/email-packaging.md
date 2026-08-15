# Packaging and emailing capability-reuse code

When the user asks for the whole capability-reuse plugin/codebase by email:

1. Package the class directory, not only `plugin/`, unless the user explicitly says plugin runtime files only. Include `SKILL.md`, `plugin/`, `scripts/`, and `references/`.
2. Exclude transient Python cache files: `__pycache__/` and `*.pyc`.
3. Create a zip from the parent directory so the archive root is `capability-reuse/`.
4. Verify before sending:
   - `sha256sum <zip>`
   - `stat -c 'SIZE_BYTES=%s' <zip>`
   - `unzip -l <zip>` or equivalent file count check
5. If SMTP/Himalaya credentials are on peer70, copy the zip there with `scp`, verify hash and size again on peer70, then send from peer70.
6. Send with Himalaya. **v2.0.0 (peer141, current)** — `template send`/MML
   do NOT exist in v2. Use `message send --save "<Sent-folder>"` with a raw
   RFC 5322 message piped via stdin. Build the MIME multipart in Python
   (`email.mime.multipart` + `MIMEApplication` for the zip), then:

```python
import subprocess
raw = msg.as_string()  # MIMEMultipart('mixed') with text part + zip attachment
proc = subprocess.run(
    ['/home/fausto/.local/bin/himalaya', 'message', 'send', '--save', 'Posta Inviata'],
    input=raw.encode('utf-8'), capture_output=True, timeout=120)
# Success: "Message successfully saved and sent"
```

   Virgilio Sent folder is `Posta Inviata` (Italian) — set `mailbox.alias.sent`
   in `~/.config/himalaya/config.toml` or pass the real name to `--save`.

   **Legacy v1 syntax (peer70, older himalaya)** — MML attachment via `template send`:

```bash
cat > /tmp/capability-reuse-email.mml <<'EOF'
From: fausto.lelli@virgilio.it
To: fausto.lelli@gmail.com
Subject: Capability Reuse plugin code

<#multipart type=mixed>
<#part type=text/plain>
Ciao Fausto,

In allegato trovi lo zip del codice capability-reuse.

File: capability-reuse-plugin-full.zip
SHA256: <sha256>
Size: <bytes> bytes
<#part filename=/tmp/capability-reuse-plugin-full.zip name=capability-reuse-plugin-full.zip><#/part>
<#/multipart>
EOF

/home/fausto/.local/bin/himalaya template send --account virgilio --output json < /tmp/capability-reuse-email.mml
```

Success signal: Himalaya returns `"Message successfully sent!"` (v1) or
`"Message successfully saved and sent"` (v2, includes copy to Sent).
