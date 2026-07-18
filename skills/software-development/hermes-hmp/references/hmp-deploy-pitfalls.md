# Deploy Script Pitfalls

Bug fixati durante lo sviluppo di `hmp-deploy.sh`.

## 1. IP health check per peer128

**Problema:** Il deploy script costruiva l'URL health check come
`http://192.168.178.${peer}:18643/health`, ma peer128 è a `.112` non `.128`.

**Sintomo:** peer128 veniva rollbackato sempre perché l'health check puntava
all'IP sbagliato, anche se il gateway era perfettamente online.

**Fix:** Estrarre l'IP dalla PEER_MAP invece di usare il peer ID:
```bash
ip_addr="${ssh_user#*@}"  # fausto@192.168.178.112 → 192.168.178.112
curl -sf "http://${ip_addr}:18643/health"
```

## 2. Path SCP per root user

**Problema:** Lo script usava `scp file root@peer:~/.hermes/plugins/hmp/`
dove `~` si espande correttamente. Ma precedentemente usava
`scp file root@peer:${HMP_DIR}/$f` dove `HMP_DIR` era
`/home/fausto/.hermes/plugins/hmp/` — percorso che non esiste su peer105/106
dove l'home di root è `/root/`.

**Sintomo:** I file venivano copiati in `/home/fausto/...` su peer105/106,
ma il gateway legge da `/root/.hermes/...`. La versione non cambiava mai.

**Fix:** Usare path relativo `~/.hermes/plugins/hmp/` nel target SCP.

## 3. Restart gateway su Fedora (peer106)

**Problema:** `systemctl --user restart hermes-gateway` manda SIGTERM.
A volte il vecchio processo non muore subito e resta in stato
`deactivating (stop-sigterm)` per minuti, bloccando il restart.

**Sintomo:** Health check fallisce perché il vecchio processo tiene la porta
ma non risponde più, mentre il nuovo non può partire.

**Fix:** Per peer106 (Fedora):
```bash
systemctl --user kill hermes-gateway -s KILL
sleep 1
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway
```

## 4. macOS launchctl kickstart

**Problema:** `launchctl kickstart gui/501/ai.hermes.gateway` senza flag `-k`
non termina il processo già in esecuzione. Il comando falliva con
"Unrecognized target specifier".

**Sintomo:** Il gateway su peer128 non veniva mai effettivamente riavviato,
e il plugin restava sulla versione vecchia.

**Fix:** Usare `-k` per killare prima di avviare:
```bash
launchctl kickstart -kp gui/501/ai.hermes.gateway
```

## 5. Duplicazione riga debug

**Problema:** Durante debugging con `print()` su stderr, ho accidentalmente
duplicato una riga di debug con un patch malformato.

**Lezione:** Leggere sempre il file completo prima di patchare. Usare
`read_file` prima di `patch`.
