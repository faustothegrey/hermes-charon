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
6. Use Himalaya MML attachment syntax with `template send`:

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

Success signal: Himalaya returns `"Message successfully sent!"`.
