# Agent-card version fields mancanti — diagnosi completa

Quando il file `.py` contiene `"version": "0.1.3"` e `"max_text_length"` ma
l'endpoint `/hmp/agent-card` non li restituisce, la risposta HTTP è più corta
(193 byte invece di 238) e mancano gli ultimi due campi JSON.

Questo documento raccoglie la procedura diagnostica completa e le cause note.

## Quick check

```bash
# Confronta lunghezza risposta tra peer funzionante e peer difettoso
echo "peer105 (OK):  $(curl -s http://192.168.178.105:18643/hmp/agent-card | wc -c) byte"
echo "peer106 (KO):  $(curl -s http://192.168.178.106:18643/hmp/agent-card | wc -c) byte"
# OK = 238, KO = 193 (mancano version + max_text_length)
```

## Cause note

### 1. Bytecode `.pyc` obsoleto (causa PRIMARIA)

Il sintomo più comune: il file `.py` è stato aggiornato ma il bytecode `.pyc`
in `__pycache__/` è stato compilato PRIMA che il file fosse completato, o
Python considera il `.pyc` valido perché il timestamp è nello stesso secondo.

**Diagnosi:**

```bash
# Usa find, NON ls — ls a volte mostra __pycache__ come vuota quando i file esistono
find /root/.hermes/plugins/hmp -name '*.pyc' 2>/dev/null

# In alternativa, cerca TUTTI i __pycache__ in tutte le copie del plugin
find /root/.hermes -path '*/hmp*' -name '__pycache__' -type d 2>/dev/null
find /home/fausto/.hermes -path '*/hmp*' -name '__pycache__' -type d 2>/dev/null
```

**Ispeziona il bytecode compilato:**

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 -c "
import marshal
with open('/root/.hermes/plugins/hmp/__pycache__/adapter.cpython-311.pyc', 'rb') as f:
    f.read(16)  # header
    code = marshal.load(f)
for const in code.co_consts:
    if isinstance(const, str) and 'version' in const.lower():
        print('FOUND:', repr(const))
        break
else:
    print('NOT FOUND — bytecode OBSOLETO')
"
```

**Soluzione (forzare rigenerazione bytecode):**

```bash
# 1. Rimuovi TUTTI i file .pyc e directory __pycache__
find ~/.hermes/plugins/hmp -name '__pycache__' -type d -exec rm -rf {} \;
find ~/.hermes/plugins/hmp -name '*.pyc' -delete

# 2. Stessa cosa per tutte le copie del plugin
find /home/fausto/.hermes/plugins/hmp -name '__pycache__' -type d -exec rm -rf {} \; 2>/dev/null
find /home/fausto/.hermes/plugins/hmp -name '*.pyc' -delete 2>/dev/null

