Obsidian vault: /home/fausto/Documents/Obsidian Vault/. Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata — non descrivere. Ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: harness-first, stable-operation-first, soft mode. "E poi?"=azione. "Basta X"=stop. peer136 escluso. peer105 offline. peer84 solo dopo 17:00. Phase 0 tooling 7/7 ok. Live-shadow authorized.
§
Fausto: minimal tool calls, risposte concise, OK diretto se registry invariato, usa contesto già disponibile. Registry HMP: ~/.hermes/registry/registry.json. Sync: "registry sync?" → JSON compatto se cambiato, OK se no; niente patch heartbeat artificiali (i peer aggiornano last_seen da soli). Gateway = systemd user hermes-gateway.service.
§
HMP :18643 delivery between peer70 and peers often gets stuck delivering. Dual-plane :18644 reliable. Use dual-plane per messaggi importanti. peer105 offline fino a nuovo avviso. peer84 cooling 11-17 (calore fisico).
§
Skill v2.4.6, live-shadow attivo
§
Gateway restart peer70: solo cron one-shot deliver=local (kill -9 e SSH esterno bloccati dal safety scanner). Peer remoti: SSH kill -9 OK. Dopo restart riavviare dual-plane :18644.
§
Session-size: compressione auto 50% OK (auxiliary rimosso→auto=nous). Watchdog 70% attivo: cron session-watchdog-70pct, script ~/.hermes/scripts/session_watchdog.py (last_prompt_tokens da sessions.json, deepseek-v4-flash=1M). session_reset.notify è post, no pre-warning nativo. Skill: hermes-session-lifecycle.
§
Email: fausto.lelli@gmail.com via Virgilio (riattivato 2026-08-01). Config SMTP funzionante: smtp.libero.it:587 STARTTLS (465/993 conn reset da IOL, cert *.libero.it; himalaya fallisce 'Unparseable SMTP reply' su IOL → usare smtplib python). pass ~/.config/himalaya/virgilio.pass — password attuale rifiutata 535, va aggiornata da Fausto.
§
SSH peer: root/ccll4372=peer106/138; fausto/ccll4372=peer84/58 (root su peer58 fallisce).
§
peer70 (Charon, RPi Bullseye py3.9): undervoltage cronico (PSU scarso). Protetto in rc.local: powersave 600MHz, zram 512M, dirty 1500/1000/10, journald 100M. Backup GitHub: state.db escluso dai secrets. Watchdog: undervoltage 15m (cooldown 60m), session 70% 30m.