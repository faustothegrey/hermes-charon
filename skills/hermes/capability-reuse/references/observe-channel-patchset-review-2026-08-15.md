# Observe-channel patchset: ciclo di review e lezioni (2026-08-15)

Storia: patchset observe-channel v0.3.0 (per-core-version core patches,
`~/.hermes/patches-core/`, regola: MAI nel sync della skill) — 5 giri di
review (REJECT×4 → ACCEPT), poi vertical slice v2.5.0 (bubble 🔍 con contesto
retrieval). Lezioni dure, riusabili a OGNI bump/review.

## Cosa il reviewer ha rifiutato (e la fix)

| P0/P1 | Fix |
|---|---|
| Patch NON cumulativa (incrementale da base) | rigenera CUMULATIVA `base..HEAD`, verifica su worktree pulito a `base` (apply+compile+reverse) |
| Fail-closed non verificabile (script fuori bundle) | bundle = patches + apply-core-patch.sh + validator + smoke + manifest + SHA256SUMS + README |
| Single-fire affermato ma mai provato | smoke runtime reale (`observe-channel-single-fire-smoke.py`, conteggi hook + sanitize assert + ordering) |
| Sanitizzazione incompleta (solo dict, tab no) | `_sanitize_observe_text` su STRING e dict, tab→spazio, unicode-format rimossi; `_sanitize_bubble_text` nel renderer gateway (seconda difesa) |
| Codice morto (helper, sink, param, import) | `get_pre_tool_call_feedback`, sink morti, `pre_tool_call_feedback_sink`, import `Callable` inutilizzato → rimossi |
| Commenti stale che descrivono codice rimosso | rimozione (documentation noise) |
| Base commit non verificabile | `base_commit` nel manifest + pin nel `--check` (FAIL exit 3 su base falsificato/mancante) + PREIMAGES (blob sha per file) nel manifest, validator verifica gli index del patch |

## PITFALL critici

1. **Increment patch con blocchi identici rimuove l'istanza SBAGLIATA.**
   3 def `_harness_feedback_sink` identiche (dispatch reale, spinner, quiet):
   l'incremento di rimozione ha matchato la def REALE → uso a riga X senza def
   = **NameError a runtime** (py_compile NON lo becca). DOPO ogni incremento
   che rimuove codice: `grep -n "def X" file` + conteggio def/uso + import
   runtime, NON solo compile.

2. **Version bump = test stale.** Ogni bump (2.4.18→2.4.19→2.5.0) lascia i
   test vecchi: fixture `plugin_version`/`cohort_label` e **reason string con
   UNDERSCORE** (`plugin_version_not_2_5_0`) — `sed 's/2\.4\.19/2.5.0/g'` NON
   matcha `2_4_19` (punti vs underscore). Cerca anche `_2_4_19`/`_2_5_0`.
   Allineare in blocco: `EXPECTED_PLUGIN_VERSION`/`EXPECTED_COHORT_LABEL`
   (review_queue.py) + `cohort.json` live (dep id + artifact_hash del nuovo
   rilascio) + SKILL.md version.

3. **Base commit LOCALE** (es. f860492 non su origin/main): la patch applica
   sul tree locale ma il reviewer testa su clone upstream pulito → mitigazione:
   preimage blob shas nel manifest (il reviewer verifica i blob contro il
   rilascio ufficiale). Fallback se rifiutato: rebase su tag upstream.

4. **SHA256SUMS deve coprire TUTTI gli artefatti del bundle** (2 patch +
   manifest + validator + smoke + installer + README + evidence) — il
   validator fail-closed lo impone; `patch-state.json` è node-local e va
   ESCLUSO dal bundle (`--allow-state` solo sul path operativo).

5. **`--gate` salva l'output completo dello smoke come evidence**
   (`evidence/gate-evidence-<ver>-<peer>.txt`) — l'evidence deve essere nel
   bundle e hashata in SHA256SUMS.

## Vertical slice v2.5.0 (bubble 🔍 con contesto retrieval)

- Hook-only: `on_pre_tool_call` (branch non-execute_code) ritorna
  `{"action":"observe","feedback":{kind:retrieval, text:"cap · score",
  duration_ms}}` SE esiste envelope attivo; altrimenti None.
- Vincoli reviewer: match FORTE session+turn, **single-fire per envelope**
  (flag `observe_shown`, consume-on-observe), fail-open senza consumare.
- Coesistenza bubble: harness-feedback emette ⚙️ per OGNI tool, capability-reuse
  🔍 UNA volta per decisione — se non single-fire = N bubble identiche = rumore.
