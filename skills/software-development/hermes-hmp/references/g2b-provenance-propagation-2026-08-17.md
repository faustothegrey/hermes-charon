# G2b — provenance propagation + review-evidence packaging (17/08/2026)

Continuazione diretta del G0 trace_id plumbing
(`references/trace-id-core-plumbing-g0-2026-08-16.md`). Stesso pattern a 6
tocchi, secondo caso d'uso: propagare metadati request-scoped dall'adapter
fino ai kwargs del hook `pre_llm_call`.

## Problema (finding della review pre-seal)

L'HMP ingress vedeva `provenance.stream=organic_live` (da body.provenance),
ma la REAL capability-reuse retrieval della stessa request UUID aveva
`stream=unknown`, `valid=false`, `reason=invalid_provenance`. La dichiarazione
provenance non viaggiava attraverso `MessageEvent → GatewayRunner → TurnContext
→ pre_llm_call` (a differenza del trace_id). Conseguenza: una vera richiesta
organica sarebbe risultata `formal_holdout_eligible=false` e l'holdout non
avrebbe accumulato le ≥60 coppie richieste.

## Fix (6 tocchi, simmetrici al G0, ZERO modifiche a capability-reuse 2.6.0)

1. **`gateway/platforms/base.py`** — `MessageEvent.capability_reuse_context: Optional[Dict]`
2. **`plugins/hmp/adapter.py`** — helper `_capability_context(raw)`:
   - `capability_reuse_provenance` da `body.provenance` (string) o
     `prov.stream/type/name` (dict)
   - marker esclusione inoltrati VERBATIM se dichiarati: `operator_solicited`,
     `is_solicited`, `solicited`, `operator_seeded`, `is_seeded`, `seeded`,
     `is_test`, `test`, `acceptance`, `is_acceptance`, `calibration`,
     `is_calibration`, `is_retry`, `retry_of`, `scheduled`, `is_scheduled`,
     `cron`, `is_cron`, `traffic_type`, `capability_reuse_traffic_type`
   - **MAI inferire organic da piattaforma/identity** — solo valori dichiarati
   - collegato nel costruttore: `MessageEvent(..., capability_reuse_context=...)`
3. **`run_agent.py`** (forwarder) + **`agent/agent_init.py`** — parametro +
   `agent._capability_reuse_context = capability_reuse_context or None`
4. **`gateway/run.py`** — 3 siti: chiamata iniziale
   (`getattr(event, "capability_reuse_context", None)`), refresh nel
   cache-reuse (`if capability_reuse_context is not None: agent._... = ...`),
   pending-drain (`capability_reuse_context=getattr(pending_event, ...)`)
5. **`agent/turn_context.py`** — kwargs hook costruiti da dict:
   `_hook_kwargs: Dict[str, Any] = {...}` poi `_invoke_hook("pre_llm_call",
   **_hook_kwargs)`; aggiungere `capability_reuse_provenance` + i marker SOLO
   se presenti in `_cr_ctx`
6. Retriever 2.6.0 INVARIATO — già legge `hook_context.capability_reuse_provenance`
   e i marker (fail-closed: marker vincono su qualsiasi dichiarazione organic)

## Verifica live accettata dalla review (smoke operator_solicited)

Richiesta con `provenance=organic_live` + `operator_solicited=true` → la real
retrieval deve mostrare:
- `provenance.stream='organic_live'`, `source='hook_context.capability_reuse_provenance'`, `valid=True`
- `traffic_type='operator_solicited'` (marker vince → formal-ineligible → holdout pulito)

PASS su Charon (trace `9c03caf7-eedb-48e3`) e peer141 (trace `decfd3f5` sul
log Charon / `5edabded` sul log peer141, post-fix).
Trace reali: smoke con testo che matcha `hmp-healthcheck` (trusted) — un testo
banale ("rispondi solo OK") fa ritornare `retrieve()` → None silenzioso, nessun
retrieval da verificare.

## Pitfall CRITICO — provenance deve essere STRINGA pura, non dict

Root cause del FAIL peer141 alla review: `_capability_context` costruiva
`ctx["capability_reuse_provenance"] = {"stream": "organic_live", "source": "body.declared"}`
(DICT). Il retriever `_request_provenance` (retriever.py:405) passa quel valore a
`normalize_provenance(stream=...)` che fa `str(raw).strip()` → il dict diventa
`"{'stream': 'organic_live', ...}"` → fuori da `PROVENANCE_STREAMS` →
`stream=unknown, valid=false, detail=invalid_value, reason=invalid_provenance`.

