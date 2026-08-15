#!/usr/bin/env bash
# apply-core-patch.sh v0.3.0 — gestione Observe Channel Patchset
# ==============================================================
# Applica/verifica la patch core observe-channel giusta per la versione
# ESATTA del core Hermes in uso. Una skill (capability-reuse), patch per
# core version.
#
# 🔒 REGOLA DI SICUREZZA (2026-08-15): le patch core NON viaggiano MAI nel
# sync della skill (zip/rsync) — vivono FUORI, nel path standard per tutti i
# peer. Search order: env override → ~/.hermes/patches-core → legacy skill
# patches/ (nodi non ancora migrati).
#
# Schema (reviewer 2026-08-15):
#   - Naming: observe-channel-core-<core_version>.patch
#   - patch-manifest.json: IMMUTABILE, identico su tutti i peer
#     (patchset, patchset_version, varianti con file/sha256/base_commit)
#   - patch-state.json: LOCALE al nodo (applied/applicable/drifted/unsupported)
#   - Compatibilità core ESATTA (0.20.1 → 0.20.1; 0.20.2 → unsupported)
#   - SHA della patch SOLO in manifest/SHA256SUMS, mai dentro il file .patch
#
# Exit codes: 0=OK · 2=PRONTA(applica) · 3=CONFLITTO/drift · 4=SMOKE FAIL
#             5=errore interno · 6=unsupported (core non mappato)

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCHES_DIR="${CAPREUSE_PATCHES_DIR:-$HOME/.hermes/patches-core}"
[ -d "$PATCHES_DIR" ] || PATCHES_DIR="$SKILL_DIR/patches"
HERMES_CORE="${HERMES_CORE_DIR:-$HOME/.hermes/hermes-agent}"
PATCH_MANIFEST="$PATCHES_DIR/patch-manifest.json"
PATCH_STATE="$PATCHES_DIR/patch-state.json"
MANIFEST="$SKILL_DIR/evidence/deployment-manifest.json"

die() { echo "ERROR: $*" >&2; exit 5; }

core_version() {
  local v
  v="$("$HERMES_CORE/venv/bin/python" -c 'import hermes_cli; print(getattr(hermes_cli, "__version__", "unknown"))' 2>/dev/null)"
  [ -z "$v" ] || [ "$v" = "unknown" ] && v="$(grep -m1 '^version' "$HERMES_CORE/pyproject.toml" 2>/dev/null | cut -d'"' -f2)"
  [ -z "$v" ] && die "impossibile rilevare la versione del core in $HERMES_CORE"
  echo "$v"
}

# ── patch-manifest.json (immutabile) ───────────────────────────────────
# Variante per la versione ESATTA del core. Ritorna il JSON della variante
# o stringa vuota se non mappata (o se il manifest è assente → fallback
# legacy con mapping per prefisso per nodi non migrati).
variant_for_core() {
  local core="$1"
  if [ -f "$PATCH_MANIFEST" ]; then
    python3 -c "
import json, sys
try:
    d = json.load(open('$PATCH_MANIFEST'))
    v = d.get('variants', {}).get('$core')
    print(json.dumps(v) if v else '')
except Exception:
    print('')
"
  else
    echo ""
  fi
}

patchset_version() {
  if [ -f "$PATCH_MANIFEST" ]; then
    python3 -c "import json; print(json.load(open('$PATCH_MANIFEST')).get('patchset_version',''))" 2>/dev/null
  fi
}

# ── patch-state.json (locale) ──────────────────────────────────────────
state_get() {
  local key="$1"
  [ -f "$PATCH_STATE" ] || { echo ""; return; }
  python3 -c "
import json, sys
try:
    d = json.load(open('$PATCH_STATE'))
    print(d.get('observe-channel', {}).get('$key', ''))
except Exception:
    print('')
"
}

state_set() {
  python3 -c "
import json, sys, datetime
try:
    d = json.load(open('$PATCH_STATE'))
except Exception:
    d = {}
d['observe-channel'] = {
    'patch_version': '$1',
    'state': '$2',
    'target_core': '$3',
    'patch_sha256': '$4',
    'applied_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'core_commit_before': '$5',
    'core_commit_after': '$6',
}
json.dump(d, open('$PATCH_STATE', 'w'), indent=2)
"
}

