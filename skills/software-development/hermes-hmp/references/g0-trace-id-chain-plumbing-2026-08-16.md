# G0 — request-unique trace_id: HMP adapter → core → capability-reuse (2026-08-16)

## Contesto

P0-10: il consumer_loop dell'HMP adapter usava `chat_id`/peer come trace_id;
la retrieval REALE di capability-reuse (pre_llm_call) ricadeva su
`sender_id`/peer. Fix richiesto: UUID v4 per richiesta, propagato in tutta la
catena. Verificato LIVE su Charon (0.17.0) e peer141 (0.20.1) — 2/2 PASS
entrambi, stesso UUID in HMP ingress E capability-reuse retrieval.

## Catena dati completa (dove va il trace_id)

```
adapter._process_item()
  → trace_id = str(uuid.uuid4())          ← GENERARE PRIMA del MessageEvent
  → MessageEvent(..., trace_id=trace_id)  ← campo nuovo sul dataclass
  → BasePlatformAdapter.handle_message(event)
  → gateway runner → _run_agent(... trace_id=getattr(event,"trace_id",None))
  → _run_agent_inner → AIAgent(trace_id=...)
  → init_agent: agent._trace_id = trace_id or ""
  → turn_context invoke_hook("pre_llm_call", ..., trace_id=getattr(agent,"_trace_id",""))
  → capability-reuse retriever: _hc.get("trace_id") è la PRIMA priorità
    (retriever.py ~583) — nessuna modifica a capability-reuse 2.6.0 necessaria
```

## I 6 tocchi core (Charon 0.17.0 — 22 inserzioni, 0 rimozioni)

| # | File | Modifica |
|---|------|----------|
| 1 | `gateway/platforms/base.py` | `MessageEvent.trace_id: Optional[str] = None` |
| 2 | `plugins/hmp/adapter.py` | UUID generato PRIMA di MessageEvent, passato al costruttore |
| 3 | `gateway/run.py` | `trace_id=getattr(event,"trace_id",None)` → _run_agent (entrambi i branch multiplex) → _run_agent_inner → AIAgent(trace_id=...) |
| 4 | `run_agent.py` | `AIAgent.__init__` parametro `trace_id` → passato a init_agent |
| 5 | `agent/agent_init.py` | parametro + `agent._trace_id = trace_id or ""` (pattern vicino a `_user_id`) |
| 6 | `agent/turn_context.py` | kwargs pre_llm_call += `trace_id=getattr(agent,"_trace_id","") or ""` |

## PITFALL 1 — adapter-only NON basta (il perché)

I kwargs di `pre_llm_call` in turn_context sono **hardcoded** (session_id,
task_id, turn_id, user_message, model, platform, sender_id). Il `raw_message`
del MessageEvent NON arriva a turn_context (in run.py è usato solo da
`_get_guild_id` per Discord). Quindi l'UUID messo solo nel body/raw NON
raggiunge mai il retriever. Serve il plumbing core sopra. Verificare PRIMA
leggendo turn_context, non assumere che l'adapter basti.

## PITFALL 2 — AGENT CACHE: secondo turno della stessa sessione

Gli agent sono cachati per sessione (`_agent_cache`, path
`reused_cached_agent`). Il secondo messaggio RIUSA l'agente e NON passa da
init_agent → `_trace_id` resterebbe quello del primo turno. Fix (scoperto da
peer141, confermato su 0.17.0): nel path cache-reuse di run.py, dopo
`agent.max_iterations = max_iterations`, aggiungere:
```python
if trace_id is not None:
    agent._trace_id = trace_id or ""
```

## PITFALL 3 — NameError silenzioso (consumer loop error)

Ordine sbagliato in _process_item: `MessageEvent(trace_id=trace_id)` PRIMA di
`trace_id = str(uuid.uuid4())` → NameError → il safety net del consumer_loop
marca il messaggio `failed` con "consumer loop error" e NON lascia eventi nel
log (sembra un problema di rete, non è un problema di codice). Generare
l'UUID come PRIMA cosa del metodo.

## PITFALL 4 — test live: serve un messaggio che matcha una capability

`ctrl.retrieve()` ritorna `None` silenzioso se nessuna capability del registry
supera la soglia (es. "rispondi solo OK" non matcha nulla → NESSUN
retrieval_event capability-reuse, solo quelli dell'adapter). Per dimostrare la
catena end-to-end serve un messaggio che matcha una capability TRUSTED del
registry (es. `hmp-healthcheck v1.0.0` → "check HMP health for peerX"). Con
provenance esplicita `organic_live` nel body HMP.

## Versioni diverse di Hermes — stessa patch, ancoraggi diversi

0.17.0 (Charon): AIAgent.__init__ è un forwarder a init_agent (run_agent.py).
0.20.1 (peer141): idem ma con TurnContext dataclass separato (`gateway/turn_context.py`) — la catena passa da `ctx.trace_id` non dall'evento. **MAI
scambiarsi file core tra versioni diverse**: ognuno applica la patch sul
proprio core. Verifica incrociata: mappare gli ancoraggi per versione PRIMA
di implementare (peer141 ha prodotto la mappa 0.20.1 in autonomia).

## Verifica live (recipe)

1. Baseline: `wc -l events.jsonl` sul peer target.
2. Inviare messaggio con provenance organic_live e testo che matcha una
   capability trusted (hmp-healthcheck).
3. Sul log eventi del peer target cercare per preview:
   - retrieval_event src=hmp_plugin.consumer_loop (ingress)
   - retrieval_event src=hook_context.capability_reuse_provenance (reale)
   - stessi trace_id UUID v4; secondo messaggio → UUID diverso.
4. I messaggi verso un peer generano eventi sul log DEL PEER, non sul
   mittente — per testare il proprio gateway inviare a se stessi (POST locale
   con from=peerX) o chiedere a un peer di inviare.

## Artefatti

- Patch 0.17.0: `~/.hermes/g0-bundle/core-patches/g0-core-0.17.0-charon.patch`
- Bundle review: `~/.hermes/g0-bundle-review.zip` (adapter + patch + manifest + test + report)
- Test: `analysis/test_g0_adapter.py` (30/30 regression + plumbing 4/4)
