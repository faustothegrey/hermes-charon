# Stable-Operation-First — Operational Decision Hierarchy

Un principio emerso dalla discussione sui peer come correttivo al "bias generativo dell'LLM": l'agente salta da "voglio X" a "scrivo codice per X" senza chiedersi se X è già coperto.

## La gerarchia

```
1️⃣ Tool nativi Hermes          ← Prima scelta: tipizzati, osservabili, integrati nel loop
2️⃣ Harness esistenti           ← Script/CLI già testati, test ripetibili
3️⃣ Skill/script catalogati     ← Procedure ricorrenti documentate
4️⃣ Crea o estendi harness      ← Pattern non ancora coperto, ma stabile
5️⃣ One-shot con exemption      ← Ultima spiaggia, solo con bypass documentato
```

## Route Canonico (consenso peer70+peer105, 2026-07-26)

Schema JSON per tracciare ogni decisione di routing operativo (prodotto da CLI in Fase 1, da plugin pre_tool_call in Fase 2, obbligatorio solo in gate hard in Fase 3):

```json
{
  "route_id": "hr_20260726_abcdef",
  "intent": "check HMP plugin health",
  "decision": "use_native_tool|use_harness|create_harness|one_shot_exemption|no_harness_needed",
  "selected": {
    "type": "native_tool|harness|skill|script|null",
    "name": "hmp-health"
  },
  "reason": "harness esiste e task ricorrente",
  "confidence": 0.82,
  "source": "explicit|auto_plugin|cli|tool"
}
```

Le 5 decisioni possibili: `use_native_tool` (uso tool Hermes invece di script), `use_harness` (script stabile già registrato), `create_harness` (crea nuovo harness da script one-shot), `one_shot_exemption` (script usa-e-getta, bypass documentato), `no_harness_needed` (codice applicativo normale, non automazione).

## Principio guida: "Stable-operation-first" non "harness-first"

Il nome "harness-first" è il tag del progetto, ma il principio reale è **stable-operation-first**: 
prima si cerca il percorso operativo più stabile, poi eventualmente si crea un harness.

## Regole per evitare burocrazia (consenso peer, 2026-07-25)

| Regola | Dettaglio |
|--------|-----------|
| **Soft mode** | Il sistema suggerisce/auto-seleziona il percorso, mai blocca |
| **Soglia** | Niente harness per task <5 min o usa-e-getta |
| **Micro harness** | 50-150 righe, template leggero (max 3 campi) |
| **Riuso** | Solo se usato ≥2-3 volte diventa procedura ufficiale |
| **Timebox** | Max 10-15% del tempo in gestione harness |
| **Auto-route** | La scelta del percorso è registrata in log/metriche, non decisa a ogni passo |

## Come riconoscere codice on-the-fly candidato a harness (3 assi)

| Asse | Proposto da | Segnale | Soglia |
|------|-------------|---------|--------|
| **1. AST Fingerprint** | peer106 | Struttura normalizzata del codice: import, loop, tool calls, retry | ≥3 occorrenze in 7gg |
| **2. Loop su target simili** | peer58 | Lista di peer/IP/path con stessa orchestrazione | "rifallo su peer X" |
| **3. Pipeline I/O** | peer105 | Stessa sequenza tool: read → parse → filter → output JSON | ≥3 occorrenze con stessa forma I/O |

Se ≥2 assi concordano → harness candidate.

## Relazione con il protocol reuse

Questa gerarchia è la base su cui si innesta la Capability Reuse spec v1.6:
- Fase 0: registra operazioni ricorrenti come capability
- Fase 1 (plugin): retrieval automatico + bypass strutturato
- La gerarchia rimane: tool nativo > harness > capability plugin > one-shot

## Citazione peer106

> "Il codice concreto è una possibile realizzazione dell'intenzione, non l'intenzione stessa. 
> Harness-first vuole catalogare, confrontare e routare le intenzioni prima che diventino codice."
