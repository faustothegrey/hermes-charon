# HMP Health check endpoint (verificato 16/08/2026)

`GET http://<host>:18643/health` → HTTP 200

```json
{"status": "ok", "service": "hmp-gateway", "gateway_adapter": true, "node_id": "<peer>", "bind": "0.0.0.0:18643"}
```

- `gateway_adapter: true` = adapter HMP attivo; `status: ok` = gateway sano.
- ⚠️ `/status`, `/ping`, `/api/status`, `/version` → 404: l'unico endpoint di health è `/health`.

## Watchdog HMP (peer141 → peer70)

- Origin `watchdog-p141-p70`: messaggio ripetuto `check HMP health for peer70` ogni ~15 min (cron su peer141).
- Risposta attesa: esito compatto (`OK` / dettaglio). Nessuna azione oltre il check finché `/health` risponde 200.
