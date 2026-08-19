Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: minimal tool calls, risposte concise, OK/PARTIAL/FAIL max-righe con numeri, OK se registry invariato; GATE fasi: tooling completo ≠ fase chiusa, serve evidenza empirica (label umani, holdout, calibrazione) prima di closure. Local Skill registry (ex-HMP) = 'skill registry' di Fausto (NON hub pubblico): ~/.hermes/registry/, publish registry-publish.py, skill type: custom. Niente heartbeat artificiali. Gateway = systemd user hermes-gateway.service.
§
Cron 'once' run_at passato = loop; restart gateway manuale; peer remoti SSH kill -9.
§
Compressione 50%, watchdog 70% (cron). Skill: hermes-session-lifecycle.
§
G0/G2b CLOSED (17/08): trace_id UUID + provenance; atteso GO sealed Phase1a. Vault: session-facts-2026-08-17-g0-g2b-review-loop.md.
§
peer106 (.106, Fedora, root): OFFLINE. peer105 RIMOSSO. peer136 Davon Debian13 fausto 0.20.2: HMP attivo (hmp 0.1.5+G0/G2b), dsv4-flash, Trixie via. peer138=0.19.0.
§
peer141 (192.168.178.141, Stella, 0.20.1): hmp 0.1.4, SSH fausto; health peer70 ~15min.
§
HMP :18643 canale v0.1.4; health GET /health 200.
§
Policy (Fausto): peer70 orchestratore+coordinatore (GO/NO-GO fasi), max stabilità, no patch core sperimentali; peer128 lead dev capability-reuse (direzione, gate, release) — peer70 NON sviluppa cap-reuse; peer141 impl+QA (evidenze); sync mirato + riavvio manuale.
§
Studio topology (prereg FROZEN): UNDERPOWERED; ripresa fix tier. Vault: topology-study-prereg-v1.1.md.
§
Core 0.17/0.20.1: _delivery_manager solo ≥0.20; gate+sink observe nel middleware solo ≥0.20 (0.17: execute_tool_calls_sequential). Proof observe: contare solo kind=retrieval.
§
Email himalaya: virgilio default; libero fausto.lelli72@libero.it invio review; hotmail rotta solo destinatario; yahoo no. Review loop = code-dev-reviewer + cron watchdog-libero-mail.
§
peer128 .112 = macOS portatile, launchd kickstart -k, SSH fausto.
§
BUG HMP (18/08, peer136): msg delivering orfano se gateway riavvia a metà turno; consumer non riprende; sessione bloccata; ping altra sessione ok. Workaround: re-invio. Fix da analizzare.