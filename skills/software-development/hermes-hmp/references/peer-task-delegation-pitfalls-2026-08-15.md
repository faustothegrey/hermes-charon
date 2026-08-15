# Peer task delegation & plugin config — pitfalls (2026-08-15)

Lezioni dalla sessione di convergenza 2.4.18→2.4.19 (peer70 ↔ peer141, canale
observe 🔍) e dal deploy HMP 0.1.4 su peer138/141.

## 1. `send_and_wait` va in timeout sui task lunghi — ma il messaggio è consegnato

`/hmp/send_and_wait` con timeout >60s su un task che richiede implementazione +
restart + smoke test (es. "porta il canale observe sul tuo core") va in timeout
PRIMA che il peer finisca. Il messaggio però è stato preso in carico e il peer
lo elabora fino in fondo (verificabile dal suo gateway.log:
`inbound message ... response ready time=400s api_calls=17`).

**Recovery (pattern che funziona):**
1. NON ri-inviare il task (doppio fire). Verificare lo stato reale via SSH:
   `git status --short` nel repo del peer + `ls plugins/` + `pgrep gateway`.
2. Se il lavoro è in corso/completato, chiedere un **report compatto** con un
   secondo send_and_wait a timeout breve: "rispondi in formato COMPATTO max N
   caratteri: FILE: ... | SMOKE: ... | ESITO: ...". Il peer accorcia e la
   risposta entra nel timeout.
3. La risposta dettagliata originale è persa (il send originale è scaduto) —
   non tentare di recuperarla dal canale; il report compatto basta.

## 2. `plugins.enabled` deve essere una lista YAML, NON una stringa JSON

peer141 ha abilitato il plugin harness-feedback scrivendo:
```yaml
plugins:
  enabled: '["hmp", "harness-feedback"]'   # ❌ stringa JSON
```
Risultato: il parser non la riconosce come lista → **nessun plugin platform
viene registrato** → al riavvio il gateway logga
`Skipping invalid routing entry 'agent:main:hmp:dm:peer70': 'hmp' is not a valid Platform`
→ **HMP DOWN, API UP** (sintomo: health :18643 giù, :8642 su).

Formato corretto:
```yaml
plugins:
  enabled:
    - hmp
    - harness-feedback
```

**Check rapido dopo un riavvio con HMP giù:** `grep -A3 '^plugins:' config.yaml`
— se `enabled` è su una riga sola tra apici, è il bug. Fix: sostituire con
lista YAML, riavviare da shell esterna, riverificare :18643.

## 3. Turno HMP appeso (sessione stuck) — muore col riavvio del gateway

Sintomo: messaggio inbound HMP ricevuto (`inbound message ... msg='check peer58
health...'`) ma **nessuna** `response ready` dopo — turno appeso su chiamata
LLM, sessione a 216–245K token. peer141 lo segnala come "messaggio rimasto in
delivering".

Recovery: il turno appeso vive nel processo del gateway → un restart da shell
esterna lo uccide. Dopo il restart:
- coda HMP pulita (`agent_messages.db`: status NOT IN delivering/working → 0)
- health :18643 OK
- il peer può rilanciare il task ("puoi rilanciare il Case B quando vuoi")

Nota: 216K token su window 1M NON è la causa (compressione a 500K) — il hang
era la chiamata LLM, non la dimensione. Non comprimere/resettare la sessione
per questo; basta il restart.

## 4. Delegare l'implementazione a un peer (pattern peer141)

Quando Fausto dice "falla implementare a lui stesso internamente": si delega il
task completo via send_and_wait con timeout lungo, si verifica via SSH che il
peer stia lavorando (file core modificati, plugin creato), e dopo il restart
del gateway del peer si chiede conferma dell'esito. Il peer implementa sul
PROPRIO core (es. 0.20.1) — non portare patch scritte per un'altra versione.
