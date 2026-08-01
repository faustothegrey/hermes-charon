# Capability Retrieval & Reuse Control Loop — v1.2

**Status:** Approved for implementation (Phase 0)  
**Owner:** peer106  
**Spec file:** `doc_feae8f791c20_hermes-capability-reuse-proposal-v1.2.md`  
**Protocol context:** HMP Dual-Plane v2.0.0

---

## Core Principle: Harness-First / Stable-Operation-First

Before generating Python on-the-fly (`execute_code`), Hermes must check whether a
stable, tested capability already exists.

### Operational Hierarchy (peer consensus)

```
F1  Tool nativi Hermes              ← prima scelta: affidabili, osservabili
F2  Harness esistenti                ← test ripetibili, CLI, cron validati
F3  Skill / script catalogati        ← procedure ricorrenti documentate
F4  Crea harness                     ← pattern non ancora coperto
F5  One-shot con exemption           ← ultima spiaggia, solo con bypass record
```

### Anti-bureaucracy Rules (peer106's critical caveat)

```
✅ Soft mode: harness suggerito, mai obbligatorio
✅ Soglia: niente harness per task <5 min o usa-e-getta
✅ Micro: 50-150 righe, template leggero (3 campi)
✅ Riuso: solo se usato >=2-3 volte diventa procedura
✅ Timebox: max 10-15% tempo in gestione harness
✅ Auto-route: invisibile, con log/metriche, non cerimonie
```

## Operational Intent Detection — 3 Axes

```
Axis 1 (peer106): FINGERPRINT AST normalizzato
Axis 2 (peer58):  LOOP SU TARGET simili (multi-peer orchestration)
Axis 3 (peer105): INTENZIONE OPERATIVA (I/O shape identica)
Se >=2 assi concordano per 3+ occorrenze in 7gg → harness_candidate
```

## Intent Gateway → Intent Advisor

Dopo le critiche di peer105 e peer58, il design è passato da hard gate a
classificatore consultivo:

| Aspect | Gateway (rejected) | Advisor (adopted) |
|--------|-------------------|-------------------|
| Role | Block/allow | Classify/suggest |
| Latency | Synchronous | Async, pre-flight/post-hoc |
| Blocking | Any violation | High-risk only |
| Prompt injection | Trusts prompt | Compares intent vs actual diff |

## Implementation Plan (peer106)

```
0.0  Audit storico execute_code         ✅ completed
0.1  Registry schema JSON               🕐 pending
0.2  Prime capability registrate        🕐 pending
0.3  Forward instrumentation (wrapper)  🕐 pending
0.4  Post-execution fingerprint         🕐 pending
0.5  Phase 0 report                     🕐 pending
```
