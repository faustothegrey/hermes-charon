# REGISTRY NOTICE flow — 16/08/2026

Sessione reale: definizione del **Local Skill registry** (ex-"HMP registry") +
pubblicazione selettiva hmp 1.26.0 + notifica ai peer attivi.

> **Status: PREFERRED PATH, non strictly mandatory.** La notifica HMP con
> resync autonomo è il modo consigliato per distribuire definizioni/versioni
> ai peer; il SCP manuale resta un'alternativa accettabile (controllo diretto,
> peer offline, o preferenza dell'operatore).

## Contesto

Fausto ha chiesto di rinominare concettualmente il registry: quando dice
"the skill registry" intende quello INTERNO del mesh, non lo skills hub
pubblico Hermes. Definizione notificata ai peer:

> Local Skill registry (ex-HMP registry) = registry interno del mesh:
> `~/.hermes/registry/` su peer70 (registry.json + peers/*.json, publish via
> registry-publish.py, skill con frontmatter `type: custom`). NON è lo skills
> hub pubblico Hermes.

## Pubblicazione selettiva (hmp sì, cap-reuse no)

Versioni locali reali al 16/08:
- skill `hermes-hmp`: **1.26.0** (stabile → pubblicata)
- plugin `hmp`: **0.1.4** (stabile → pubblicato)
- skill `capability-reuse`: **2.5.0** locale ma **2.2.0** nel registry (in dev → NON pubblicata)
- plugin `capability-reuse`: idem, fermo a 2.2.0

Comandi di verifica prerequisiti:
```bash
grep -m1 "^version:" ~/.hermes/skills/software-development/hermes-hmp/SKILL.md
grep -m1 "version" ~/.hermes/plugins/hmp/plugin.yaml
```

Aggiornamento manifest (script Python inline su peer70):
```python
pp = json.load(open("peers/peer70.json"))
# solo le voci stabili; le voci in dev si lasciano intatte
for s in pp["skills"]:
    if s["name"] == "hermes-hmp":
        s["version"] = "1.26.0"
for p in pp["plugins"]:
    if p["name"] == "hmp":
        p["version"] = "0.1.4"
pp["updated_at"] = now; pp["registry_updated_at"] = now
json.dump(pp, open("peers/peer70.json", "w"), indent=2)
```
`registry.json` (indice aggregato) NON porta versioni → nessuna modifica.

## Notifica HMP ai peer attivi

Health check (solo peer con `"status":"ok"` e `node_id`):
```bash
curl -sf --connect-timeout 3 http://192.168.178.<ip>:18643/health
```
Online al 16/08: **141, 138, 58** (offline: 106, 128, 84, 105).

Send (POST al gateway target, from_peer nel body):
```bash
MSGID="reg_notice_${p}_$(date +%s%N)"
curl -s -X POST "http://192.168.178.${p}:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"'$MSGID'","from":"peer70","to":"peer'$p'","type":"request","timeout":300,"payload":{"text":"..."}}'
```
Testo del messaggio: 1) definizione registry da salvare in MEMORIA,
2) istruzione di resync autonomo skill hermes-hmp → v1.26.0, 3) fallback:
"se non hai accesso, rispondi chiedendo il tar.gz".

Poll (risposte 10-60s, ripollare fino a `completed`):
```bash
curl -s "http://192.168.178.${p}:18643/hmp/poll/${MSGID}"
```

Fallback distribuzione skill: tar.gz pronto in `~/.hermes/registry/dist/hermes-hmp-1.26.0.tar.gz`
(creato con `tar czf` da `~/.hermes/skills/software-development/`).

## Esito reale

| Peer | Memoria | hmp skill |
|------|---------|-----------|
| 141 | ✅ | resync 1.26.0 |
| 138 | ✅ | già 1.26.0 |
| 58 | ✅ | resync 1.26.0 |

## Pitfall incontrati

- Il DB locale (`~/.hermes/data/hmp_gateway_plugin/messages.db`) traccia i
  messaggi OUTBOUND del gateway locale, non quelli inviati via curl diretto →
  per il poll usare gli ID restituiti dal send (memorizzarli), non cercarli nel DB.
- `sqlite3 .tables` su messages.db può fallire se la tabella ha un nome diverso
  → usare `hmp-read-msg.py --last <peer>` per l'ispezione, non query raw.
- Il registry è spesso STALE rispetto allo stato reale dei peer (vedi
  sezione "Pitfall: registry.json è STANTIO" in SKILL.md) — la notifica HMP
  con conferma esplicita del peer è il modo affidabile di verificare.
