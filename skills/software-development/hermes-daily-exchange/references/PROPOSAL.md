# Hermes Daily Exchange — Proposta

## Cos'è
Ogni giorno, i peer della rete si scambiano conoscenza procedurale: skill create/modificate, bug fix, pattern scoperti, anti-pattern, "leaked strategies". peer70 fa da coordinatore.

## Formato
File in `~/.hermes/exchange/YYYY-MM-DD-peerID.md` con frontmatter YAML + corpo markdown, stile SKILL.md.

## Cosa si condivide (solo delta)
- Skill nuove/modificate (con checksum SHA-256)
- Bug fix in gateway/plugin/script
- Pattern di tool-use
- Anti-pattern scoperti
- Limitazioni osservate
- "Rimpianto della settimana"

## Flusso giornaliero (notte/03:00)
1. Ogni peer genera il proprio digest
2. Pubblica via SCP a peer70
3. peer70 consolida in daily/YYYY-MM-DD.md
4. peer70 copia nel vault Obsidian

## Flusso settimanale (domenica, pianificato)
1. Curator analizza i 7 digest
2. Pattern ricorrenti → candidate skill
3. Skill lottery + battle evaluation

## Trust-score
- 3+ peer confermano → promosso a knowledge base
- Skill con high confidence → skill versionate

Votazione: GO all'unanimità da peer105, 106, 84, 128 il 2026-07-17.