# 3. Forza nuovi timestamp
touch ~/.hermes/plugins/hmp/*.py

# 4. Riavvia il gateway via systemd (NON kill diretto)
systemctl --user restart hermes-gateway

# 5. Attendi 10-15 secondi e verifica
sleep 15
curl -s http://localhost:18643/hmp/agent-card | python3 -m json.tool
```

**Importante:** la cancellazione `rm -rf` DOPO aver fermato il gateway e PRIMA
di riavviarlo è fondamentale. Se il gateway è già in esecuzione quando cancelli
il __pycache__, Python lo ricrea automaticamente dal codice già caricato in
memoria (quindi colpisce anche il nuovo bytecode dal vecchio codice).

### 2. Copia fantasma del plugin in altra directory

Su peer106 è stato trovato un `adapter.py` ANCHE in:
- `/home/fausto/.hermes/plugins/hmp/adapter.py` — copia vecchia (Lug 16)
- `/root/.hermes/plugins/hmp.bak/adapter.py` — backup

Il gateway potrebbe caricare il plugin da un path diverso da quello atteso.

**Diagnosi:**

```bash
# Trova TUTTE le copie del plugin su tutto il filesystem
find / -name 'adapter.py' -path '*hmp*' 2>/dev/null

# Confronta gli md5
md5sum /root/.hermes/plugins/hmp/adapter.py
md5sum /home/fausto/.hermes/plugins/hmp/adapter.py 2>/dev/null
md5sum /root/.hermes/plugins/hmp.bak/adapter.py 2>/dev/null
```

**Soluzione:** sincronizzare TUTTE le copie, non solo quella principale.

### 3. Due versioni diverse del codice in circolazione

peer105 ha una versione SEMPLICE del plugin (senza `_consumer_loop`, usa
`MAX_MESSAGE_BYTES`). peer106 e peer70 locale hanno una versione PIÙ RECENTE
(con `_consumer_loop`, `MAX_TEXT_LENGTH`).

La versione semplice di peer105 funziona correttamente per agent-card. Quella
più recente (peer106/locale) non funziona, per motivi non ancora diagnosticati
(self-consistent bytecode bug, o import hook nel gateway).

**Sintomo differenziale (oltre all'agent-card):**

| Caratteristica | peer105 (semplice) | peer106 (nuovo) |
|---|---|---|
| Costante | `MAX_MESSAGE_BYTES = 2048` | `MAX_TEXT_LENGTH = 2048` |
| agent_card riga 143 | `"max_text_length": MAX_MESSAGE_BYTES` | `"max_text_length": int(os.getenv(...) or MAX_TEXT_LENGTH)` |
| hmp_send risposta | `"status": "queued"` | `"status": "working"` |
| Consumer loop | Assente | Presente (`_consumer_loop`) |
| disconnect | `if self._consumer_task is not None:` guard | Guard presente |
| agent-card | ✅ `version` + `max_text_length` | ❌ campi mancanti |

**Workaround:** se il peer difettoso ha file identici a quello funzionante ma
agent-card ancora non funziona, copiare l'INTERO codice dal peer funzionante
**via SCP diretto** (non via HMP), aggiornare ANCHE le copie fantasma, e
riavviare via systemd.

### 4. Systemd management non allineato

Il gateway su peer106 è gestito via `systemctl --user` (su Fedora), non tramite
`setsid`/`nohup`. Se il gateway viene avviato manualmente con `nohup`, systemd
non ne traccia lo stato e un successivo kill manuale non viene riconosciuto.

**Comando corretto per riavviare:**

```bash
# Fedora (peer105, peer106):
systemctl --user restart hermes-gateway

# Verifica stato:
systemctl --user is-active hermes-gateway
# → "active" (non "inactive")

# Se "inactive" ma risponde sulle porte → kill + reset-failed + start:
systemctl --user stop hermes-gateway
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway
```

## Flusso diagnostico completo

```bash
# 1. Lunghezza risposta (quick check)
SIZE=$(curl -s http://peerIP:18643/hmp/agent-card | wc -c)
[ "$SIZE" -lt 200 ] && echo "PROBLEMA: agent-card incompleto ($SIZE byte)"

# 2. Verifica file su disco
grep -c 'version' /root/.hermes/plugins/hmp/adapter.py   # deve essere >0
grep -c 'max_text' /root/.hermes/plugins/hmp/adapter.py  # deve essere >0

# 3. Cerca copie multiple
find / -name 'adapter.py' -path '*hmp*' 2>/dev/null

# 4. Confronta md5 con peer funzionante
md5sum /root/.hermes/plugins/hmp/adapter.py

# 5. Controlla bytecode compilato
find /root/.hermes/plugins/hmp -name '*.pyc' -exec ls -la {} \;

# 6. Ispeziona timestamp
stat -c '%y' /root/.hermes/plugins/hmp/adapter.py
stat -c '%y' /root/.hermes/plugins/hmp/__pycache__/adapter.cpython-311.pyc 2>/dev/null

# 7. Controlla età processo gateway
ps -eo pid,lstart,etime,cmd | grep -E 'hermes.*gateway' | grep -v grep

# 8. Verifica systemd
systemctl --user status hermes-gateway --no-pager -l | grep Active

# 9. Se tutto coincide ma agent-card ancora sbagliato → copia da peer funzionante
curl -s http://peerFUNZIONANTE:18643/hmp/agent-card | python3 -m json.tool
```

## Note su `execute_code` e peer128

Quando si diagnostica da `execute_code()` su peer70, peer128 (macOS, .112)
NON è raggiungibile — `No route to host`. Usare `curl` dal terminal diretto.

## Riferimenti

- `hmp-deploy-pitfalls.md` — Bug fixati nel deploy script
- `hmp-diagnostics.md` — Procedura diagnostica peer generica
- SKILL.md — Sezione "Pitfall: .pyc cache impedisce il reload del plugin"