# ── verifica integrità ─────────────────────────────────────────────────
patch_sha256() { sha256sum "$1" 2>/dev/null | awk '{print $1}'; }

core_commit() { git -C "$HERMES_CORE" rev-parse --short HEAD 2>/dev/null || echo ""; }

# ── v0.3.0 (P0-3): base anchoring HARD-FAIL ────────────────────────────
# Il base_commit dichiarato nel manifest DEVE esistere come commit nel repo
# del core e DEVE essere antenato del HEAD attuale. Un core che non contiene
# il base (o diverge da esso) NON può dichiararsi coerente col patchset:
# fail-closed su entrambi i path (forward e reverse).
verify_base_hard() {
  local base="$1" mode="$2"
  if [ -z "$base" ]; then
    echo "FAIL-CLOSED: base_commit mancante nel manifest per core $VERSION (variante non valida)" >&2
    exit 3
  fi
  if ! git -C "$HERMES_CORE" cat-file -e "${base}^{commit}" 2>/dev/null; then
    echo "FAIL-CLOSED: base_commit $base NON esiste nel repo del core ($HERMES_CORE) — core non allineato al patchset (mode=$mode)" >&2
    exit 3
  fi
  if ! git -C "$HERMES_CORE" merge-base --is-ancestor "$base" HEAD 2>/dev/null; then
    echo "FAIL-CLOSED: base_commit $base NON è antenato del HEAD $(core_commit) — core divergente dal patchset (mode=$mode); rigenera la patch dal base corretto" >&2
    exit 3
  fi
  echo "  base_commit OK ($mode): $base è antenato del HEAD $(core_commit)"
}

# --status: applicable / applied / drifted / unsupported
status_report() {
  local v core_ver patch_file declared_sha actual_sha base_commit st
  core_ver="$(core_version)"
  v="$(variant_for_core "$core_ver")"
  echo "Observe Channel Patchset $(patchset_version) — core $core_ver"
  if [ -z "$v" ]; then
    echo "  stato: UNSUPPORTED (nessuna variante per core $core_ver nel manifest)"
    return 6
  fi
  patch_file="$PATCHES_DIR/$(echo "$v" | python3 -c 'import json,sys; print(json.load(sys.stdin)["file"])')"
  declared_sha="$(echo "$v" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
  base_commit="$(echo "$v" | python3 -c 'import json,sys; print(json.load(sys.stdin)["base_commit"])')"
  [ -f "$patch_file" ] || { echo "  stato: ERROR (file mancante: $patch_file)"; return 5; }
  actual_sha="$(patch_sha256 "$patch_file")"
  [ "$actual_sha" != "$declared_sha" ] && { echo "  stato: DRIFTED (sha patch $actual_sha ≠ manifest $declared_sha)"; return 3; }
  echo "  patch: $(basename "$patch_file")  sha256 ${declared_sha:0:12}...  base_commit $base_commit"
  echo "  core HEAD: $(core_commit)"
  st="$(state_get state)"
  if (cd "$HERMES_CORE" && git apply --check -R "$patch_file" 2>/dev/null); then
    # reverse-check OK => patch applicata (indipendentemente dallo state file)
    if [ "$st" = "applied" ]; then
      echo "  stato: APPLIED (v$(state_get patch_version), state file coerente)"
    else
      echo "  stato: APPLIED (reverse-check ok; state file assente/incoerente — esegui 'apply' per registrarlo)"
    fi
  elif (cd "$HERMES_CORE" && git apply --check "$patch_file" 2>/dev/null); then
    echo "  stato: APPLICABLE (non applicata, applicabile)"
  else
    echo "  stato: DRIFTED (né reverse né forward check — core modificato/aggiornato?)"
  fi
  return 0
}

