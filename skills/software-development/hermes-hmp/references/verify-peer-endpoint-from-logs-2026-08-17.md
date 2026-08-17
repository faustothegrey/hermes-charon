# Verificare l'IP/endpoint attuale di un peer (da peer70, senza SSH)

Quando un peer segnala un cambio IP o si chiede l'endpoint verificato, NON fidarsi
di registry/memoria: verificare dal traffico live di peer70.

## Procedura

1. **DB messaggi autoritativo**: `~/.hermes/data/hmp_gateway_plugin/messages.db`
   tabella `hmp_gateway_messages` (colonne: `message_id`, `idempotency_key`,
   `from_peer`, `to_peer`, `chat_id`, `text`, `status`, `raw_json`, `accepted_at`).
   Un messaggio `from_peer=<peer>` con `accepted_at` recente = conferma live che
   il peer è online. NOTA: il DB NON registra l'IP sorgente — serve l'access log.
2. **Access log per IP sorgente**: `~/.hermes/logs/agent.log` righe
   `aiohttp.access: <IP> [data] "POST /hmp/send" 202` = messaggio IN entrata da
   quell'IP; `GET /hmp/poll/<message_id>` = chi fa poll (il client mittente che
   attende la risposta). L'IP della POST più recente per quel peer = IP attuale
   verificato. Esempio utile: la riga access log della POST che ha trasportato il
   messaggio che stai processando.
3. **Conferma identità**: risposte `/health` nei log (`errors.log`, `agent.log`)
   con `node_id=<peer>` + `HTTP=200` confermano che quell'IP serve quel peer.
4. **Registry**: `~/.hermes/registry/peers/<peer>.json` = ultimo manifest, MA può
   essere stantio (giorni). Usarlo solo come riferimento, non come verità.
5. **Se il traffico live concorda col vecchio IP mentre l'utente segnala un
   cambio**: riportare l'evidenza esatta (timestamp della POST/poll) e dire
   esplicitamente che il cambio non è ancora stato osservato da peer70. Non
   inventare un nuovo IP per compiacere la richiesta.

## Comandi utili

```bash
# Ultimi messaggi da un peer (DB, no sqlite3 CLI — usare python3)
python3 - <<'EOF'
import sqlite3, datetime
conn = sqlite3.connect("/home/fausto/.hermes/data/hmp_gateway_plugin/messages.db")
cur = conn.cursor()
cur.execute("SELECT message_id, from_peer, to_peer, substr(text,1,100), accepted_at "
            "FROM hmp_gateway_messages WHERE from_peer='<peer>' ORDER BY rowid DESC LIMIT 5")
for r in cur.fetchall():
    ts = datetime.datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M:%S') if r[4] else '?'
    print(ts, "|", r[0], "|", r[1], "->", r[2], "|", r[3])
EOF

# Access log: ultimo traffico da un IP specifico
grep -n "<IP>" ~/.hermes/logs/agent.log | grep "aiohttp.access" | tail -15
```

## Pitfall

- Il DB messaggi ha colonna `from_peer` ma NON l'IP: usare l'access log in parallelo.
- `sqlite3` CLI può mancare (usare il modulo python3 `sqlite3`).
- Il poll di un message_id può venire da un IP diverso dalla POST (client con
  source-IP differente): la POST /hmp/send è la firma più affidabile dell'IP.
