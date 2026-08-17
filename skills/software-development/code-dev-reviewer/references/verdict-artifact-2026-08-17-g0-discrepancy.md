# Verdict artifact — G0/G2b discrepancy gate (2026-08-17)

Reconstruction of the reviewer verdict for the G0 "CLOSED" dispute raised by peer128/peer141.

## Primary artifact: the email (mailbox-resident, NOT on disk)

- Mailbox: Libero INBOX, account `libero` (`fausto.lelli72@libero.it`), **email ID 6**
- From: `fausto.lelli@hotmail.com` (display "Pippo Baudo") · 2026-08-17 12:44
- Subject: `RE: [DEV] G0 FINAL v7 — G2b CLOSED su entrambi i core (remediation review completa), pre-holdout`
- Fetch: `himalaya envelope list -a libero --page-size 40 --output json` then `himalaya message read -a libero 6`
- The verdict was ALREADY marked seen — only listing all envelopes (not `not flag seen`) finds it.

### Verbatim closure lines (email ID 6)

> "Ricevuto. Ho letto anche il bundle allegato: report e manifest indicano **G0 e G2b CLOSED, con remediation completata su entrambi i core** e test/evidence coerenti. Il pacchetto risulta quindi pronto per il sealed Phase 1a organic holdout, subordinatamente alla decisione GO del reviewer."

Note: the email cites NO adapter SHA — it defers to "report e manifest". SHAs live in the bundle report, not the email.

## SHAs (reviewed bundle vs live tree)

| Artifact | SHA-256 | Where |
|---|---|---|
| `adapter.py` v0.1.4-g0-g2b (REVIEWED, bundle frozen 2026-08-17 00:29) | `b9525a0b61deec9715c8831760e31f963c842a6f49dd2e12af165770f88a0bf0` | `~/.hermes/g0-bundle/report-g0.md` §4 + `~/.hermes/g0-bundle/adapter.py` |
| `adapter.py` LIVE on peer70 (modified 2026-08-17 **15:37, post-verdict**) | `6fc19e0ff8c8013698bcd74a23c3b04609601356abe7913442cacf2b26d4dd3d` | `~/.hermes/plugins/hmp/adapter.py` (also peer128-bundle copy) |
| SHA cited by peer141 handoff | `71c66088…` | **0 matches on peer70 filesystem** → belongs to peer141's node tree |

Live drift = event_store import-resolution fix ("G2b/G0 review blocker fix, 2026-08-17", 81 diff lines): canonical `$HERMES_HOME/plugins/capability-reuse` path first, legacy skills-copy fallback only if it exposes the full `emit_*` surface. Substantive, not cosmetic.

## Scope answer (peer128's question)

- "G0 CLOSED" per verdict = **phase0_p141_p70 cohort only** (peer70 Charon 0.17.0 + peer141 0.20.1, "entrambi i core").
- Does NOT close the canonical **peer58+peer106** milestone: no evidence artifact on peer70 shows that slice ran (peer58 last_seen 2026-08-13; peer106 offline, upgrade pending).
- Baseline holds untouched: formal Phase 0 NOT YET (sealed Phase 1a holdout pending GO), Phase 1B/Decision Trace NO-GO, Observe Channel = separate train, broad active rollout NO-GO.

## Related canonical records (peer70 side)

- `~/.hermes/g0-bundle/report-g0.md` (v7) — component SHA table, §5 status
- `~/.hermes/g0-bundle/peer128-bundle/README-capreuse-v260.md` — cap-reuse 2.6.0 canonical artifact doc (impl-capreuse hash method: cumulative sha256 of name+bytes of 11 top-level .py, sorted; plugin.yaml excluded)
- Vault `Progetti/Hermes/session-facts-2026-08-17-g0-g2b-review-loop.md` — paraphrase only; quotes come from the email
- `REBAR_REVIEW_STATE.md` (2026-08-15, Fausto-supplied) — **not present on peer70 filesystem**; exists on peer128/Fausto side
