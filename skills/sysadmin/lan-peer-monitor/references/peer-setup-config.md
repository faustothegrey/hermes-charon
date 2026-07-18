# Peer Network Setup — Reference Config

## Config YAML (gateway → api_server)

⚠️ **IMPORTANT:** `host` and `port` MUST go under `extra:`. Flat placement silently falls back to `127.0.0.1:8642`.

```yaml
# ~/.hermes/config.yaml
gateway:
  enabled: true
  platforms:
    telegram:
      enabled: true
      token_env: TELEGRAM_BOT_TOKEN
    api_server:
      enabled: true
      extra:
        host: 0.0.0.0
        port: 8642
```

## Environment

```bash
# ~/.hermes/.env
API_SERVER_KEY=<openssl rand -hex 32>   # min 16 chars for 0.0.0.0 binds
```

## Cronjob

```python
cronjob(
    action="create",
    name="Peer Network Monitor",
    schedule="every 1h",
    script="peer-monitor.py",
    attach_to_session=True,
    deliver="local",
)
```

## Known peers table (PEERS.md structure)

| Nome | IP | Host | OS | Ruolo | Stato |
|---|---|---|---|---|---|
| peer70 | 192.168.178.70 | raspberrypi | Debian 11 aarch64 | orchestratore | Online |
| peer84 | 192.168.178.84 | N56VV | Ubuntu 22.04 x86_64 | peer | Online |
| peer60 | 192.168.178.60 | raspberrypi | Raspbian 9 armv7l | peer | Offline |
| peer128 | da mDNS | MacBookPro | macOS 26.5.1 | peer | Non via IPv4 |

## Output files

| File | Format | Purpose |
|---|---|---|
| STATUS.md | Markdown table | Human-readable status |
| status.json | JSON | Machine-readable |
| history.log | Pipe-separated | Append-only change log |
