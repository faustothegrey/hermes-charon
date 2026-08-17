# Reviewer-ready bundle staging (17/08/2026 — peer128 G0+G2b 0.20.1)

Workflow usato per consegnare la patch core cumulativa G0+G2b (Hermes 0.20.1)
a un reviewer esterno (peer128/Copilot advisory) che richiede puntatori esatti
e verifica indipendente, senza eseguire installazioni alla cieca. Consolidato
dalle 6 round di review (core patch → plugin HMP → capability-reuse): ogni
round ha prodotto un FAIL di packaging (non di codice) — le regole sotto sono
il risultato.

## Dove vivono gli artefatti

- Sorgente originale: `~/.hermes/g0-bundle/` (core-patches/, evidence/, manifest.json, report-g0.md, test_g0_adapter.py, test_g0_plumbing_output.txt)
- Bundle staged per peer: `~/.hermes/g0-bundle/peer128-bundle/`
  - `core-patches/g0-g2b-core-0.20.1-peer141-cumulative.patch`
  - `plugins/hmp/` (plugin COMPLETO v0.1.5: plugin.yaml, __init__.py, adapter.py, core.py)
  - `capability-reuse/` (v2.6.0 canonico: 11 .py top-level + plugin.yaml)
  - `manifest-peer128.json`, `README.md`, `evidence/`, `tests/`
- Archivio: `~/.hermes/g0-bundle/peer128-bundle.zip` + **sidecar esterno** `peer128-bundle.zip.sha256`

## Regole del bundle reviewer-ready

1. **Patch per VERSIONE** con SHA-256 + base commit (`git rev-parse HEAD`) — mai "patch in attesa"
2. **Sidecar esterno** per lo zip (`bundle.zip.sha256`), MAI hash ricorsivo dentro il manifest
3. **Output test CONGELATO** + evidence raw JSONL — un "PASS" senza output raw = non reviewable
4. Report che descrive ESATTAMENTE il bundle corrente (hash, file, stato) — report stale = blocker
5. `bundle_clean: true`, no secrets, non-self-modifying, **nessun deploy/restart per il reviewer**

## ⚠️ MANIFEST FLAT 1:1 (FAIL round 4)

Tutte le entry payload vanno nel `files` **top-level**. Una sezione annidata
(es. `capability_reuse.files`) fa contare 16 invece di 29 a un validatore
esterno che legge solo `files` → FAIL. Le sezioni annidate portano SOLO
metadati (version, hash method, note). Il manifest deve essere 1:1 con la
directory reale: verificare set-equality + zero hash drift sia dalla walk
della dir sia dallo zip estratto.

## ⚠️ ORDINE DI PACKAGING FINALE (FAIL round 5: pyc nel zip)

