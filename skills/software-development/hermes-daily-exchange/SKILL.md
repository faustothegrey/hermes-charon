---
name: hermes-daily-exchange
description: "Hermes Daily Exchange — sistema di scambio quotidiano di conoscenza tra peer della rete. Ogni notte peer70 raccoglie i digest da tutti i peer via SSH+SCP, consolida e copia nel vault Obsidian. v1.1.0"
type: custom
version: 1.1.0
---

# Hermes Daily Exchange

Sistema in cui tutti i peer della rete Hermes si scambiano ogni giorno conoscenza procedurale: skill create/modificate, bug fix, pattern scoperti, anti-pattern, limiti osservati. peer70 fa da coordinatore. L'obiettivo è l'auto-evoluzione collettiva.

Il progetto è stato approvato all'unanimità da tutti i peer (GO da peer105, 106, 84, 128 il 2026-07-17).

## Architettura finale

```
03:30  peer70 → daily-collect.sh (SSH in TUTTI i peer)
         ├── peer84  → ssh + daily-digest.sh → SCP file a peer70
         ├── peer105 → ssh + daily-digest.sh → SCP file a peer70
         ├── peer106 → ssh + daily-digest.sh → SCP file a peer70
         └── peer128 → ssh + daily-digest.sh → SCP file a peer70

03:35  peer70 → daily-consolidate.sh
         ├── Unisce TUTTI i peer in daily/YYYY-MM-DD.md
         └── Copia in Obsidian Vault Exchange/
```

## Perché peer70 fa tutto via SSH (non SCP dai peer)

- `root@peer105` **non può** SCP come `fausto@peer70` (chiavi SSH diverse)
- `root@peer106` idem
- La soluzione: **peer70** SSH in ogni peer → genera digest → SCP **da** peer a peer70
- Lo script `daily-publish.sh` sui peer è stato semplificato: SOLO genera digest (nessun SCP)

## Schedule e vincoli temporali

| Ora | Azione | Note |
|-----|--------|------|
| **03:00** | peer84 **si accende** (cooling finito) | Dà 30 minuti di margine |
| **03:30** | `daily-collect.sh` | Tutti i peer sono ON |
| **03:35** | `daily-consolidate.sh` | Prima del session reset |
| **04:00** | Hermes session reset (`at_hour: 4`) | Sessioni inattive da 24h vengono pulite |

### peer84 — cooling schedule

```
03:00 → 11:00  ON  (8h)
11:00 → 17:00  OFF (cooling — spento!)
17:00 → 02:00  ON  (9h)
02:00 → 03:00  OFF (1h cooling — spento!)
```

peer84 è SPENTO dalle 11:00 alle 17:00 e dalle 02:00 alle 03:00. L'exchange alle 03:30 dà 30 minuti di margine dopo l'accensione delle 03:00.

## Script su peer70 (source of truth)

### daily-collect.sh

```bash
bash ~/.hermes/scripts/daily-collect.sh [date]
```

SSH in ogni peer, esegue `daily-publish.sh` (che genera il digest), poi SCP il file risultante da peer a peer70. Mappa dei peer:

```bash
PEERS=(
  "peer84  fausto@192.168.178.84  /home/fausto"
  "peer105 root@192.168.178.105  /root"
  "peer106 root@192.168.178.106  /root"
  "peer128 fausto@192.168.178.112 /Users/fausto"
)
```

Nota: ogni entry contiene (`peer_id`, `ssh_user`, `remote_home`) — necessario perché `scp` e `ssh` usano percorsi assoluti diversi per ogni peer (fausto=/home, root=/root, macOS=/Users).

### daily-consolidate.sh

```bash
bash ~/.hermes/scripts/daily-consolidate.sh [date]
```

Unisce tutti i file `~/.hermes/exchange/<peer>/YYYY-MM-DD.md` in un unico
`~/.hermes/exchange/daily/YYYY-MM-DD.md`, poi lo COPIA automaticamente nel
vault Obsidian (`~/Documents/Obsidian Vault/Exchange/`).

### daily-digest.sh (sui peer remoto)

```bash
bash ~/.hermes/scripts/daily-digest.sh <peer_id> [--force]
```

Genera `~/.hermes/exchange/<peer_id>/YYYY-MM-DD.md` con:
- Sessioni recenti (ultime 24h da state.db)
- Skill modificate (SKILL.md più recenti di 24h)
- Versione plugin HMP

### daily-publish.sh (sui peer remoto, SEMPLIFICATO)

```bash
bash ~/.hermes/scripts/daily-publish.sh <peer_id>
```

SOLO genera il digest. **Non fa più SCP.** La copia a peer70 la fa
`daily-collect.sh` via SCP da peer70.

