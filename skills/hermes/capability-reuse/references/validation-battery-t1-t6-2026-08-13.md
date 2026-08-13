# Validation battery T1-T6 (2026-08-13) — capability-reuse 2.4.16

Batteria di test concordata tra peer70 e peer106 per validare la 2.4.16
(clean-cohort/live-metadata gates). Risultati e fix applicati.

## Risultati

| Test | Esito | Note |
|------|-------|------|
| T1 Artifact Identity | ✅ PASS | Versioni interne allineate (SKILL.md/plugin.yaml/protocol.py = 2.4.16), gateway riavviato post-deploy. Il deployment-manifest.json è l'autorità — aggiornarlo OGNI volta che si promuove una versione |
| T2 Clean Cohort | ✅ PASS | Dopo fix: retrieval event con traffic_type=organic_peer, requester_peer_id, processing_peer_id, provenance=organic_live, schema 1.2 — 10/10 campi |
| T3 Disposition Accounting | ✅ PASS | Dopo fix script: 143 retrieval = 123 review + 20 excluded, zero orfani |
| T4 Eligibility Fail-Closed | ✅ PASS | 13/13 casi + flag injection: formal_holdout_eligible ricalcolato da campi trusted, MAI accettato come flag in input |
| T5a Reversed/Rejection | ✅ PASS | 10/10 dopo fix pattern italiani |
| T5b Cross-Peer | ✅ PASS | peer58 emette la propria retrieval chain con metadati live (processing_peer=peer58, requester=peer70) |
| T6 Scope | — | Dichiarazione scope peer58/peer106 da includere nel report finale |

## Fix applicati

### T2: metadati live-shadow nel consumer_loop del plugin HMP
Il retrieval event usciva con traffic_type=unknown perché il plugin emetteva
`emit_retrieval` senza metadati. Fix: nel consumer_loop di adapter.py passare:
- `traffic_type="organic_peer"` (da from_peer)
- `requester={actor_type: agent, actor_id: hmp:<peer>, request_channel: hmp,
  requester_peer_id: <from_peer>, processing_peer_id: self.node_id}`
- `provenance="organic_live"`, `provenance_source="hmp_plugin.consumer_loop"`

### T3: disposition accounting nello script review queue
`generate-review-queue-v245.py` faceva `continue` sui retrieval senza candidates —
20 eventi (3 organici!) sparivano senza disposition. Fix: invece di saltare,
creare un record excluded con `disposition: excluded,
disposition_reason: no_reviewable_candidate` + metadati (traffic_type,
requester_peer_id, processing_peer_id, raw_request_ref). Aggiunto
`excluded_records` e `disposition_accounting_total` al summary JSON.

### T5a: pattern mutating italiani mancanti
`_extract_request_effect` in retriever.py copriva solo termini inglesi —
un prompt operatore in italiano ("controlla health e se giu riavvialo") veniva
classificato read_only → poteva aprire active decision pericolosa. Fix:
- mutating_terms italiani: riavvia/riavvialo/ferma/arresta/disattiva/attiva/
  aggiorna/riconfigura/spegnilo/accendilo/termina/sospendi/riprendi/cambia/
  modifica/sostituisci/installa/rimuovi/elimina/invia/scrivi/crea/cancella
- composite patterns italiani: "se non healthy riavvia", "controlla X e riavvialo"
- read_terms italiani: mostra/stato/verifica/controlla/salute/elenco/lista
- non_operational italiani: spiega/descrivi/come funziona/dimmi come

**Lezione**: la rete peer è italofona — qualsiasi classificazione NLP della skill
deve coprire sia inglese sia italiano, e i casi di sicurezza (mutating) vanno
testati in entrambe le lingue.

## Test rapido della classificazione
```bash
cd ~/.hermes/skills/hermes/capability-reuse && python3 -c "
import sys; sys.path.insert(0, '.')
from plugin.retriever import _extract_request_effect
for q in ['check health and restart if unhealthy', 'controlla health e se giu riavvialo',
          'mostra lo stato di peer58', 'spiega come funziona il healthcheck']:
    print(q, '->', _extract_request_effect(q))
"
```
