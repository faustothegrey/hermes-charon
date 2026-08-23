# RUNBOOK — Reinstall Hermes Agent (peer70/Charon) da Snapshot NAS
# ISTRUZIONI COMPLETE PER IL NUOVO AGENTE
# (da eseguire sul NUOVO sistema, dopo upgrade OS)
# Versione: 1.0 · 2026-08-23 · autore: ALICE (peer70)
# Fonte: FRITZ.NAS/Hermes-Snapshot/hermes-snapshot-20260823-1210.tar.gz

# ═══════════════════════════════════════════════════════════════════════
# 0. CONTESTO E PRINCIPI
# ═══════════════════════════════════════════════════════════════════════
# - Host: peer70 "Charon", RPi arm64, COORDINATORE mesh
# - OS: passa a Debian 12 bookworm (Python 3.11 nativo — stesso toolchain attuale)
# - Hermes da ripristinare: v0.17.0 + 5 file dirty patch (observe-channel cap-reuse)
# - Questo runbook ripristina l'AGENTE IDENTICO a prima dell'upgrade.
# - REGOLA: un cambiamento alla volta. Prima OS (questo runbook). Il bump di
#   versione Hermes è un progetto SEPARATO (sezione 11) da fare DOPO, a freddo.
# - Come peer70 coordinatore: massima stabilità, niente patch sperimentali.
#
# COSE CHE SERVE AVERE PRIMA DI INIZIARE:
#   - Accesso alla rete LAN (il NAS FRITZ!Box a 192.168.178.1)
#   - Credenziali NAS: fausto / ccll4372 (o quelle aggiornate)
#   - Password sudo/utente locale (fausto)
#   - ~/.ssh/id_rsa (è nello snapshot; se il box è nuovo, ripristinare PRIMA
#     di toccare GitHub/envelope)

# ═══════════════════════════════════════════════════════════════════════
# 1. INSTALLAZIONE OS DI BASE
# ═══════════════════════════════════════════════════════════════════════
# Obiettivo: Debian 12 bookworm arm64, utente "fausto", hostname "Charon".
# - Scarica immagine: https://cdimage.debian.org/debian-cd/current/arm64/iso-cd/
#   (o Raspberry Pi OS derivato bookworm se preferisci)
# - Flash su microSD, boot.
# - Crea utente: fausto (uid 1000, come oggi).
# - Imposta hostname: Charon
#   sudo hostnamectl set-hostname Charon
# - Aggiorna:
#   sudo apt update && sudo apt full-upgrade -y
#
# VERIFICA:
#   hostname            → Charon
#   lsb_release -d      → Debian GNU/Linux 12 (bookworm)
#   python3 --version   → 3.11.x
#   id fausto           → uid=1000(fausto)

# ═══════════════════════════════════════════════════════════════════════
# 2. PACCHETTI DI BASE
# ═══════════════════════════════════════════════════════════════════════
sudo apt install -y \
  git curl wget rsync openssl \
  python3 python3-pip python3-venv python3-dev \
  tmux netfilter-persistent iptables \
  cifs-utils smbclient \
  build-essential \
  dbus-user-session

# Node.js (richiesto da Hermes — il runtime è in ~/.hermes/node nello snapshot,
# ma su sistema nuovo conviene reinstallare o copiare quello vecchio, vedi sez. 6)
# npm/npx servono per i plugin.

# ═══════════════════════════════════════════════════════════════════════
# 3. RIPRISTINO IDENTITÀ DI SISTEMA (PRIMA di tutto il resto)
# ═══════════════════════════════════════════════════════════════════════
# 3.1 SSH KEYS (CRITICO: senza id_rsa niente decrypt envelope secrets)
#     Lo snapshot contiene ssh/id_rsa, id_rsa.pub, authorized_keys.
mkdir -p ~/.ssh && chmod 700 ~/.ssh
#   (copia i file dallo snapshot — vedi sez. 5 per montare il NAS)
#   chmod 600 ~/.ssh/id_rsa ~/.ssh/authorized_keys
#   chmod 644 ~/.ssh/id_rsa.pub

# 3.2 SUDOERS — ripristina il file (o crea):
#   /etc/sudoers.d/fausto-nopasswd   →   fausto ALL=(ALL) NOPASSWD:ALL
sudo sh -c 'echo "fausto ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/fausto-nopasswd'

# 3.3 FSTAB — ripristina il mount CIFS del NAS (credenziali in file separato):
sudo sh -c 'cat > /etc/fstab' <<'EOF'
proc            /proc           proc    defaults          0       0
PARTUUID=ROOT / ext4 defaults,noatime 0 1
//192.168.178.1/FRITZ.NAS/Software /home/fausto/Software cifs credentials=/home/fausto/.smbcredentials,uid=1000,gid=1000,iocharset=utf8,noperm,nofail,x-systemd.automount,noauto 0 0
EOF
#   (adatta PARTUUID a /boot e /)
#   Crea ~/.smbcredentials con i dati NAS:
cat > ~/.smbcredentials <<'EOF'
username=fausto
password=ccll4372
EOF
chmod 600 ~/.smbcredentials