list_mapping() {
  echo "Observe Channel Patchset $(patchset_version) — mapping (dir: $PATCHES_DIR)"
  if [ -f "$PATCH_MANIFEST" ]; then
    python3 -c "
import json
d = json.load(open('$PATCH_MANIFEST'))
for core, v in sorted(d.get('variants', {}).items()):
    print('  core %-8s -> %s (v%s, sha256 %s..., base %s)' % (core, v['file'], v.get('variant_version','?'), v['sha256'][:12], v['base_commit']))
"
  else
    echo "  (manifest assente — nodo non migrato; FAIL-CLOSED)"
  fi
  echo "Versione core rilevata: $(core_version)"
}

# ── SMOKE: verifica funzionale del canale observe ─────────────────────
smoke_check() {
  echo "SMOKE: verifica canale observe su core $(core_version)..."
  local out
  out="$(cd "$HERMES_CORE" && "$HERMES_CORE/venv/bin/python" - <<'PYEOF' 2>&1
import sys
try:
    from hermes_cli.plugins import get_pre_tool_call_block_message
    try:
        from hermes_cli.plugins import _delivery_manager
        mgr = _delivery_manager()
    except Exception:
        from hermes_cli.plugins import get_plugin_manager
        mgr = get_plugin_manager()
except Exception as e:
    print("IMPORT_FAIL: %s" % e); sys.exit(4)

received = []
def sink(text):
    received.append(text)

def fake_hook(tool_name, args, task_id="", **kwargs):
    return {"action": "observe", "feedback": "SMOKE-observed-tool-considered"}

def fake_hook_dict(tool_name, args, task_id="", **kwargs):
    return {"action": "observe", "feedback": {"kind": "retrieval",
            "text": "SMOKE-dict-retrieval", "duration_ms": 3}}

try:
    hooks = getattr(mgr, "_hooks", {})
    lst = hooks.setdefault("pre_tool_call", [])
    if fake_hook not in lst:
        lst.append(fake_hook)
    if fake_hook_dict not in lst:
        lst.append(fake_hook_dict)
except Exception as e:
    print("REGISTER_FAIL: %s" % e); sys.exit(4)

try:
    msg = get_pre_tool_call_block_message(
        tool_name="terminal", args={"cmd": "echo smoke"},
        task_id="smoke-task", session_id="smoke-sess",
        feedback_sink=sink,
    )
except Exception as e:
    print("GATE_FAIL: %s" % e); sys.exit(4)

ok_str = "SMOKE-observed-tool-considered" in received
ok_dict = any(isinstance(r, dict) and r.get("text") == "SMOKE-dict-retrieval" for r in received)
if ok_str and ok_dict:
    print("SMOKE_OK: feedback_sink ricevuto (stringa + dict) -> %r" % (received,))
    sys.exit(0)
else:
    print("SMOKE_FAIL: sink non ricevuto (string=%s dict=%s, received=%r)"
          % (ok_str, ok_dict, received))
    sys.exit(4)
PYEOF
)"
  local rc=$?
  echo "$out"
  [ $rc -eq 0 ] && { echo "  -> canale observe FUNZIONANTE (hook -> feedback_sink)"; return 0; }
  echo "  -> canale observe NON funzionante (rc=$rc)" >&2
  return 4
}

# ── main ───────────────────────────────────────────────────────────────
[ -d "$HERMES_CORE" ] || die "core non trovato in $HERMES_CORE (set HERMES_CORE_DIR per override)"
[ -d "$PATCHES_DIR" ] || die "dir patches non trovata: $PATCHES_DIR"

MODE="${1:-apply}"
case "$MODE" in
  --list)   list_mapping; exit 0 ;;
  --smoke)  smoke_check; exit $? ;;
esac

# ── P0-3/P0-4 (review-3): risoluzione variante + base HARD gate condiviso
# da --check, --gate, apply E --status — un solo punto di compatibilità.
VERSION="$(core_version)"
VARIANT="$(variant_for_core "$VERSION")"
if [ -z "$VARIANT" ]; then
  # v0.3.0 FAIL-CLOSED: senza patch-manifest.json (o senza variante esatta
  # per questo core) NON si applica nulla. Niente più fallback legacy per
  # prefisso: un core non mappato è UNSUPPORTED, sempre.
  if [ ! -f "$PATCH_MANIFEST" ]; then
    die "FAIL-CLOSED: patch-manifest.json assente in $PATCHES_DIR — rifiuto di applicare qualsiasi patch senza manifest (migra il nodo allo schema observe-channel v0.3.0)"
  fi
  die "UNSUPPORTED: nessuna variante observe-channel per core ESATTO $VERSION nel manifest (varianti: $(python3 -c "import json; print(', '.join(sorted(json.load(open('$PATCH_MANIFEST')).get('variants', {}).keys())))" 2>/dev/null))"
