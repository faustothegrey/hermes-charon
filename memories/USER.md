Fausto: azione > attesa. "E poi?"=agisci. "basta X"=stop. HMP primario, API fallback, SSH manutenzione. Tool > harness > skill > one-shot. Risposte complete dopo tool call, no tool call inutili.
§
Registry sync: OK se invariato, compact JSON se cambiato. Mai tool call inutili.
§
Risposte concise, evidenze concrete, niente teoria. Distinguere tooling da validation.
§
Peer58 preferisce minimal protocol. Solo OK o JSON. No extra tool call durante registry sync.
§
Peer upgrade: canary scelto da Fausto (ago-2026: peer141 Stella; prima peer58), poi idle, coordinator last. Fausto fa l'upgrade lui, agente verifica dopo suo OK. Intervieni solo su fallimento. Verifica: HMP bidir, plugin, config, gateway.
§
Registry sync: heartbeat-only changes (solo last_seen) = "OK" diretto, nessun tool call né JSON. Solo cambiamenti strutturali (nuovi peer, skill/plugin modificati) meritano risposta con compact JSON.
§
Fausto: stile architetturale concreto, comunicazione italo-inglese. Preferisce: step revertabili, soft mode (mai hard gate), testing prima del deploy, rollout graduale peer-by-peer, server-side processing, 1 chiamata HTTP per azione (resto harness), push model su polling. Odia burocrazia operativa — "stable-operation-first" non deve diventare overhead. Documenta via email (Virgilio→Gmail).
§
Chiamami ALICE.