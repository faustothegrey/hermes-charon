# T6 — Scope & Non-Generalization Statement

**Batteria:** capability-reuse v2.4.16 validation (T1-T6)
**Data:** 2026-08-13
**Coordinatore:** peer70 (Charon)
**Implementatore/fonte:** peer106 (trixie)

---

## 1. Dichiarazione di scope (obbligatoria)

**La validazione è limitata a peer106 + peer58 + peer70. Nessuna generalizzazione alla fleet.**

I risultati T1-T5 sono validi SOLO per:
- Questo deployment (cohort `dep-v2416-peer58-peer106-clean-20260802T114235Z`)
- Questo registry/traffic mix (rete locale Hermes, 5 peer attivi)
- Questi threshold (calcolati sul traffico reale di peer70/106/58)

**Non estendere** questi risultati a: peer84, peer128, peer138, peer141 o a qualsiasi peer non incluso nel cohort, senza una validazione dedicata.

---

## 2. Risultati per test

| Test | Esito | Note |
|---|---|---|
| T1 Artifact Identity | ✅ PASS | versioni interne allineate 2.4.16 (SKILL.md/plugin/protocol), gateway riavviato post-deploy |
| T2 Clean Cohort | ✅ PASS | retrieval event con metadati completi (traffic_type=organic_peer, requester, processing, provenance=organic_live, schema 1.2) — via plugin HMP :18643 |
| T3 Disposition Accounting | ✅ PASS | 146 retrieval events: 126 review records + 20 excluded = 146 (zero orfani). Fix: generate-review-queue assegna disposition esplicita `no_reviewable_candidate` invece di skip silenzioso |
| T4 Eligibility Fail-Closed | ✅ PASS | 13/13 casi + flag injection: `formal_holdout_eligible` ricalcolato da campi trusted, mai accettato come flag |
| T5a Reversed/Rejection | ✅ PASS | 10/10 classificazioni effect (mutating/read_only/non_operational). Fix: pattern compositi italiani aggiunti (`se non healthy riavvialo` → mutating) |
| T5b Cross-Peer | ✅ PASS | peer58 emette la propria retrieval chain (processing_peer=peer58, requester=peer70, provenance organic_live) — non solo risposta HMP |

## 3. Fix applicati durante la validazione

1. **T3**: `scripts/generate-review-queue-v245.py` — i retrieval senza candidates ora ricevono disposition esplicita `excluded/no_reviewable_candidate` (erano saltati silenziosamente)
2. **T5a**: `plugin/retriever.py` — aggiunti termini mutating italiani (riavvia/ferma/disattiva/...) + pattern compositi (`e se giu riavvialo`, `controlla...e poi riavvialo`) + termini read/non_operational italiani
3. **Architettura**: convergenza dual-plane → plugin HMP :18643 completata (ritiro :18644 da tutta la rete)

## 4. Limiti noti della validazione

- **Volumi bassi**: il traffico organico reale osservato è limitato (4 eventi organic_peer su peer70 durante i test). I threshold sono validi per questo volume, NON per scale maggiori.
- **Nessun carico**: non sono stati eseguiti stress test sul plugin sotto carico HMP intenso.
- **peer138/141**: hanno la 2.4.16 installata ma NON sono stati validati (solo peer106/58). La loro inclusione nel cohort richiede la stessa batteria.
- **Registry eterogeneo**: la rete ha peer con versioni Hermes diverse (0.17.0-0.20.0) — i risultati valgono per questa combinazione.

## 5. Threshold validi solo per questo deployment

I threshold di intervento/eligibility calcolati durante questa validazione si applicano ESCLUSIVAMENTE al deployment peer106/58/70. Qualsiasi modifica a registry, traffico o configurazione invalida questi threshold e richiede ri-validazione.

---

*Report generato da peer70 come deliverable T6 della batteria di validazione v2.4.16, concordata con peer106 il 13/08/2026.*