fi
PATCH_FILE="$PATCHES_DIR/$(echo "$VARIANT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["file"])')"
BASE_COMMIT="$(echo "$VARIANT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["base_commit"])')"
DECLARED_SHA="$(echo "$VARIANT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
[ -f "$PATCH_FILE" ] || die "file patch mancante: $PATCH_FILE"

# base anchoring HARD su TUTTI i path (check, gate, apply, status):
# un core che non contiene/deriva dal base dichiarato è un FAIL, sempre.
verify_base_hard "$BASE_COMMIT" "$MODE"

case "$MODE" in
  --status)
    status_report
    exit $?
    ;;
esac

case "$MODE" in
  --check)
    # v0.3.0: verifica profonda prima di dichiarare lo stato.
    # 1) sha della patch vs manifest
    if [ -n "$DECLARED_SHA" ]; then
      ACTUAL_SHA="$(patch_sha256 "$PATCH_FILE")"
      [ "$ACTUAL_SHA" = "$DECLARED_SHA" ] || die "sha256 MISMATCH: patch $ACTUAL_SHA ≠ manifest $DECLARED_SHA (drift?)"
      echo "  sha256 OK: $(basename "$PATCH_FILE") = ${ACTUAL_SHA:0:12}..."
    fi
    # 2) core version ESATTA già garantita da variant_for_core (fail-closed)
    # 3) base anchoring HARD: eseguito PRIMA del dispatch (main condiviso) —
    #    qui resta solo il reverse/forward git apply check.
    # 4) reverse-check: OK = già applicata
    if (cd "$HERMES_CORE" && git apply --check -R "$PATCH_FILE" 2>/dev/null); then
      echo "OK: observe-channel $(patchset_version) già applicata su core $VERSION"
      exit 0
    fi
    if (cd "$HERMES_CORE" && git apply --check "$PATCH_FILE" 2>/dev/null); then
      echo "PRONTA: patch NON applicata ma applicabile su core $VERSION (BLOCCANTE nei gate: esegui apply)"
      exit 2
    fi
    echo "CONFLITTO: patch non applicata e non applicabile (core modificato/aggiornato?)" >&2
    echo "  -> rigenera la patch e aggiorna manifest+state" >&2
    exit 3
    ;;
  --gate)
    # usa il path assoluto dello script per il re-invoke (--check): se
    # eseguito come `bash script.sh` relativo, "$0" non è in PATH -> rc 127
    SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
    "$SELF" --check; rc=$?
    [ $rc -ne 0 ] && { echo "GATE FAIL: --check rc=$rc (BLOCCANTE)" >&2; exit $rc; }
    # P0-4 (v0.3.0) + P0-2 (review-4): --gate esegue il single-fire smoke
    # REALE (conteggio invocazioni + sanitize + block/observe ordering) col
    # venv del core selezionato, DOPO aver verificato l'integrità dello
    # smoke contro lo SHA dichiarato nel manifest (artifacts.single_fire_smoke)
    # — uno smoke alterato/finto non può più passare il gate.
    SMOKE_SCRIPT="$PATCHES_DIR/observe-channel-single-fire-smoke.py"
    if [ ! -f "$SMOKE_SCRIPT" ]; then
      echo "GATE FAIL: smoke reale assente: $SMOKE_SCRIPT (BLOCCANTE)" >&2
      exit 4
    fi
    SMOKE_DECLARED="$(python3 -c "
import json,sys
try:
    d=json.load(open('$PATCH_MANIFEST'))
    print(d.get('artifacts',{}).get('single_fire_smoke',{}).get('sha256',''))
except Exception:
    print('')