# 3.4 IPTABLES — ripristina PRIMA di esporre servizi, con safety:
#   (dal sistema vecchio: system/iptables.rules nello snapshot)
sudo iptables-restore < system/iptables.rules
#   SAFETY: applica con rollback automatico se perdi la connessione:
#   echo "sudo iptables -P INPUT ACCEPT" | sudo at now + 5 minutes
#   (se non c'è at: sudo apt install at)
sudo netfilter-persistent save

# 3.5 LINGER — il gateway user-unit parte al boot anche senza login:
sudo loginctl enable-linger fausto

# ═══════════════════════════════════════════════════════════════════════
# 4. MONTARE IL NAS E LEGGERE LO SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════
# 4.1 Monta il NAS (o usa smbclient diretto)
mkdir -p ~/Software
sudo mount -a          # monta il mount CIFS da fstab
#   oppure ad-hoc:
#   sudo mount -t cifs //192.168.178.1/FRITZ.NAS/Software ~/Software \
#     -o credentials=/home/fausto/.smbcredentials,uid=1000,gid=1000,noperm

# 4.2 Estrai lo snapshot in staging
mkdir -p ~/restore && cd ~/restore
tar -xzf ~/Software/../Hermes-Snapshot/hermes-snapshot-20260823-1210.tar.gz
#   (o se la cartella Hermes-Snapshot è alla radice del NAS, non in Software:
#    smbclient //192.168.178.1/FRITZ.NAS -U 'fausto%...' \
#      -c 'cd Hermes-Snapshot; get hermes-snapshot-20260823-1210.tar.gz ~/restore/snap.tar.gz')
#   Struttura: agent-core/  system/  ssh/  source-patches/  RESTORE-MANIFEST.md

