# Piano: Clone completo dell'agente (peer70/Charon) per upgrade OS

Data: 2026-08-23
Autore: ALICE (Hermes peer70)
Stato: REV 2 — peer review completata (5/5 peer, 2026-08-23), correzioni integrate

## 0. Esito peer review (HMP, 5/5 online, tutte risposte)

| Peer | Verdetto | Correzioni richieste |
|---|---|---|
| peer58 | struttura A-D corretta | state.db via sqlite3 .backup; id_rsa copia off-box + test decrypt; export systemd/cron JSON; iptables-save; git bundle verify |
| peer128 (Mac) | solido; 3 fix critiche | untracked (.install_method); sqlite3 .backup (WAL=corruzione); **id_rsa in chiaro off-box** (single point of failure #1); linger; pull-model rsync |
| peer136 | solido; 3 gap | **node_modules 1.1G da escludere**; .install_method untracked; git apply --check; iptables PRIMA di esporre; fstab creds separate |
| peer138 | A-/B+ | dry-run restore OBBLIGATORIO; venv non portabile (ricrea); manifest pinned; **registry/ da preservare**; repo privato |
| peer141 | APPROVE + 3 corr. | git diff incompleto (untracked+staged); stime ~2.7G/2.1G; SSH peer128 da verificare; patches-core/ nel Layer A; 2ª copia id_rsa |

**Convergenza maggioritaria sulle 5 decisioni:**
1. state.db → INCLUDE (via `sqlite3 .backup`, MAI tar a caldo) [58,128,136,138] / 141: escludi ma snapshot separato
2. peer128 off-box → CONFERMATO (111 GiB liberi, Mac, modello pull) [tutti]
3. Immagine SD → SÌ, gateway fermo, streamata via SSH verso peer128 [58,128,136,141] / 138: ultima rete, non sostituisce dry-run
4. OS target → **Debian 12 bookworm** [58,128,136,141] / peer138: trixie (già provato su 138)
5. Eseguire Fase 0-2 subito → SÌ, read-only [TUTTI, unanime]

## 1. Obiettivo

Clonare in modo COMPLETO l'agente Hermes su peer70 (Charon, RPi arm64)
così da poter aggiornare il sistema operativo (Debian 11 bullseye) senza
perdere nulla, e ripristinare l'agente identico sul nuovo OS.

## 2. Inventario reale del box (rilevato, non stimato)

### 2.1 ~/.hermes (HOME agente) = 3.0 GB
| Path | Dim | Contenuto | In backup nightly? |
|---|---|---|---|
| hermes-agent/ | 1.9G | Sorgente Hermes v0.17.0 + **12 commit locali + 5 file modificati** (patch capability-reuse observe-channel) | NO ⚠️ |
| state.db | 644M | Store sessioni (SQLite+FTS) — runtime state | NO (by design) |
| node/ | 201M | Runtime Node (nvm-style) | NO |
| bin/ | 72M | Binary vari | NO |
| lsp/ | 35M | Language servers | NO |
| skills/ | 35M | 97 skill, 5 pinnate | SÌ |
| logs/ | 26M | Log gateway/cron | NO |
| data/ | 20M | Dati capreuse/HMP | NO |
| tests/ | 17M | Test suite | NO |
| cron/ | 5.2M | Definizioni job cron | SÌ |
| scripts/ | 1.3M | Script utente (fritzbox, netboard, capreuse...) | SÌ |
| plugins/ | 924K | capability-reuse, harness-feedback, hmp | SÌ |
| registry/ | 180K | Skill registry locale | SÌ |
| exchange/, peer-network/, netboard/ | ~450K | Stato HMP/mesh | NO |

### 2.2 Segreti (presenti, già gestiti)
- ~/.hermes/.env (23K) e ~/.hermes/auth.json (9.4K)
- Backup nightly → GitHub faustothegrey/hermes-charon.git, cifratura envelope (chiave = ~/.ssh/id_rsa), bundle sano ~10KB, nightly OK (ultimo 22/08 23:00)

### 2.3 Configurazione di sistema (NON nel backup GitHub)
- systemd user: hermes-gateway.service (ENABLED) + hermes-gateway-restart.service
- systemd system: netboard.service, netboard-web.service (ENABLED)
- crontab utente: 4 job capreuse (batch-reuse-analyzer, central-collector, dashboard, hmp-healthcheck)
- ~27 job cron Hermes (backup nightly, watchdogs, HMP, exchange, capreuse)
- iptables: policy INPUT DROP + ACCEPT LAN 192.168.178.0/24 (persistito via netfilter-persistent)
- fstab: mount CIFS NAS (aggiunto oggi)
- sudoers: fausto-nopasswd
- SSH keys: ~/.ssh/id_rsa + authorized_keys (CRITICHE: GitHub, peer, envelope)

### 2.4 Dati utente fuori ~/.hermes
- ~/scripts-ai (4.0M, da NAS oggi)
- ~/Documents/Obsidian Vault (404K)
- ~/Backups/hermes-config (repo git backup)

### 2.5 Target di storage disponibili
| Target | Spazio | Uso |
|---|---|---|
| Disco locale | 42G free | Staging temporaneo |
| NAS FRITZ.NAS | 362M free | TROPPO PICCOLO per clone completo |
| peer128 (.112, SSH open) | verificare | Backup off-box ⭐ |

## 3. Cosa manca al backup nightly (gap da colmare)

Il backup nightly copre config/skills/plugins/cron/memories/secrets MA NON:
1. **Sorgente Hermes con patch locali** (1.9G, 12 commit + 5 file dirty) — il pezzo critico
2. state.db sessioni (regenerabile, decisione)
3. systemd unit (gateway + netboard)
4. crontab + job cron Hermes (i cron sono in cron/, ma serve export pulito)
5. SSH keys, iptables, fstab, sudoers
6. runtime data (data/, exchange/, peer-network/, netboard/, logs/)
7. scripts-ai + vault

## 4. Strategia di clone (a strati)

### Layer A — Artefatto agente completo (il deliverable principale)
```
tar.gz di ~/.hermes completo + file di sistema, escluso il ridondante:
  INCLUDE: tutto tranne quanto sotto + ~/.hermes/patches-core/ (source-of-truth patch)
           + registry/ (registry.json + peers/*.json) + RESTORE-MANIFEST.json
  ESCLUDE: node/, bin/, lsp/ (reinstallabili), hermes-agent/node_modules (1.1G!),
           __pycache__, *.pyc, state.db VIVO (vedi sotto)
  state.db: copia con `sqlite3 ~/.hermes/state.db ".backup <tmp>/state.db.bak"` poi
            comprimila nel tar. MAI tar/cp del .db a caldo (WAL = corruzione).
```
Stima corretta (peer141): ~2.7 GB con state.db, ~2.1 GB senza; gzip → ~1.5-2.2 GB.
`node_modules` escluso → documentare reinstall in Fase 4 (`npm ci` da package.json).
Manifest pinned: versioni esatte node/lsp/dipendenze per la reinstall.

### Layer B — Patch del sorgente Hermes (replicabilità)
Oltre al tar, esportare il delta del sorgente come git bundle:
```
cd ~/.hermes/hermes-agent
git bundle create ~/Backups/hermes-source.bundle --all
git diff HEAD > ~/Backups/hermes-source-dirty.patch   # 5 file modificati
git status --porcelain > ~/Backups/hermes-dirty-list.txt  # cattura untracked (.install_method)
```
⚠️ `git diff` da solo NON cattura untracked né staged: usare `git diff HEAD`
+ lista `git status --porcelain` (o `git stash -u` come snapshot completo).
Verifica in Fase 2: `git bundle verify` + `git apply --check` su checkout
stock v0.17.0 pulito — "il patch esiste" ≠ "il patch si applica".

### Layer C — Backup nightly GitHub (già attivo, va verificato prima)
- Confermare che l'ultimo nightly sia `ok` e il bundle secrets sano (<100MB)
- ⚠️ Repo `faustothegrey/hermes-charon` deve essere PRIVATO (contiene secrets)
- ⚠️ Single point of failure: l'envelope si decifra con ~/.ssh/id_rsa → copia
  in chiaro di id_rsa off-box (peer128, permessi 600) OPPURE nel Layer D

### Layer D — Safety net opzionale: immagine disco completa
```
# a gateway/servizi FERMI (dd a caldo di root montato non è crash-consistent)
sudo systemctl --user stop hermes-gateway  (e servizi netboard)
sudo dd if=/dev/mmcblk0 bs=4M | gzip | ssh peer128 'cat > charon-full-<data>.img.gz'
```
(59.6G scheda, ~15G usati → immagine compressa ~8-12G; streamare via SSH
per non riempire i 42G locali. peer128 ha 111 GiB liberi.)

## 5. Sequenza di esecuzione

### Fase 0 — Pre-flight (15 min)
- [ ] Verifica nightly backup: `cronjob action=list` → state scheduled, last ok
- [ ] Verifica bundle secrets: `ls -la ~/Backups/hermes-config/secrets/*.enc` → KB
- [ ] Verifica SSH a peer128: `ssh fausto@192.168.178.112` (host key + spazio `df -h`)
- [ ] `hermes doctor` → tutto verde
- [ ] Stop gateway? NO per Layer A config/data (leggiamo file); SÌ per state.db
      (o usare sqlite3 .backup a caldo, che è sicuro in WAL) e per Layer D

### Fase 1 — Crea artefatti (20-30 min)
- [ ] `sqlite3 ~/.hermes/state.db ".backup /tmp/state.db.bak"` (MAI cp a caldo)
- [ ] Crea tar.gz Layer A in ~/Backups/charon-clone-<data>.tar.gz
      (escluso node_modules; incluso .install_method, patches-core/, registry/)
- [ ] Crea git bundle + `git diff HEAD` patch + dirty-list Layer B
- [ ] Snapshot config di sistema (unit systemd, crontab, iptables-save, fstab,
      sudoers, hostname, `systemctl --user is-enabled`, `hermes cron list --all`)
      in ~/Backups/system-snapshot-<data>/
- [ ] Snapshot SSH keys: id_rsa + id_rsa.pub + authorized_keys + ~/.ssh/config
      in bundle separato; **copia in chiaro id_rsa verso peer128 (600)**
- [ ] rsync tutto su peer128:~/.backups/charon-<data>/ (modello PULL dal Mac,
      verifica checksum) — oppure staging locale 42G + rsync dopo

### Fase 2 — Verifica del clone (CRITICA, prima di toccare l'OS)
- [ ] Test di restore su directory scratch: estrai tar in /tmp/restore-test
- [ ] Confronta checksum campioni sorgente vs tar
- [ ] `git bundle verify` + clone del bundle in scratch + `git apply --check`
      del dirty patch su checkout stock v0.17.0 pulito
- [ ] Test decrypt secrets: `restore-hermes.sh` su scratch (NON sul vivo)
- [ ] Documenta il report di verifica (questo è il rehearsal — valida l'integrità
      dell'archivio, NON è una prova di boot su OS pulito)

### Fase 3 — Upgrade OS (azione di Fausto o con supporto)
- [ ] Backup completo della scheda (Layer D, gateway e servizi FERMI, off-box)
- [ ] Installazione nuovo OS (raccomandato: Debian 12 bookworm arm64)
- [ ] Reinstall base: Python 3.11, git, openssl, tmux, rsync, netfilter-persistent, CIFS utils
- [ ] Ripristino ~/.ssh (chiavi), fstab (credenziali CIFS in file separato),
      iptables (PRIMA di esporre servizi, con rollback-timer `at now+5min` per
      evitare lockout da policy DROP), sudoers, hostname=Charon
- [ ] `loginctl enable-linger fausto` (gateway user-unit senza login attivo)

### Fase 4 — Restore agente
- [ ] Installa Hermes base: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` (o git clone v0.17.0)
- [ ] Ricrea venv: la venv binaria NON è portabile Debian 11→12 (Python 3.9→3.11);
      ricostruire da requirements/pyproject con la Python del nuovo sistema + test smoke
- [ ] Applica Layer B (git bundle + `git diff HEAD` patch + untracked) se riparti da stock
- [ ] Oppure estrai ~/.hermes dal Layer A (completo)
- [ ] Ripristina ~/.hermes/.env + auth.json (dall'envelope o dal tar)
- [ ] Ripristina systemd user unit + abilita gateway + linger
- [ ] Ripristina crontab + job cron Hermes (da cron/ + `hermes cron list` JSON)
- [ ] Ripristina netboard (system service + dir)
- [ ] Ripristina plugins (hmp/capreuse/harness-feedback) e registry/ — ordine: gateway → plugin → cron → test
- [ ] Ripristina scripts-ai e vault
- [ ] `hermes doctor` + `hermes gateway start`

### Fase 5 — Verifica post-restore
- [ ] `hermes --version` → 0.17.0 + 12 commit locali presenti
- [ ] `git status` in hermes-agent → 5 file dirty + 1 untracked (.install_method) identici
- [ ] `git status --porcelain` → pulito sugli untracked (niente residui)
- [ ] Gateway UP: `curl http://127.0.0.1:8642/health` (o porta reale)
- [ ] HMP bidirezionale con peer (health peer70 + ping a peer141)
- [ ] Patchset observe riapplicato (capability-reuse) — verifica comportamento, non solo git status
- [ ] `hermes cron list` → tutti i job presenti
- [ ] Skill: 97 presenti, 5 pinnate
- [ ] Memoria: entries identiche
- [ ] SMB/NAS: mount CIFS funzionante
- [ ] iptables: policy DROP + LAN ACCEPT
- [ ] Plugins hmp/capreuse/harness-feedback caricati

## 6. Decisioni richieste a Fausto (prima di eseguire) — con raccomandazione peer review

1. **state.db (644M)**: includere la cronologia sessioni? → raccomandato SÌ via
   `sqlite3 .backup` (58/128/136/138); peer141: escludi dal main ma snapshot separato
2. **Target off-box**: peer128 CONFERMATO (111 GiB liberi, Mac, modello pull rsync) [unanime]
3. **Immagine disco (Layer D)**: SÌ, gateway fermo, streamata via SSH [58/128/136/141]
4. **OS di destinazione**: Debian 12 bookworm arm64 [58/128/136/141]; trixie solo peer138
5. **Eseguire subito Fase 0-2**: SÌ, read-only [TUTTI, unanime]

## 7. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Patch locali perse (5 dirty + .install_method untracked) | Layer B: `git diff HEAD` + `git status --porcelain` + bundle + patches-core/ nel Layer A |
| Chiavi SSH perse / secrets illeggibili | id_rsa in chiaro off-box (peer128, 600) + Layer D; senza id_rsa niente decrypt envelope |
| state.db corrotto durante copy | `sqlite3 state.db ".backup ..."` — MAI cp/tar del .db vivo (WAL=corruzione) |
| Restore mai testato | Fase 2: dry-run restore su scratch + git apply --check + test decrypt — prerequisito, non opzionale |
| venv/binari non portabili Debian 11→12 | Ricreare venv con Python 3.11 + test smoke; manifest pinned versioni |
| Scheda SD morta durante upgrade | Layer D immagine completa (gateway fermo) prima |
| Cron/nightly persi | Export cron/ + `hermes cron list` JSON + crontab |
| Lockout iptables al restore | iptables PRIMA di esporre servizi + rollback-timer `at now+5min` |
| Gateway non parte al boot | `loginctl enable-linger fausto` |
| node_modules 1.1G gonfia il tar | Escluso; reinstall via `npm ci` documentata in Fase 4 |
| Repo backup non privato | Verificare faustothegrey/hermes-charon = PRIVATE |

## 8. Riferimenti
- Skill: hermes-backup (procedura backup/restore esistente)
- Repo backup: ~/Backups/hermes-config → faustothegrey/hermes-charon.git
- restore-hermes.sh già presente nel repo backup
