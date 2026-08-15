Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: minimal tool calls, risposte concise, OK diretto se registry invariato, usa contesto già disponibile. Registry HMP: ~/.hermes/registry/registry.json. Sync: "registry sync?" → JSON compatto se cambiato, OK se no; niente patch heartbeat artificiali (i peer aggiornano last_seen da soli). Gateway = systemd user hermes-gateway.service.
§
Cron 'once' con run_at passato gira a OGNI tick (bug noto): job kill-gateway → loop restart infinito (14/08). Restart gateway = manuale. shutdown/reboot hardline assoluto. Peer remoti: SSH kill -9 + script no_agent OK.
§
Session-size: compressione 50% (auxiliary→auto=nous), watchdog 70% cron session-watchdog-70pct (~/.hermes/scripts/session_watchdog.py, deepseek-v4-flash=1M). Skill: hermes-session-lifecycle.
§
Undervoltage Charon RISOLTO 13/08 (nuovo caricatore): throttled 0x0, ondemand 1500MHz, prot. rimosse, zram ok.
§
capability-reuse 2.4.19 (15/08): skill=plugin peer70/141, e2e 10/10, harness-fb 0.1.1 dict. Core-patch per-version: patches in ~/.hermes/patches-core/, MAI nel sync skill; apply-core-patch.sh --check/--smoke/--gate (sha256). .bak* in plugins//skills/ shadowa discovery → backup SOLO in ~/.hermes/backups/.
§
peer106 (192.168.178.106, Fedora, SSH root): OFFLINE da 14/08, upgrade Hermes/hmp pendente.
§
WireGuard: peer58 .58:51820, peer128=10.0.0.6 DDNS settembre2.homepc.it. peer138=.138 (capability-reuse). Sessioni HMP da peer: SSH/sudo/upnpc timeout senza approvazione Fausto → fargli fare da console.
§
peer141 (192.168.178.141, Stella, Hermes 0.20.1): hmp 0.1.4, canale observe portato internamente sul core (14/08), SSH fausto. peer138 (DietPi, root, pip): gateway systemd DI SISTEMA (no --user), hmp 0.1.4.
§
Dual-plane :18644 RITIRATO 13/08 (peer70/58/106/138/141). Plugin HMP :18643 unico canale, v0.1.4 su tutti i peer (14/08). Non riavviare :18644.
§
Policy operativa (Fausto, 14/08): peer70 = orchestratore/source of truth, massima stabilità — niente script/patch core sperimentali su peer70; sviluppo su peer141, sync mirato solo a cose fatte + singolo riavvio manuale.