# ═══════════════════════════════════════════════════════════════════════
# 5. RIPRISTINO AGENT-CORE (config, skills, secrets, memories)
# ═══════════════════════════════════════════════════════════════════════
# 5.1 Copia l'intero agent-core in ~/.hermes
mkdir -p ~/.hermes
cp -a ~/restore/.../agent-core/* ~/.hermes/

# 5.2 Permessi corretti
chmod 600 ~/.hermes/.env ~/.hermes/auth.json ~/.hermes/config.yaml
chmod 700 ~/.hermes/skills ~/.hermes/plugins ~/.hermes/scripts

# 5.3 VERIFICA che i file chiave siano presenti e validi:
python3 -c "import yaml;yaml.safe_load(open('/home/fausto/.hermes/config.yaml'));print('config OK')"
grep -cE '^[A-Z_]+=' ~/.hermes/.env          # deve dare ~17
ls ~/.hermes/skills | head                    # 97 skill
cat ~/.hermes/memories/MEMORY.md | head       # memoria
cat ~/.hermes/registry/registry.json | head   # registry mesh

# ═══════════════════════════════════════════════════════════════════════
# 6. INSTALLAZIONE HERMES (stock v0.17.0 — poi si applica la patch)
# ═══════════════════════════════════════════════════════════════════════
# Il metodo di installazione originale era GIT (file .install_method = "git").
# Ricostruire lo stesso layout:
cd ~/.hermes
git clone https://github.com/NousResearch/hermes-agent.git hermes-agent
cd ~/.hermes/hermes-agent
git checkout f171842f0de73171031ce4f62a4fcfc7adc397d8   # upstream base esatta (vedi source-patches/upstream-base.txt)

# Crea venv e installa (stesso percorso della unit systemd):
python3 -m venv venv
./venv/bin/pip install -U pip
./venv/bin/pip install -e .       # o: ./venv/bin/pip install .

# Launcher CLI (ripristina il symlink/script che c'era):
cat > ~/.local/bin/hermes <<'EOF'
#!/usr/bin/env bash
unset PYTHONPATH
unset PYTHONHOME
exec "/home/fausto/.hermes/hermes-agent/venv/bin/hermes" "$@"
EOF
chmod +x ~/.local/bin/hermes

# Node runtime: ripristina ~/.hermes/node dallo snapshot (o reinstalla nodejs
# compatibile — PATH della unit usa ~/.hermes/node/bin)
#   (se nello snapshot non c'è node/ perché escluso: apt install nodejs npm)

# VERIFICA:
hermes --version   # → Hermes Agent v0.17.0 (2026.6.19)

# ═══════════════════════════════════════════════════════════════════════
# 7. APPLICAZIONE PATCH CORRE (LA PARTE DELICATA)
# ═══════════════════════════════════════════════════════════════════════
# IMPORTANTE: usa source-patches/hermes-current-dirty.patch (il patch ATTUALE,
# 5 file), NON patches-core/observe-channel-core-0.17.0.patch (generazione
# vecchia che tocca file già finiti upstream — non applicare quello).
cd ~/.hermes/hermes-agent
git apply --check ~/restore/.../source-patches/hermes-current-dirty.patch
#   → deve dire "CLEAN". Se fallisce, FERMATI: il base non è quello giusto.
git apply ~/restore/.../source-patches/hermes-current-dirty.patch

# Untracked file:
echo "git" > ~/.hermes/hermes-agent/.install_method

# VERIFICA — deve corrispondere a source-patches/hermes-dirty-list.txt:
git status --porcelain
#   M agent/agent_init.py
#   M agent/turn_context.py
#   M gateway/platforms/base.py
#   M gateway/run.py
#   M run_agent.py
#   ?? .install_method

# ═══════════════════════════════════════════════════════════════════════
# 8. SYSTEMD: GATEWAY + NETBOARD
# ═══════════════════════════════════════════════════════════════════════
# 8.1 Gateway user-unit (ripristina i file da system/ o dal vivo):
mkdir -p ~/.config/systemd/user
#   copia system/hermes-gateway.service e hermes-gateway-restart.service
#   in ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway.service
#   (richiede linger attivo — sez. 3.5)

# 8.2 Netboard (system services, framebuffer + web):
sudo cp system/netboard.service /etc/systemd/system/
sudo cp system/netboard-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now netboard.service netboard-web.service

# ═══════════════════════════════════════════════════════════════════════
# 9. CRON E JOB HERMES
# ═══════════════════════════════════════════════════════════════════════
# 9.1 crontab utente (4 job capreuse — ripristina da system/crontab.txt):
crontab system/crontab.txt

# 9.2 Job cron Hermes (~27): i file sono in ~/.hermes/cron/ (già ripristinati
#     con agent-core). Verifica che vengano rilevati:
hermes cron list --all
#   → devono apparire TUTTI i job (backup nightly, watchdogs, HMP, exchange...)

# ═══════════════════════════════════════════════════════════════════════
# 10. VERIFICA FINALE COMPLETA
# ═══════════════════════════════════════════════════════════════════════
echo "--- versione ---"; hermes --version
echo "--- patch applicata ---"; cd ~/.hermes/hermes-agent && git status --porcelain
echo "--- gateway ---"; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8642/health   # → 200
echo "--- HMP ---";     curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18643/hmp/health  # → 200
echo "--- skills ---";  find ~/.hermes/skills -name SKILL.md | wc -l   # → 97
echo "--- plugins ---"; ls ~/.hermes/plugins/    # capability-reuse, harness-feedback, hmp
echo "--- memoria ---"; wc -l ~/.hermes/memories/MEMORY.md
echo "--- NAS ---";     df -h ~/Software | tail -1
echo "--- cron hermes ---"; hermes cron list --all | grep -c Name:
echo "--- crontab ---"; crontab -l | grep -c capreuse   # → 4
echo "--- iptables ---"; sudo iptables -L INPUT -n | head -3   # policy DROP + LAN ACCEPT

# HMP bidirezionale (test con un peer): chiedere a un peer di pingare, o:
curl -s http://192.168.178.141:18643/hmp/health   # peer141 Stella deve rispondere

# ═══════════════════════════════════════════════════════════════════════
# 11. (OPZIONALE, SEPARATO) BUMP DI VERSIONE HERMES
# ═══════════════════════════════════════════════════════════════════════
# NON fare subito. Prima: OS stabile + 0.17.0 + patch verificati (sez. 1-10).
# Quando decidi di salire di versione, procedi come progetto a parte:
#
# 1. Snapshot di stato prima (rivedere il tarball NAS).
# 2. Su un CLONE di test (peer106/peer141 suggeriti dai peer) verifica che il
#    nuovo Hermes (0.19/0.20.x) si installi e i plugin hmp/capreuse funzionino.
# 3. Le 5 patch locali: RIBASA, non riapplicare alla cieca. Alcune sono già
#    upstream (es. 5bb34a7 typing-indicator). Usa patches-core/ come source of
#    truth, applica con git apply --3way, risolvi i conflitti, verifica per
#    COMPORTAMENTO (canale observe, trace-id, typing) non solo git status.
# 4. peer70 = coordinatore → sali di versione per ULTIMO (canary prima).
# 5. Regola mesh: un cambiamento alla volta, rollback sempre possibile
#    (il tarball NAS resta valido per la versione 0.17.0).
#
# SE il bump rompe qualcosa → ripristina dal tarball (sez. 5-7) e resta su 0.17.0.

# ═══════════════════════════════════════════════════════════════════════
# 12. ROLLBACK / SE QUALCOSA VA STORTO
# ═══════════════════════════════════════════════════════════════════════
# - Il tarball è la fonte canonica. Sempre estraibile in fresh ~/restore.
# - state.db (644M sessioni) NON è nel tarball: se serve la cronologia completa,
#   recuperare da peer128 (copia off-box) — per ora peer70 è l'unico nodo.
# - Se la patch non si applica (sez. 7): NON forzare. Ricontrolla che il base
#   sia f171842f e che tu stia usando source-patches/hermes-current-dirty.patch.
# - Se il gateway non parte: journalctl --user -u hermes-gateway -n 50
# - Se i secrets non si decifrano: serve ~/.ssh/id_rsa (sez. 3.1) — senza,
#   l'envelope GitHub è illeggibile.

# ═══════════════════════════════════════════════════════════════════════
# FINE RUNBOOK
# ═══════════════════════════════════════════════════════════════════════
