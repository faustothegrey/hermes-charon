# SSE Streaming — Esplorazione v0.2.0 (non adottata)

## Contesto

Durante lo sviluppo di v0.2.0 del plugin HMP, è stato implementato un endpoint
SSE (`GET /hmp/stream/{message_id}`) per streaming in tempo reale delle risposte.

## Perché non adottata

1. **Nessun tool progress intermedio**: Con DeepSeek v4 flash (e probabilmente
   la maggior parte dei provider), l'agente produce UNA SOLA risposta — non ci
   sono messaggi intermedi separati per ogni tool call. Quindi SSE e poll
   ricevono lo stesso contenuto nello stesso momento.
2. **Complessità aggiuntiva**: Il codice SSE (in-memory queue, event store,
   endpoint stream) aggiungeva ~150 righe di codice per zero vantaggio pratico.
3. **Rischio di regressione**: Modificare `adapter.send()` per non chiamare
   `store.complete()` rischiava di rompere la backward compat con poll e
   send_and_wait.
4. **Modifica al core**: Per avere tool progress intermedi, serviva aggiungere
   `"hmp"` a `_PLATFORM_DEFAULTS` in `gateway/display_config.py` — una modifica
   al core Hermes che rompeva la compatibilità tra versioni del plugin.

## Cosa è rimasto

- `SUPPORTS_MESSAGE_EDITING = False` nell'adapter — evita che il gateway
  cerchi di fare streaming editing su HMP
- `send_or_update_status()` implementata (pronta, mai chiamata dalla gateway)
- La lezione: **SSE non serve se il modello non produce messaggi intermedi**

## Se in futuro servisse

1. Aggiungere `"hmp"` a `_PLATFORM_DEFAULTS` in `display_config.py` con
   `interim_assistant_messages: True` e `tool_progress: new`
2. Il gateway chiamerebbe `send_or_update_status()` sull'adapter
3. L'adapter pusha su SSE via SSEStreamStore
4. MA: attenzione alla compatibilità — se il core ha HMP in display_config
   e il plugin è v0.1.0, la gateway crash-loopa