1. Test con `PYTHONDONTWRITEBYTECODE=1` (gli import NON devono scrivere
   `__pycache__` nell'albero da zippare)
2. Rimuovere TUTTI `__pycache__/` e `*.pyc`, poi `assert` zero residui
3. Rigenerare il manifest flat DALL'ALBERO PULITO
4. `zip -r bundle.zip dir/ -x "*.pyc" -x "*__pycache__*"` (l'esclusione esplicita
   serve anche se i pyc sono stati rimossi — un test post-manifest può rigenerarli)
5. Validare lo zip ESTRATTO in temp dir: set-equality manifest↔zip + hash
   per-file, SENZA importare nulla (solo hashing) + `unzip -t`
6. Sidecar esterno `sha256sum` + cross-check CLI

## ⚠️ CANONICAL-PATH RESOLUTION (FAIL round 6)

Un adapter che importa un helper di un plugin dipendente (es. event_store da
capability-reuse) deve risolvere **prima** il path runtime canonico
(`$HERMES_HOME/plugins/capability-reuse`, profile-safe via `get_hermes_home()`),
e usare la copia legacy (`skills/...`) SOLO se espone la surface completa
(`hasattr` su ogni funzione richiesta). `sys.path` mutato solo per un candidato
che passa il check (una copia stale non può oscurare la canonica). Degrado
pulito se incompatibile (`HAS_EVENT_STORE=False`, emit_* = None), mai crash.
Hardcodare il path legacy = su un peer con copia v2.2.0 l'adapter resta
disabilitato anche dopo l'installazione corretta della v2.6.0.

## Atomic deploy & multi-file versioning

- `adapter.py` + `core.py` SI DEPLOYANO INSIEME: l'adapter chiama
  `queue()/dequeue()` assenti nei core più vecchi → copia parziale = 500.
- La versione del plugin vive in PIÙ file — grep TUTTI:
  `v244_metadata.PLUGIN_VERSION`, `protocol.VERSION`,
  `review_queue.EXPECTED_PLUGIN_VERSION`. Sync parziale = retrieval che
  dichiarano la versione vecchia (pitfall pre-seal reale).
- Rollback in COPPIA atomica: ripristinare capability-reuse da solo con
  adapter nuovo attivo = 500.

## Hash canonico artifact (metodo impl-capreuse)

```python
import hashlib, pathlib
h = hashlib.sha256()
for f in sorted(pathlib.Path(plugin_dir).glob("*.py")):  # top-level SOLO, non ricorsivo, non zip
    h.update(f.name.encode())
    h.update(f.read_bytes())
```
Congelare il METODO col valore: zip-sha, cumulativo ricorsivo e
names+bytes-dello-zip danno hash DIVERSI. Il test del bundle va messo FUORI
dalla dir dell'artifact (un .py di test dentro il glob rompe conteggio e hash).
Moduli con relative import (retriever.py) NON importabili top-level: check di
sintassi `compile()` + nota che in produzione si caricano via sys.path package.
Scenari env-isolati in **subprocess** con `HERMES_HOME` (una var custom tipo
`TEST_HERMES_HOME` NON viene letta da get_hermes_home → falso provenienza);
`importlib.reload` fallisce dopo `sys.modules.pop`.

## Base commit & precondizioni di apply

- Patch 0.20.1 generata contro `ddf57637dda3301d2388dee4991ee6d28c8c1793` (peer141/Stella)
- Commit del peer target (es. peer128 `165c889e...`) **NON verificabile dal coordinator**
  (object DB di un'altra versione non presente) → consegnare i comandi di verifica al target:
  ```bash
  git merge-base --is-ancestor ddf57637dda3301d2388dee4991ee6d28c8c1793 HEAD && echo BASE_OK || echo BASE_MISSING
  git apply --check core-patches/<patch>.patch    # dry-run, gate autoritativo
  ```
- `git apply --check` pulito = apply sicuro; fallimento su file con edit locali non
  sovrapposti → usare `--3way`, MAI `reset --hard`/`checkout` (distrugge gli edit locali).

## Conflict guidance (esempio reale)

Patch tocca 6 file core: `agent/agent_init.py`, `agent/turn_context.py`,
`gateway/platforms/base.py`, `gateway/run.py`, `gateway/turn_context.py`, `run_agent.py`.
Il peer target aveva edit non correlati in `hermes_cli/gateway.py` e
`tests/hermes_cli/test_gateway_service.py` → **ortogonali**, nessun conflitto atteso,
gli edit restano intatti. Verifica sempre i path della patch (`grep "^diff --git" patch`)
prima di dichiarare conflitti.

## Verifica contenuto cumulativo (anti-bluffer)

Patch cumulativa G0+G2b deve avere `capability_reuse_context` in TUTTI i 6 file:
```bash
grep -c "capability_reuse_context" <patch>    # 17 match sulla 0.20.1 peer141
```
Una patch solo-trace (G0 senza G2b) = blocker secondo la review (P0-4).

## Flusso operativo

1. Audit ESISTENZA con search una-pattern-per-volta (vedi AUDIT PITFALL in SKILL.md)
2. Copiare artefatti in `peer<X>-bundle/` con core-patches/ + evidence/ + test
3. Scrivere README (precondizioni, apply, backup/rollback, validation, conflict guidance)
4. `manifest-<peer>.json` FLAT con SHA-256 per-file, rigenerato dall'albero pulito
5. `zip -r` con `-x "*.pyc"` + `sha256sum` in sidecar esterno
6. Validare lo zip estratto (set-equality + hash, senza import)
7. Consegnare path + hash + comandi di verifica al reviewer — mai eseguire apply/restart per lui
