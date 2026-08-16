Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: minimal tool calls, risposte concise, OK se registry invariato, usa contesto già disponibile. Local Skill registry (ex-HMP) = 'skill registry' di Fausto (NON hub pubblico): ~/.hermes/registry/, publish registry-publish.py, skill type: custom. Niente heartbeat artificiali (last_seen lo aggiornano i peer). Gateway = systemd user hermes-gateway.service.
§
Cron 'once' con run_at passato gira a OGNI tick (bug noto): kill-gateway → loop restart. Restart gateway = manuale. shutdown/reboot hardline. Peer remoti: SSH kill -9 + no_agent OK.
§
Compressione 50%, watchdog 70% (cron session-watchdog-70pct). Skill: hermes-session-lifecycle.
§
capability-reuse 2.5.0: skill=plugin peer70/141. Core-patch: patches in ~/.hermes/patches-core/, MAI nel sync skill; apply-core-patch.sh --check/--smoke/--gate (sha256). HMP send: from_peer = requester reale; POST proprio gateway = iniezione locale. .bak* shadowa discovery → backup SOLO in ~/.hermes/backups/. G0 16/08: adapter hmp trace_id=UUID/richiesta; bundle ~/.hermes/g0-bundle/.
§
peer106 (.106, Fedora, SSH root): OFFLINE da 14/08, upgrade pendente.
§
WireGuard: peer58 .58:51820, peer128=10.0.0.6 DDNS settembre2.homepc.it. peer138=.138 (capability-reuse). Sessioni HMP da peer: SSH/sudo/upnpc timeout senza approvazione Fausto → fargli fare da console.
§
peer141 (192.168.178.141, Stella, Hermes 0.20.1): hmp 0.1.4, canale observe interno al core, SSH fausto; check HMP health peer70 ~15min (autom.).
§
Dual-plane :18644 RITIRATO. HMP :18643 unico canale v0.1.4. Store msg: ~/.hermes/data/hmp_gateway_plugin/messages.db (NON hmp/agent_messages.db); log tronca 80ch. Helper: ~/.hermes/scripts/hmp-read-msg.py.
§
Policy (Fausto 14/08): peer70 orchestratore, max stabilità — niente patch core sperimentali; sviluppo su peer141; sync mirato + riavvio manuale.
§
Studio topology ESEGUITO 16/08 → UNDERPOWERED (63 trans, 79 started, 4 cluster; audit in skill analysis/). Gap: recurrence-audit non emette tier confidence → stratificazione non eseguibile. Ripresa: fix tier + calibration.