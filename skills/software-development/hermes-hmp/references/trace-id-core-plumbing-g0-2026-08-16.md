# G0 — trace_id request-unique end-to-end (16/08/2026)

Contesto: capability-reuse 2.6.0 ACCEPT, P0-10 aperto — l'adapter HMP generava
UUID v4 per richiesta ma il retrieval reale di capability-reuse (pre_llm_call)
ricadeva su sender_id/peer. Fix verificato live su Charon 0.17.0 e peer141 0.20.1.

## Perché adapter-only NON basta (lezione chiave)

I kwargs di `pre_llm_call` sono **hardcoded** in `agent/turn_context.py`
(lista fissa: session_id, task_id, turn_id, user_message, conversation_history,
is_first_turn, model, platform, sender_id). Niente `trace_id`, niente
`chat_id`, niente `raw_message`. Il `raw_message` del MessageEvent non arriva
a turn_context (in run.py è usato solo per `_get_guild_id()` di Discord).
Quindi un adapter non può iniettare metadata nel hook context senza plumbing core.

## Il fix (7 tocchi, nessuna modifica a capability-reuse)

1. `gateway/platforms/base.py`: `MessageEvent.trace_id: Optional[str] = None`
2. `adapter.py` (HMP plugin): generare `trace_id = str(uuid.uuid4())` **PRIMA**
   della costruzione di MessageEvent, passare `trace_id=trace_id` nel costruttore
3. `gateway/run.py`: `trace_id=getattr(event, "trace_id", None)` → `_run_agent`
   → `_run_agent_inner` → `AIAgent(trace_id=...)` (entrambi i branch multiplex)
4. `run_agent.py` AIAgent forwarder: parametro + pass-through a `init_agent`
5. `agent/agent_init.py`: parametro + `agent._trace_id = trace_id or ""`
6. `agent/turn_context.py`: kwargs += `trace_id=getattr(agent, "_trace_id", "") or ""`
7. (fix cache + pending, sotto)

Il retriever di capability-reuse legge già `hook_context["trace_id"]` come
prima priorità (`retriever.py` ~583) → nessuna modifica alla skill 2.6.0.

## Due gotcha scoperti dal test stessa-sessione (entrambi fixati)

1. **Agent cache**: gli agent sono cachati per sessione; il secondo turno riusa
   l'agente e SALTA `init_agent` → il trace resterebbe quello del primo turno.
   Fix: refresh esplicito nel path cache-reuse di run.py:
   `if trace_id is not None: agent._trace_id = trace_id or ""`.
2. **Pending drain**: un follow-up su sessione attiva passa dalla `_run_agent`
   ricorsiva (run.py ~17953) che NON passava trace_id → fallback a peer.
   Fix: `trace_id=getattr(pending_event, "trace_id", None) if pending_event is not None else None`.

## Ancoraggi dual-core (mai scambiare file core tra versioni)

Stesso design, ancoraggi diversi:
- **0.17.0 (Charon)**: AIAgent.__init__ forwarder → init_agent; kwargs hook ~riga 419.
- **0.20.1 (peer141)**: forwarder su righe diverse; il gateway usa un dataclass
  `TurnContext` separato (`gateway/turn_context.py`) invece dell'evento grezzo →
  serve `TurnContext.trace_id` + catena ctx; cache-reuse refresh ~run.py:5382.
Per la review servono patch esatte PER VERSIONE con sha256 (`git diff` o
`diff -u` sui file modificati).

## Protocollo di test live (cosa dimostra davvero la catena)

