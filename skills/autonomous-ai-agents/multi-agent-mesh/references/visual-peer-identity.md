# Visual Peer Identity: Shell Prompt Color Scheme

When managing multiple Hermes peers on the same LAN, a standardized shell prompt with per-peer color coding makes reconnaissance instant — you can tell *which machine you're on* by the hostname color alone, without reading the hostname text.

## Format

Use a **unified format** across all peers, varying only the hostname color:

```
\[COLOR\]\u@\h\[RESET\]:\[BLUE\]\w\[RESET\]$
```

Where:
- `\u` = username (neutral color)
- `\h` = hostname (per-peer color)
- `\w` = working directory (consistent blue across all peers)
- `$` = prompt suffix

## Color Allocation

Assign a unique color to each peer. Common ANSI 256-color codes:

| Peer Profile | Color | ANSI Code | 
|---|---|---|
| Coordinator (24/7 orchestrator) | Blue | `01;34` |
| Heavy worker (laptop, thermal) | Green | `01;32` |
| Media/YouTube specialist | Yellow | `01;33` |
| Research/Web specialist | Cyan | `01;36` |
| Mac/Desktop | Red | `01;31` |
| Test/Dev | Magenta | `01;35` |

## PS1 Config Line

Add to each peer's `~/.bashrc`:

```bash
export PS1="\[\e[COLORm\]\u@\h\[\e[0m\]:\[\e[01;34m\]\w\[\e[0m\]\$ "
```

Replace `COLOR` with the peer's ANSI code.

Example for a coordinator (blue hostname):
```bash
export PS1="\[\e[01;34m\]\u@\h\[\e[0m\]:\[\e[01;34m\]\w\[\e[0m\]\$ "
```

## Deploying Across Peers

On the orchestrator peer, use the chat completions API to tell each peer to append the PS1 line to their bashrc:

```
Q: "Esegui: echo 'export PS1=\"\\\\[\\\\e[01;32m\\\\]\\\\u@\\\\h\\\\[\\\\e[0m\\\\]:\\\\[\\\\e[01;34m\\\\]\\\\w\\\\[\\\\e[0m\\\\]\\\\$ \"' >> ~/.bashrc. Rispondi DONE."
R: "DONE"
```

Important: escape sequences must be **doubly escaped** when embedded in a JSON string inside an API payload. Each `\` becomes `\\`, each `[` becomes `\\[`, etc.

## Pitfalls

- **Terminal emulator detection:** Some minimalist terminals or cron-mode shells may not set `$TERM` to a value that enables `force_color_prompt`. The PS1 with ANSI codes works regardless of `force_color_prompt` when set via `export PS1=...` — no color-prompt detection logic needed.
- **Source after adding:** After appending to `~/.bashrc`, either `source ~/.bashrc` or start a new shell.
- **Lock yourself out:** If you set a malformed PS1 that breaks the shell, you can still recover via the API (the agent's terminal session is independent of the user's interactive shell prompt). Use `unset PS1` or fix theline.
- **Propagation delay:** The PS1 change only affects new shell sessions — existing open terminals keep the old prompt.
