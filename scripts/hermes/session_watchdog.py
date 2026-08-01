#!/usr/bin/env python3
"""Session size watchdog — avvisa su Telegram quando la sessione attiva
supera la soglia configurata (default 70% della context window).

Pattern watchdog: stdout vuoto = silenzio; stdout non vuoto = consegnato
verbatim al canale di consegna del cron job (no_agent=True).

Fonte dati: ~/.hermes/sessions/sessions.json → last_prompt_tokens
(aggiornata dal gateway a ogni turno = dimensione reale dell'ultimo prompt).
"""
import json
import os

SESSIONS_JSON = os.path.expanduser("~/.hermes/sessions/sessions.json")
THRESHOLD = 0.70
CONTEXT_LENGTH = 1_000_000  # deepseek-v4-flash (1M window); adattare se cambia modello

# Soglia di allerta: se il file non si aggiorna da N minuti, il valore letto
# potrebbe essere vecchio — ma il gateway salva a ogni turno, quindi ok.
STALE_MINUTES = 60


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def main() -> None:
    try:
        with open(SESSIONS_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Watchdog sessione: impossibile leggere {SESSIONS_JSON}: {exc}")
        return

    # Sessioni Telegram attive (DM + topic)
    candidates = {
        k: v for k, v in data.items()
        if k.startswith("agent:main:telegram:")
        and isinstance(v, dict)
        and v.get("session_id")
    }
    if not candidates:
        return  # nessuna sessione telegram attiva → silenzio

    # La più recente (la sessione con cui stai parlando ora)
    entry = max(candidates.values(), key=lambda v: v.get("updated_at", ""))
    sid = entry.get("session_id", "?")
    tokens = int(entry.get("last_prompt_tokens") or 0)
    pct = (tokens / CONTEXT_LENGTH) * 100

    if pct >= THRESHOLD * 100:
        print(
            f"⚠️ Sessione Telegram vicina al limite\n"
            f"• Contesto: {_fmt_tokens(tokens)} / {_fmt_tokens(CONTEXT_LENGTH)} token "
            f"({pct:.0f}%)\n"
            f"• Soglia warning: {THRESHOLD:.0%} — compressione automatica: 50%\n"
            f"• Consiglio: /compress ora, oppure /new per ripartire pulito\n"
            f"• Sessione: {sid}"
        )
    # sotto soglia → nessun output (silenzio)


if __name__ == "__main__":
    main()
