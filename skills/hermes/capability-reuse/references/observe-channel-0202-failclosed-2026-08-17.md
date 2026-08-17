# Observe-channel core patch: stato 0.20.2 e pattern fail-closed (2026-08-17)

## Verifiche eseguite da peer70 (fatti, non assunzioni)

| Verifica | Fonte | Esito |
|----------|-------|-------|
| Manifest varianti observe-channel | `~/.hermes/patches-core/patch-manifest.json` | Solo `0.17.0` e `0.20.1`. NESSUNA variante 0.20.2 |
| `get_pre_tool_call_block_message` nel core locale | search_files in `~/.hermes/hermes-agent/` | 0 risultati → NON upstream in 0.17.0 |
| `plugins.py` @ cf64ca2 (0.20.2) | raw.githubusercontent.com (estratto) | Hook list completa (pre_tool_call, post_tool_call, pre_llm_call, transform_*, pre_verify, API/session/subagent/gateway/approval/kanban) — NESSUN `feedback_sink` né `get_pre_tool_call_block_message` |
| `gateway/run.py` @ cf64ca2 | raw GitHub (estratto) | Nessun `tool.considered` nel pipeline/progress rendering |
| `agent/tool_executor.py` @ cf64ca2 | raw GitHub (estratto) | `_execute_tool_calls_sequential/concurrent`, authorization gate, checkpoints — NESSUN `feedback_sink` |
| web_search `get_pre_tool_call_block_message` @ cf64ca2 | web_search | 0 risultati |

## Conclusioni

1. **Observe-channel NON è upstream in 0.20.2** — è ancora esclusivamente una
   patch (nessuno dei 3 file a cf64ca2 contiene la funzionalità).
2. **Nessuna patch 0.20.2 recensita esiste** — il manifest immutabile ha solo:
   - `0.20.1` → `observe-channel-core-0.20.1.patch` (sha256
     `0e97fc8bc2847b17590fca786eec4926a9fbf3b43e76af7cff24b32c223a557c`, base `c896c09`)
   - `0.17.0` → `observe-channel-core-0.17.0.patch` (sha256
     `852cc71f5cbfd8e326eb26ef23266b25903dca59a20e3b51cc89b9c97f835f27`, base `f860492`)
3. **Mai applicare la patch 0.20.1 a 0.20.2**: target/base diversi, nessun
   evidence di review per quel base.

## Pattern FAIL-CLOSED per preparazione patch su core non ottenibile

Quando una richiesta chiede "prepara patch recensita per core X" e la baseline
esatta NON è ottenibile/verificabile localmente (es. core locale diverso, terminal
bloccato, nessuna tree del core target):

1. **Verificare upstream prima di tutto** (raw.githubusercontent.com per i 3 file
   del core target + web_search per i simboli chiave). Se la funzionalità esiste
   già upstream → risposta: "niente patch necessaria".
2. **Se non upstream e nessuna variante nel manifest** → NON stadiare artefatti
   finti. Preimage hash, compile e smoke richiedono la tree esatta: senza di essa
   ogni artefatto sarebbe non verificato.
3. **Rispondere FAIL-CLOSED** con: tabella verifiche (fonte + esito), varianti
   esistenti nel manifest, motivo per cui la baseline non è ottenibile, e 2
   opzioni concrete (peer prepara localmente + io verifico; oppure autorizzazione
   a clonare il core target in staging).
4. Non modificare MAI il peer target durante la preparazione.

## Nota: una skill, patch per core version

La skill capability-reuse è UNA versione su tutti i peer; la patch è per-core.
`scripts/apply-core-patch.sh` (v0.3.0) gestisce: `--list`, `--status`, `--check`
(0=applicata, 2=pronta, 3=conflitto), `--smoke` (funzionale, exit 4 su fail),
`--gate` (check+smoke), con base_commit HARD-fail (P0-3) e sha256 vs manifest.
Le patch vivono FUORI dal sync della skill in `~/.hermes/patches-core/`
(search order: env `CAPREUSE_PATCHES_DIR` → `~/.hermes/patches-core` → legacy
`<skill>/patches`).
