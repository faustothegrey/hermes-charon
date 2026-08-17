#!/usr/bin/env python3
"""
HMP Brainstorm / Gang Idea Machine

Un giro strutturato di brainstorming tra i peer della rete HMP.
Max 3 round. Ogni round: domanda → risposte → sintesi → votazione.
Alla fine: consenso o no.

Usage da execute_code():
  exec(open('/home/fausto/.hermes/scripts/hmp-brainstorm.py').read())
  result = brainstorm("Tema: ...", "Domanda: ...", max_rounds=3)
"""
import importlib.util, sys, json, time
from typing import Dict, List, Optional

# ── HMP tools ──────────────────────────────────────────────────────────
spec = importlib.util.spec_from_file_location(
    "hmp", "/home/fausto/.hermes/scripts/hmp/hmp_tools.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

hmp_send_and_wait = mod.hmp_send_and_wait

# ── Peer attivi ────────────────────────────────────────────────────────
PEERS = [84, 106, 128]
PEER_NAMES = {84: "peer84 (Ubuntu)", 106: "peer106 (Fedora)", 128: "peer128 (macOS)"}

def brainstorm(theme: str, question: str, max_rounds: int = 3) -> Dict:
    """
    Esegue un brainstorming tra i peer HMP.

    Args:
        theme: Il tema del brainstorming
        question: La domanda specifica
        max_rounds: Max round (default 3)

    Returns:
        dict con risultato, risposte per round, consenso finale
    """
    print(f"\n{'='*60}")
    print(f"🧠 HMP BRAINSTORM")
    print(f"{'='*60}")
    print(f"Tema: {theme}")
    print(f"Domanda: {question}")
    print(f"Peer: {', '.join(PEER_NAMES.values())}")
    print(f"Max round: {max_rounds}\n")

    all_rounds = []
    current_question = question

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─'*60}")
        print(f"Round {round_num}/{max_rounds}")
        print(f"{'─'*60}")

        # 1. Chiedi a tutti i peer
        responses = {}
        for pid in PEERS:
            print(f"\n  {PEER_NAMES[pid]}...", end=" ", flush=True)
            msg = (
                f"BRAINSTORM - Round {round_num}/{max_rounds}\n"
                f"Tema: {theme}\n"
                f"Domanda: {current_question}\n\n"
                f"Rispondi in massimo 3-4 frasi, concreto e ACTIONABLE. "
                f"Proposte pratiche, non teoria."
            )
            try:
                resp = hmp_send_and_wait(pid, msg, f"br{round_num}_{pid}",
                                          max_polls=40, poll_interval=5)
                responses[pid] = resp.strip()
                print("✅")
            except Exception as e:
                responses[pid] = None
                print(f"❌ {e}")

        all_rounds.append(responses)

        # 2. Stampa risposte
        print(f"\n\n  ── Risposte Round {round_num} ──")
        for pid in PEERS:
            r = responses.get(pid)
            if r:
                print(f"\n  {PEER_NAMES[pid]}:")
                for line in r.split("\n"):
                    print(f"    {line}")
            else:
                print(f"\n  {PEER_NAMES[pid]}: (nessuna risposta)")

        # 3. Se ultimo round, passa direttamente al consenso
        if round_num == max_rounds:
            break

        # 4. Sintesi (sempre la stessa per ora — peer70 la fa)
        synthesis = _synthesize(responses, theme, current_question)

        print(f"\n\n  ── Sintesi Round {round_num} ──")
        print(f"  {synthesis}")

        # 5. Votazione sulla sintesi
        print(f"\n\n  ── Votazione Round {round_num} ──")
        votes = {}
        for pid in PEERS:
            print(f"  {PEER_NAMES[pid]}...", end=" ", flush=True)
            vote_msg = (
                f"VOTAZIONE - Round {round_num}/{max_rounds}\n"
                f"Sintesi delle idee emerse:\n{synthesis}\n\n"
                f"Sei d'accordo con questa direzione? Rispondi solo: SI o NO. "
                f"Se NO, cosa cambieresti in 1 frase."
            )
            try:
                resp = hmp_send_and_wait(pid, vote_msg, f"vote{round_num}_{pid}",
                                          max_polls=30, poll_interval=5)
                votes[pid] = resp.strip() if resp else ""
                print(f"→ {votes[pid][:60]}")
            except Exception as e:
                votes[pid] = f"ERR: {e}"
                print(f"❌ {e}")

        # 6. Analisi voti
        yes_votes = sum(1 for v in votes.values() if v.upper().startswith("SI"))
        no_votes = sum(1 for v in votes.values() if v.upper().startswith("NO"))
        total = len([v for v in votes.values() if v and not v.startswith("ERR")])

        print(f"\n\n  Risultato: {yes_votes}/{total} SI, {no_votes}/{total} NO")

        if total > 0 and yes_votes / total >= 0.5:
            print(f"  ✅ Consenso raggiunto al Round {round_num}!")
            return _final_report(theme, question, responses, votes, round_num, consensus=True)

        # Se NO, prepara nuova domanda con le obiezioni
        no_reasons = [v for pid, v in votes.items()
                      if v.upper().startswith("NO")]
        if no_reasons:
            current_question = (
                f"{question}\n\n"
                f"Obiezioni dal round precedente:\n"
                f"{' '.join(no_reasons[:3])}\n\n"
                f"Proponi una soluzione che tenga conto di questi punti."
            )

    # Dopo max_rounds, vediamo se c'è consenso finale
    print(f"\n\n  ── Votazione Finale ──")
    final_votes = {}
    for pid in PEERS:
        print(f"  {PEER_NAMES[pid]}...", end=" ", flush=True)
        final_msg = (
            f"VOTAZIONE FINALE\n"
            f"Tema: {theme}\n"
            f"Dopo {max_rounds} round di brainstorming, le risposte sono state raccolte.\n\n"
            f"CONSENSO FINALE: approvi la direzione emersa?\n"
            f"Rispondi solo: SI o NO."
        )
        try:
            resp = hmp_send_and_wait(pid, final_msg, f"final_{pid}",
                                      max_polls=30, poll_interval=5)
            final_votes[pid] = resp.strip() if resp else ""
            print(f"→ {final_votes[pid][:60]}")
        except Exception as e:
            final_votes[pid] = f"ERR: {e}"
            print(f"❌ {e}")

    yes_votes = sum(1 for v in final_votes.values() if v.upper().startswith("SI"))
    total = len([v for v in final_votes.values() if v and not v.startswith("ERR")])
    consensus = total > 0 and yes_votes / total >= 0.5

    return _final_report(theme, question, all_rounds[-1], final_votes, max_rounds, consensus)


def _synthesize(responses: Dict, theme: str, question: str) -> str:
    """Crea una sintesi delle risposte."""
    lines = [f"Sintesi brainstorming: {theme}"]
    for pid, resp in responses.items():
        if resp:
            # Prendi la prima frase significativa
            first = resp.split("\n")[0][:120]
            lines.append(f"- {PEER_NAMES[pid]}: {first}")
    return "\n".join(lines)


def _final_report(theme, question, responses, votes, rounds, consensus):
    """Report finale."""
    print(f"\n{'='*60}")
    print(f"📋 REPORT FINALE HMP BRAINSTORM")
    print(f"{'='*60}")
    print(f"Tema: {theme}")
    print(f"Domanda: {question}")
    print(f"Round: {rounds}")
    print(f"Consenso: {'✅ SI' if consensus else '❌ NO'}")
    print(f"\nVoti:")
    for pid, v in votes.items():
        name = PEER_NAMES[pid]
        print(f"  {name}: {v[:80]}")
    print(f"\nRisposte:")
    for pid, r in responses.items():
        if r:
            print(f"\n  {PEER_NAMES[pid]}:")
            for line in r.split("\n")[:4]:
                print(f"    {line}")

    return {
        "theme": theme,
        "question": question,
        "rounds": rounds,
        "consensus": consensus,
        "votes": votes,
        "responses": responses,
    }


if __name__ == "__main__":
    # Esempio
    result = brainstorm(
        "Miglioramento della rete HMP",
        "Quale singola feature o miglioramento vorresti vedere sul plugin HMP?",
        max_rounds=2
    )
