---
name: daily-exchange
description: "Daily Exchange — sistema di condivisione conoscenza tra peer Hermes. Ogni notte i peer generano un digest delle loro scoperte, peer70 consolida, e il risultato finisce nel vault Obsidian."
type: custom
version: 1.1.0
---

# Daily Exchange

Sistema di scambio conoscenza giornaliero tra i peer della rete Hermes. Ogni notte i peer generano un digest delle loro sessioni, peer70 li raccoglie, consolida, e copia il risultato nel vault Obsidian.

## Architettura

```
03:30  daily-collect.sh  ──→ SSH in ogni peer → daily-digest.sh → genera file
                         ──→ SCP da peer a peer70 → exchange/<peer>/YYYY-MM-DD.md

03:35  daily-consolidate.sh ──→ Unisce tutti i digest → exchange/daily/YYYY-MM-DD.md
                            ──→ Copia in vault Obsidian (se presente)
```

## Flusso

| Ora | Script | Cosa fa |
|-----|--------|---------|
| 03:30 | `daily-collect.sh` | Su peer70: SSH in ogni peer, genera digest, SCP a peer70 |
| 03:35 | `daily-consolidate.sh` | Su peer70: unisce tutti, copia in vault Obsidian |

## Script

| Script | Path | Cosa fa |
|--------|------|---------|
| `daily-digest.sh` | `~/.hermes/scripts/` | Genera digest locale (sessioni, skill, plugin version) |
| `daily-publish.sh` | `~/.hermes/scripts/` | Wrapper: genera digest (usato dal collect, no SCP) |
| `daily-collect.sh` | `~/.hermes/scripts/` | Su peer70: SSH in tutti i peer, genera + SCP |
| `daily-consolidate.sh` | `~/.hermes/scripts/` | Su peer70: unisce tutti i digest, copia in vault |

## peer84 — cooling schedule

peer84 è SPENTO in queste fasce orarie:
- **11:00 → 17:00** (6h pomeriggio)
- **02:00 → 03:00** (1h notte)

Accensione alle **03:00**. Il collect parte alle **03:30** — 30 minuti di margine per far partire il gateway.

## Peer partecipanti

| Peer | SSH User | Remote home |
|------|----------|-------------|
| peer84 | fausto@192.168.178.84 | /home/fausto |
| peer105 | root@192.168.178.105 | /root |
| peer106 | root@192.168.178.106 | /root |
| peer128 | fausto@192.168.178.112 | /Users/fausto |

## ⚠️ Cron Job Tirith Security Blocker

I cron job `daily-exchange-collect` e `daily-exchange-consolidate` DEVONO essere configurati come `no_agent: true` in `~/.hermes/cron/jobs.json`. Senza questa impostazione, il Tirith security scanner blocca TUTTI i comandi terminal nelle sessioni cron con `tirith:unknown` — anche `pwd && echo test`.

**Impostazione corretta in jobs.json:**

```json
{
  "id": "34c92c320db0",
  "name": "daily-exchange-collect",
  "script": "daily-collect.sh",
  "no_agent": true,
  ...
}
```

**Cosa significa `no_agent: true`:**
- Lo script viene eseguito direttamente via subprocess dal cron scheduler
- Nessun agente LLM, nessun controllo di sicurezza — bypassa completamente Tirith
- L'output dello script viene consegnato direttamente
- Lo stesso pattern usato da `peer70-watchdog`, `Load Monitor`, heartbeat scripts

**Perché non possiamo usare `no_agent: false`:**
Il gateway Hermes imposta `HERMES_EXEC_ASK=1` a startup (`gateway/run.py:1638`). Questo env var viene ereditato dal cron scheduler. In `approval.py:1613`, la presenza di `HERMES_EXEC_ASK` fa sì che il codice bypassi il percorso cron-mode e cada nel percorso Tirith + gateway-approval — che non può funzionare in cron senza utente.

**Il file `cron_config_override.yaml` non funziona:** Contiene le impostazioni corrette (`approvals.cron_mode: allow`, `security.tirith_enabled: false`) ma non viene mai caricato da `load_config()`. Ogni tentativo di usarlo come workaround è fallito (documentato in sessioni del 14-17 Luglio 2026).

**Riferimento:** Vedi `sysadmin/cron-operations` skill per la documentazione completa del Tirith blocker e delle workaround.

## Cron job (configurazione attuale)

| Nome | Job ID | Schedule | Tipo | Script |
|------|--------|----------|------|--------|
| `daily-exchange-collect` | `34c92c320db0` | `30 3 * * *` | `no_agent: true` | `daily-collect.sh` |
| `daily-exchange-consolidate` | `cebd0d8bd258` | `35 3 * * *` | `no_agent: true` | `daily-consolidate.sh` |

## Vault Obsidian

Path: `~/Documents/Obsidian Vault/`

Dopo il consolidate, il file viene copiato in `Exchange/YYYY-MM-DD.md`.

**Nota su peer70:** Il vault Obsidian non è presente su peer70 (directory non trovata). La copia automatica termina silenziosamente senza errore, ma non produce output. Per avere il consolidato nel vault, o il vault deve essere montato su peer70, o il consolidate deve essere eseguito dal peer che ha il vault.

## Peer health al momento della raccolta (2026-07-18)

| Peer | Stato | Note |
|------|-------|------|
| peer70 | ✅ Online | Digest generato localmente |
| peer105 | ✅ Online (HMP :18643) | Raggiungibile via HMP, ma SSH/SCP richiede terminal |
| peer106 | ✅ Online (HMP :18643) | Raggiungibile via HMP, ma SSH/SCP richiede terminal |
| peer84 | ❌ Unreachable (cooling window) | 11:00-17:00 + 02:00-03:00 |
| peer128 | ❌ Offline | Non raggiungibile dal 6 luglio 2026 |

## HMP Brainstorm

Script in `~/.hermes/scripts/hmp-brainstorm.py` — giro strutturato di brainstorming tra i peer via HMP.

```python
# Uso da execute_code()
exec(open('/home/fausto/.hermes/scripts/hmp-brainstorm.py').read())
result = brainstorm("Tema", "Domanda?", max_rounds=3)
```

Meccanismo:
1. Invia domanda a tutti i peer
2. Raccoglie risposte
3. Sintesi + votazione GO/NO GO
4. Max 3 round
5. Report finale con consenso o no

## Formato digest

```markdown
---
peer: peer106
date: 2026-07-17
plugin_version: 0.1.2
type: daily
---

## Sessioni di oggi

  - 18:11 | peer-feedback-round
  - 07:02 | Clean HMP Plugin Test

## Plugin HMP

Versione plugin: 0.1.2. Nessuna skill modificata.
```

## Pitfall: SSH + SCP da root a fausto

Quando `daily-collect.sh` su peer70 SSH in peer105/106 come root e poi SCP il file, il target su peer70 è `fausto@192.168.178.70:...`. La chiave pubblica di root su peer105/106 deve essere in `~fausto/.ssh/authorized_keys` su peer70.

**Soluzione:** lo SCP parte da peer70 verso il peer (pull), non dal peer verso peer70 (push) — così la chiave è quella di fausto@peer70 che ha accesso ovunque.

## Pitfall: Plugin HMP version drift

Il plugin HMP (0.1.2 → 0.1.3) può avere versioni diverse su peer diversi. Il digest registra la versione locale di ogni peer. Se un peer è rimasto a 0.1.2 mentre peer70 è a 0.1.3, non è un errore — il plugin è retrocompatibile. È utile però per tracciare quali peer hanno ricevuto l'aggiornamento.