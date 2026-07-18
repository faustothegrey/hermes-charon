# HMP Message Size Limits

I peer agentici processano i messaggi HMP in sessioni Hermes.
La dimensione del payload.text impatta direttamente sui tempi di risposta.

## Regola pratica

| Dimensione | Tempo risposta tipico | Esito |
|-----------|----------------------|-------|
| < 500 byte | 5-10 secondi | ✅ Rapido |
| 500-2000 byte | 10-30 secondi | ✅ Normale |
| 2000-3000 byte | 30-120 secondi | ⚠️ Lento |
| > 3000 byte | > 5 minuti o blocco | ❌ Peer si blocca |

**Mai superare 3000 byte di testo nel payload.**

## Pattern per file transfer via HMP

Per inviare script o file ai peer, usare base64:

```bash
# Mittente: codifica
B64=$(base64 -w0 script.py)

# Invia come messaggio HMP singolo (se il totale sta sotto 3KB)
curl -s -X POST "http://192.168.178.<PEER>:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d "{
    \"hmp_version\": \"1.0\",
    \"message_id\": \"install_$(date +%s%N)\",
    \"from\": \"peer70\",
    \"to\": \"peer<PEER>\",
    \"type\": \"request\",
    \"payload\": {\"text\": \"mkdir -p dir && echo '${B64}' | base64 -d > path/script.py && python3 path/script.py\"}
  }"
```

Il messaggio totale (istruzioni + base64 + contesto) deve stare sotto 3KB.

## Alternative per file grandi (>3KB)

1. **Spezzare in più messaggi**: inviare il file in chunk, ognuno sotto 2KB
2. **SSH + SCP**: se la chiave SSH è configurata, usare scp:
   ```bash
   scp file.py fausto@192.168.178.<PEER>:~/.hermes/scripts/
   ```
3. **Base64 via SSH**: per file medi, evitare HMP del tutto:
   ```bash
   base64 -w0 file.py | ssh fausto@192.168.178.<PEER> "base64 -d > ~/.hermes/scripts/file.py"
   ```

## Pattern: installazione tooling su peer remoto

Usato con successo in questa sessione per distribuire `registry-publish.py`:

1. Preparare una versione **mini** dello script (solo core, niente CLI, ~1.5KB)
2. Fare il base64 e verificare che il messaggio totale sia sotto 2.5KB
3. Inviare con istruzioni di installazione inline
4. Peer risponde in 15-45 secondi con OK/ERRORE