Fix: **stringa pura** — `ctx["capability_reuse_provenance"] = prov.strip()`
(o `.stream` se dict). Sintomo identico PRIMA/DOPO:
```
PRIMA (dict): stream=unknown  valid=False  reason=invalid_provenance  ← FAIL review
DOPO  (str):  stream=organic_live  valid=True                          ← fix
```
Lezione: quando un valore hook passa per `normalize_provenance`/`str()`,
verificare che sia il tipo che il consumer si aspetta (string), non un dict
strutturato "carino". Un unit-test della catena (adapter → hook kwargs →
_request_provenance → normalize) lo becca prima della review.

## Pitfall — pending-drain perde i metadati (bug trovato dal test stesso-sessione)

2 request consecutive sulla STESSA sessione: REQ-2 (pending drain, sessione
attiva) perdeva trace_id E provenance → fallback a `peer_id` nel retriever.
Fix in entrambe le patch: passare `trace_id` e `capability_reuse_context` dal
`pending_event` nella chiamata ricorsiva `_run_agent(...)` del drain
(run.py ~17953 su 0.17, ~28289 su 0.20.1). Senza questo, il secondo request
di una sessione busy ricade su chat_id/peer.

## Dual-core: MAI scambiare file core

peer70 (0.17.0) e peer141 (0.20.1) applicano lo STESSO delta con ancoraggi
diversi (AIAgent forwarder vs TurnContext su 0.20.1, righe diverse).
Workflow: chi implementa produce la patch per il proprio core; l'altro la
usa come REFERENCE per la propria versione (`scp` al peer → lui adatta).
Ogni bundle deve contenere le patch di ENTRAMBE le versioni con base commit.

## Review-evidence packaging (lezione dai 4 blocker P0-1..P0-4)

Il reviewer ha rifiutato il primo bundle per packaging, non per codice:

| Blocker | Requisito |
|---|---|
| P0-1 | report DEVE descrivere esattamente il bundle corrente (hash, file, stato) — report stale = blocker |
| P0-2 | raw live evidence JSONL nel bundle (eventi reali, trace, catena) — dichiarare "PASS" senza raw = non reviewable |
| P0-3 | output del plumbing test CONGELATO nel bundle (non solo "30/30") — test con mock di handle_message non prova il core |
| P0-4 | patch esatta di OGNI versione core (0.17 + 0.20.1) con hash + base commit |

Checklist bundle reviewer-ready:
- [ ] patch per-version con SHA-256 + base commit (`git rev-parse HEAD`)
- [ ] evidence raw JSONL per nodo (eventi con catena completa: ingress→surface→real retrieval)
- [ ] output test congelato (adapter regression + plumbing end-to-end)
- [ ] manifest.json con SHA di ogni componente — MAI l'hash dell'intero zip dentro lo zip (ricorsivo/stale); usare **sidecar esterno** `bundle.zip.sha256` (stesso pattern release skill)
- [ ] report che matcha il bundle (mai copia di una versione precedente)
- [ ] `bundle_clean: true`, nessun secrets/patches
- [ ] la patch 0.17 inclusa deve essere la CUMULATIVA reale (G0+G2b) del deployment live — una patch trace-only presentata come "cumulativa" = blocker (verificare col grep `capability_reuse_context` nella patch)

Regola pre-holdout (reviewer): le richieste di validazione/smoke vanno marcate
esplicitamente non-organic (`operator_solicited` ecc.) PRIMA dell'ingresso;
`provenance=organic_live` NON si usa come scorciatoia per traffico creato per
raccogliere evidence — il marker esclusione vince e tiene pulito l'holdout.

## Pre-seal deployment identity (allineamento 2.6.0)

- Allineamento plugin peer: `v244_metadata.py` `PLUGIN_VERSION` + `protocol.py`
  `VERSION` — i file più facili da dimenticare quando event_store/retriever
  sono già aggiornati (peer141 dichiarava 2.5.0 pur avendo il resto a 2.6.0)
- Artifact hash CANONICO (metodo "impl-capreuse"): sha256 cumulativo
  `h.update(f.name.encode()); h.update(f.read_bytes())` sui `.py` TOP-LEVEL
  della dir plugin, sorted (11 file) — NON ricorsivo, NON lo zip. Il metodo
  va congelato nel manifest perché metodi diversi (zip sha, cumulativo
  ricorsivo, names+bytes dello zip) danno hash diversi
- `cohort.json`: stesso `deployment_id` + `deployment_timestamp` UTC su
  entrambi i nodi (peer141 era a −2h: ambiguïtà UTC/local da eliminare)
- Collector: `CAPABILITY_REUSE_COLLECTOR_PEER_ID=peer70` in `.env` + restart
  gateway — NOTA: `/proc/<pid>/environ` NON mostra le var caricate da dotenv a
  runtime (falso negativo); verificare nelle retrieval reali, non in /proc
