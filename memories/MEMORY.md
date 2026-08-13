Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: minimal tool calls, risposte concise, OK diretto se registry invariato, usa contesto già disponibile. Registry HMP: ~/.hermes/registry/registry.json. Sync: "registry sync?" → JSON compatto se cambiato, OK se no; niente patch heartbeat artificiali (i peer aggiornano last_seen da soli). Gateway = systemd user hermes-gateway.service.
§
Gateway restart peer70: cron one-shot inaffidabile (run_at passato=mai, ticker 5min) → restart manuale di Fausto. shutdown/reboot hardline assoluto. Peer remoti: SSH kill -9 + script no_agent OK. Dual-plane :18644 in ritiro, non riavviare.
§
Session-size: compressione 50% (auxiliary→auto=nous), watchdog 70% cron session-watchdog-70pct (~/.hermes/scripts/session_watchdog.py, deepseek-v4-flash=1M). Skill: hermes-session-lifecycle.
§
Undervoltage Charon RISOLTO 13/08 (nuovo caricatore, trial-error Fausto): throttled 0x0, ondemand 1500MHz, protezioni rimosse (service undervoltage-protect disabilitato, powersave tolto da rc.local), zram/journal mantenuti.
§
capability-reuse 2.4.17 VALIDATA 13/08 (T1-T6 ✅ peer106 conferma, fix T3 disposition + T5a pattern italiani) e distribuita su peer70/106/58/138/141 (backup .bak-2417).
§
peer106 (192.168.178.106, Fedora) = "trixie" nel linguaggio di Fausto (parlare: trixie; registry/docs: peer106). Macchina .136 (pi.dev, ex-trixie) ora = "Diet".
§
WireGuard: peer58 .58:51820, peer128=10.0.0.6 DDNS settembre2.homepc.it. peer138=.138 (capability-reuse). Sessioni HMP da peer: SSH/sudo/upnpc timeout senza approvazione Fausto → fargli fare da console.
§
peer141 (192.168.178.141, Stella, RPi aarch64, Hermes v0.20.0): nuovo peer 13/08/26, sostituisce peer105 (defunto). HMP :18643 v0.1.3 + API :8642 attivi, skill hermes-hmp caricata. SSH user fausto, key bidirezionale OK.
§
Dual-plane :18644 RITIRATO 13/08 da tutta la rete (peer70/58/106/138/141, confermato da tutti). Plugin HMP :18643 unico canale, v0.1.4 con live-shadow metadata (T2 capreuse PASS). hmp_dual_plane*.py rimossi ovunque. Non riavviare :18644.