- **"rispondi solo OK" NON trigghera' il retrieval**: `retrieve()` ritorna
  None silenzioso se nessuna capability registrata supera la soglia. Usare un
  messaggio che matcha una capability TRUSTED registrata (es. "check HMP health
  for <peer>" → hmp-healthcheck@1.0.0 nel registry).
- Distinguere ingress adapter dal retriever reale via `provenance.source`:
  `hmp_plugin.consumer_loop` = adapter; `hook_context.capability_reuse_provenance`
  = retrieval REALE pre_llm_call.
- Test stessa-sessione: 2 request con `session_id` condiviso, seconda ~2s dopo
  la prima (forza pending-drain + agent cache). Entrambe devono avere stesso
  UUID tra ingress e retrieval, e UUID-A ≠ UUID-B.
- Verifica in `~/.hermes/data/reuse-observer/events.jsonl` (schema con trace_id
  top-level). I retrieval con candidates vuoti sono comunque emessi (se il
  registry ha capability), ma con provenance/eligible coerenti al fail-closed.

## Packaging per review esterna (lezione dai 4 blocker P0-1..P0-4)

- Il report DEVE descrivere l'artefatto esatto (hash, stato) — un report stale
  (hash vecchi, "nessuna patch core") fa rigettare il bundle.
- Includere: patch core esatte per versione (sha256), raw live JSONL, test di
  plumbing con OUTPUT congelato, adapter source + hash, manifest.
- Un test che mocka `handle_message` prova solo l'adapter, NON la catena core →
  serve un plumbing test che attraversa MessageEvent→AIAgent→kwargs→retriever.
- La dipendenza `adapter REQUIRES core plumbing` (TypeError su core vanilla)
  va trattata come release surface separata (base commit, apply fail-closed).

## Bug incontrato (ordine di definizione)

`trace_id=trace_id` nella costruzione di MessageEvent PRIMA di
`trace_id = str(uuid.uuid4())` → NameError → "consumer loop error" nel DB
(messaggi falliti silenziosi). Generare l'UUID prima dell'evento.

## Esito review (16/08): P0-10 CLOSED, G0 NO-GO per deployment identity

Il reviewer ha ACCETTATO trace plumbing + adapter (P0-10 chiuso, prova runtime
same-session su entrambi i core) ma ha RIGETTATO "G0 fully closed / pre-seal
ready" SOLO per identità di deployment/cohort, non per codice. Lezioni:

- **Bundle finale = report che descrive l'artefatto esatto**: hash reali delle
  patch, base commit git dei due core (`git rev-parse HEAD`), patch 0.20.1
  inclusa (non "richiesta"), evidence raw di entrambi i peer. Un report stale
  (hash vecchi, "patch in attesa") fa rigettare anche un bundle con codice ok.
- **Partial plugin-version misalignment (pitfall di classe)**: la versione di
  capability-reuse vive in PIÙ file — `v244_metadata.py PLUGIN_VERSION`,
  `protocol.py VERSION`, `event_store.py`, `retriever.py`,
  `review_queue.py EXPECTED_PLUGIN_VERSION`. Un sync parziale lascia le real
  retrieval che dichiarano la versione VECCHIA (peer141 dichiarava 2.5.0 pur
  avendo event_store/retriever a 2.6.0). Prima di un pre-seal: grep della
  versione in TUTTI i file del plugin, non solo SKILL.md/plugin.yaml.
- **Pre-seal deployment checklist** (dal reviewer): allineare il plugin alla
  versione ACCEPTED su entrambi i peer → stesso artifact hash → NUOVO
  deployment_id (non riusare `dep-v250-...`) → deployment_timestamp UTC
  coerente tra peer (peer141 era a −2h) → collector_peer_id configurato e
  provato → cohort_label verificato → 1 richiesta per direzione con envelope
  completa. Solo allora: "G0 CLOSED → GO to sealed Phase 1a holdout".
- Il gate fail-closed funziona: retrieval con provenance invalid (unknown,
  valid=false) sono NON-eligible per l'organic holdout — comportamento
  desiderato, non bug.

## Pre-seal eseguito (16/08 sera): 7/7 PASS su entrambi i core

Dopo la review, il pre-seal smoke è stato eseguito e completato:

### Artifact hash canonico (metodo impl-capreuse)

Il reviewer richiedeva l'identità ESATTA dell'artifact 2.6.0. Il metodo
canonico (usato da peer141, verificato identico su entrambi i nodi):
```python
h = hashlib.sha256()
for f in sorted(Path(plugin_dir).glob('*.py')):   # SOLO top-level, NON ricorsivo, NON zip
    h.update(f.name.encode())                     # name
    h.update(f.read_bytes())                      # + content
```
11 file (init, compatibility, dispatcher, event_store, execution_plan,
labels_store, protocol, registry, retriever, review_queue, v244_metadata).
NON coincide con: sha256 dello zip, cumulativo dei .py DENTRO lo zip,
names+bytes dello zip, o cumulativo ricorsivo della dir — tutti metodi
diversi che ho provato prima di chiedere a peer141. Congelare il metodo
nel seal, non solo il valore.

### Pitfall: /proc/<pid>/environ NON mostra le var caricate da dotenv

Verificando `CAPABILITY_REUSE_COLLECTOR_PEER_ID` dopo l'aggiunta a
`~/.hermes/.env` + restart, `/proc/<pid>/environ` la mostrava MANCANTE —
falso negativo: `load_hermes_dotenv()` (hermes_cli/env_loader.py) carica il
`.env` a runtime con `override=True`, quindi /proc/environ (env INITIALE del
processo) non la contiene. **Verificare comportamentalmente** (mandare un
messaggio e ispezionare l'envelope nell'evento), non via /proc/environ.

### Envelope pre-seal verificato (entrambi i nodi)

| Campo | Valore congelato |
|---|---|
| trace_id | UUID v4 unico, stesso in ingress e real retrieval |
| plugin_version | 2.6.0 (peer141 allineato: v244_metadata.py + protocol.py) |
| plugin_artifact_hash | ebab8ae6… (impl-capreuse, identico su entrambi) |
| deployment_id | dep-v260-phase0-p141p70-20260816T213821Z (NUOVO, non v250) |
| deployment_timestamp | 21:38:21Z UTC, coerente (peer141 era a −2h) |
| collector_peer_id | peer70 (da .env, non vuoto) |
| cohort_label | phase0_p141_p70 |

Checklist pre-seal in `SKILL.md` (sezione 📣 REGISTRY NOTICE / pre-seal) e
report in `~/.hermes/g0-bundle/`. Verdetto atteso reviewer: G0 CLOSED →
GO to sealed Phase 1a organic holdout.

