Obsidian vault: ~/Documents/Obsidian Vault/Progetti/Hermes/ per note tecniche.
§
Esecuzione immediata, ripetizione 2x = esegui. HMP > API > SSH.
§
Fausto: risposte concise, OK se registry invariato, tool minimali; GATE: tooling ≠ fase chiusa, serve evidenza empirica prima di closure. Local Skill registry (ex-HMP) = registry interno Fausto (~/.hermes/registry/, publish registry-publish.py, type: custom). Gateway = systemd user hermes-gateway.service.
§
Cron 'once' run_at passato = loop; restart gateway manuale; peer remoti SSH kill -9.
§
G0/G2b CLOSED (17/08); atteso GO sealed Phase1a. Dettagli: vault session-facts-2026-08-17-g0-g2b-review-loop.md.
§
Rebar Phase1: G2 falsifier ACCEPT (ID10) + rework ACCEPT + GO a G3 (ID17, 20/08). Vincoli: baseline G1 fake-server congelata, semantica enforcement G2 fissa; modifica = nuovo item review. Verdetto in staging per peer128 (offline). Dettagli: data/rebar-phase1-verdicts.md.
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
Core 0.17/0.20.1: _delivery_manager solo ≥0.20; gate+sink observe nel middleware solo ≥0.20 (0.17: execute_tool_calls_sequential).
§
Email himalaya: virgilio default; libero invio review; hotmail/yahoo rotti. Review loop = skill code-dev-reviewer + cron watchdog-libero-mail.
§
peer128 .112 = macOS portatile, launchd kickstart -k, SSH fausto.
§
BUG HMP (18/08 peer136): msg delivering orfano se gateway riavvia a metà turno; sessione bloccata; workaround re-invio; fix da analizzare. Dettagli: vault session-facts.
§
peer58 .58 HMP :18643 hmp 0.1.3, online.
§
Skill essenziali (TUTTE PINNED 18/08, ortogonali): memory-vault-hybrid, hermes-hmp, code-dev-reviewer, skill-registry-protocol, mesh-citizenship.