" 2>/dev/null)"
    if [ -z "$SMOKE_DECLARED" ]; then
      echo "GATE FAIL: artifacts.single_fire_smoke.sha256 mancante nel manifest (BLOCCANTE)" >&2
      exit 4
    fi
    SMOKE_ACTUAL="$(patch_sha256 "$SMOKE_SCRIPT")"
    if [ "$SMOKE_ACTUAL" != "$SMOKE_DECLARED" ]; then
      echo "GATE FAIL: smoke sha256 $SMOKE_ACTUAL ≠ manifest $SMOKE_DECLARED (smoke alterato?)" >&2
      exit 4
    fi
    echo "  smoke sha256 OK: $(basename "$SMOKE_SCRIPT") = ${SMOKE_ACTUAL:0:12}..."
    # P1-3 (review-5): l'evidence del gate include l'output COMPLETO dello
    # smoke (tutti i 7 casi: observe-only/dict, sanitize, ordering x2,
    # approve, sink-failure) — audit autosufficiente, non solo summary.
    SMOKE_LOG="/tmp/oc_smoke_gate_$(date +%Y%m%d_%H%M%S).log"
    if ! (cd "$HERMES_CORE" && "$HERMES_CORE/venv/bin/python" "$SMOKE_SCRIPT" 2>&1 | tee "$SMOKE_LOG" | grep -q "RESULT: PASS"); then
      echo "GATE FAIL: single-fire smoke REALE non PASS (vedi $SMOKE_LOG)" >&2
      exit 4
    fi
    echo "  smoke FULL output ($(grep -c '  PASS\|  FAIL' "$SMOKE_LOG") casi):"
    # appende l'output completo dello smoke allo stdout (quindi anche
    # all'evidence se l'utente redirige il --gate su file)
    sed 's/^/    /' "$SMOKE_LOG"
    echo "GATE PASS: patch applicata + single-fire smoke reale PASS (1 decision -> 1 invocation)"
    exit 0
    ;;
esac

# apply (default)
# verifica integrità SHA (necessaria anche per apply: state_set usa ACTUAL_SHA)
if [ -n "$DECLARED_SHA" ]; then
  ACTUAL_SHA="$(patch_sha256 "$PATCH_FILE")"
  [ "$ACTUAL_SHA" = "$DECLARED_SHA" ] || die "sha256 MISMATCH: patch $ACTUAL_SHA ≠ manifest $DECLARED_SHA (drift?)"
  echo "  sha256 OK: $(basename "$PATCH_FILE") = ${ACTUAL_SHA:0:12}..."
fi
# P1 fix (reviewer): BEFORE deve essere il commit PRIMA del git apply —
# git apply non crea commit, quindi HEAD~1 NON è il before (è il parent
# dell'HEAD invariato). Catturiamo core_commit PRIMA dell'apply.
CORE_BEFORE="$(core_commit)"
if (cd "$HERMES_CORE" && git apply --check -R "$PATCH_FILE" 2>/dev/null); then
  # già applicata: registra/ripara lo state se assente o incoerente
  if [ -n "$DECLARED_SHA" ] && [ "$(state_get state)" != "applied" ]; then
    AFTER="$(core_commit)"
    state_set "$(patchset_version)" "applied" "$VERSION" "$ACTUAL_SHA" "$CORE_BEFORE" "$AFTER"
    echo "stato registrato in $PATCH_STATE (patch già applicata)"
  fi
  echo "Già applicata: observe-channel $(patchset_version) su core $VERSION (niente da fare)"
  exit 0
fi
(cd "$HERMES_CORE" && git apply "$PATCH_FILE") || die "git apply fallito per $PATCH_FILE su core $VERSION"
AFTER="$(core_commit)"
if [ -n "$DECLARED_SHA" ]; then
  state_set "$(patchset_version)" "applied" "$VERSION" "$ACTUAL_SHA" "$CORE_BEFORE" "$AFTER"
  echo "stato registrato in $PATCH_STATE"
fi
echo "OK: patch observe-channel $(patchset_version) applicata su core $VERSION"
echo "Nota: riavvia il gateway da shell esterna (NON con job cron ripetuti), poi verifica con --smoke."
exit 0