## Cron job attivi

| Job | Schedule | Cosa fa |
|-----|----------|---------|
| `daily-exchange-collect` | **30 3 * * *** | `bash ~/.hermes/scripts/daily-collect.sh` |
| `daily-exchange-consolidate` | **35 3 * * *** | `bash ~/.hermes/scripts/daily-consolidate.sh` |

## Directory

```
~/.hermes/exchange/
├── PROPOSAL.md              # Proposta originale approvata
├── daily/                   # Consolidati + round live
│   ├── YYYY-MM-DD.md        # Digest notturno (5 peer)
│   └── YYYY-MM-DD-exchange-round.md  # Round live manuale
├── peer70/ → peer70/
├── peer84/ → peer84/
├── peer105/ → peer105/
├── peer106/ → peer106/
└── peer128/ → peer128/

~/Documents/Obsidian Vault/
├── Index.md                 # Home page con wiki-link
├── Exchange/                # Sync automatico da daily-consolidate.sh
│   └── YYYY-MM-DD.md
└── Peers/
    ├── peer70.md
    ├── peer84.md
    ├── peer105.md
    ├── peer106.md
    └── peer128.md           # Ogni peer ha frontmatter + wikilink ai propri contributi
```

## Round live (manuale)

Per fare uno scambio in tempo reale (non aspettare il cron notturno):

```bash
# 1. Chiedi a tutti i peer (usa execute_code con importlib)
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('hmp', '/home/fausto/.hermes/scripts/hmp/hmp_tools.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

question = 'HERMES DAILY EXCHANGE - Condividi la scoperta/skill/bugfix/pattern PIU rilevante delle tue ultime sessioni. Inizia con [SKILL] [BUGFIX] [PATTERN] [ANTIPATTERN] [DISCOVERY]. Max 3 frasi.'

for pid in [105, 106, 84]:
    r = mod.hmp_send_and_wait(pid, question, f'round{pid}', max_polls=40, poll_interval=5)
    print(f'peer{pid}: {r}')
"

# 2. peer128 via curl (execute_code non arriva a .112)
# Vedi pattern: curl con MSGID noto + poll manuale

# 3. Salva il risultato in ~/.hermes/exchange/daily/YYYY-MM-DD-exchange-round.md
```

peer128 non è raggiungibile da `execute_code` (errore "No route to host" dal
sandbox Python). Usare `curl` diretto + poll per peer128.

## Peer voting per decisioni collettive

Per decisioni che coinvolgono tutti i peer (approvazione proposte, votazioni):

```python
# Ogni peer vota GO/NO GO
proposal = "PROPOSTA... Rispondi solo: GO o NO GO."
results = {}
for pid in [105, 106, 84]:
    r = mod.hmp_send_and_wait(pid, proposal, f'vote{pid}', max_polls=40, poll_interval=5)
    results[pid] = r.strip()
# peer128 via curl
```

Il primo round di votazione (2026-07-17) ha dato 4/4 GO.

## Pattern: Peer lenti

peer105 e peer84 impiegano 30-60s per rispondere anche a messaggi semplici.
peer106 risponde in 10-20s. peer128 risponde in 5-10s.

Per messaggi lunghi/complessi, peer105/106/84 possono impiegare 2-3 minuti.
Usare `max_polls=60` e `poll_interval=5` (5 minuti totali) per non timeoutare.

## Roadmap

| Step | Stato |
|------|-------|
| 1. Struttura directory | ✅ |
| 2. daily-digest.sh | ✅ |
| 3. daily-publish.sh | ✅ |
| 4. daily-collect.sh (da peer70) | ✅ |
| 5. daily-consolidate.sh + vault sync | ✅ |
| 6. Cron collect 03:30 | ✅ |
| 7. Cron consolidate 03:35 | ✅ |
| 8. NetBoard Pulse (mostra exchange live su :8191) | ✅ |
| 9. Weekly curator (pattern → skill) | 📅 |
| 10. Monthly librarian (knowledge base) | 📅 |

## NetBoard Integration

Il consolidato giornaliero è visibile su `http://192.168.178.70:8191` (NetBoard web UI) nella sezione **HMP Live Pulse** — mostra in tempo reale gli ultimi scambi HMP tra peer, includendo i messaggi del Daily Exchange.

Inoltre, un thread background in `netboard-web.py` polla il DB HMP ogni 3 secondi (`SELECT` su SQLite locale) e mantiene un buffer circolare degli ultimi 30 eventi. Zero impatto sul carico (DB di ~20 righe).

Il `daily-consolidate.sh` copia automaticamente il consolidato nel vault Obsidian (`~/Documents/Obsidian Vault/Exchange/`).
