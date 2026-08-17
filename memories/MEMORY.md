Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: minimal tool calls, risposte concise, OK/PARTIAL/FAIL max-righe con numeri, OK se registry invariato; GATE fasi: tooling completo ≠ fase chiusa, serve evidenza empirica (label umani, holdout, calibrazione) prima di closure. Local Skill registry (ex-HMP) = 'skill registry' di Fausto (NON hub pubblico): ~/.hermes/registry/, publish registry-publish.py, skill type: custom. Niente heartbeat artificiali. Gateway = systemd user hermes-gateway.service.
§
Cron 'once' run_at passato = loop; restart gateway manuale. Peer remoti: SSH kill -9 + no_agent OK.
§
Compressione 50%, watchdog 70% (cron session-watchdog-70pct). Skill: hermes-session-lifecycle.
§
G0/G2b CLOSED (17/08): trace_id UUID + provenance, dep-v260/2.6.0/ebab8ae6/collector peer70; atteso GO sealed Phase1a. Vault: session-facts-2026-08-17-g0-g2b-review-loop.md.
§
peer106 (.106, Fedora, SSH root): OFFLINE, upgrade pend. peer105 RIMOSSO 17/08.
§
peer141 (192.168.178.141, Stella, Hermes 0.20.1): hmp 0.1.4, canale observe interno al core, SSH fausto; check HMP health peer70 ~15min (autom.).
§
HMP :18643 unico canale v0.1.4. Health: GET /health → 200 (gateway_adapter:true) = gateway OK; /status,/ping,/version = 404.
§
Policy (Fausto): peer70 orchestratore+publisher autoritativo (GO/NO-GO fasi), max stabilità, no patch core sperimentali; peer141 impl+QA (evidenze); 17/08 peer128 lead dev capability-reuse (direzione, gate, release); sync mirato + riavvio manuale.
§
Studio topology (prereg v1.1 FROZEN): UNDERPOWERED, stratificazione bloccata; ripresa fix tier. Vault: topology-study-prereg-v1.1.md.
§
Core 0.17/0.20.1: _delivery_manager solo ≥0.20 (0.17: get_plugin_manager); gate+sink observe nel middleware solo ≥0.20 (0.17: execute_tool_calls_sequential). Proof observe: contare solo kind=retrieval.
§
Email himalaya: virgilio default; libero fausto.lelli72@libero.it invio review; hotmail rotta solo destinatario; yahoo no. Review loop = code-dev-reviewer + cron watchdog-libero-mail.
§
peer128 .112 = macOS, launchd ai.hermes.gateway (kickstart -k), SSH fausto.