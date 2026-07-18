---
name: hmp-talkshow
description: "Host an interactive live talk show with remote Hermes peers via HMP."
type: custom
version: 2.0.0
author: Hermes Agent
platforms: [linux, macos]
---

# HMP Talk Show — Live Audio Show via Google Cast

Run an interactive live audio talk show where **the Hermes agent on peer70** 
(conduttore) questions remote Hermes peers (opinionists) via HMP. Every 
exchange is spoken aloud on a Google Home device using distinct edge-tts 
Italian voices.

Il conduttore parla su un Google Home (Pallino, Cucina, ecc.) tramite 
`tts-cast.py`, i peer rispondono via HMP, e le risposte vengono lette 
ad alta voce con voci diverse.

## Voice assignments

| Role | edge-tts voice | ID |
|------|---------------|-----|
| **Conduttore** (Hermes peer70) | Diego | `it-IT-DiegoNeural` |
| **peer105** | Elsa | `it-IT-ElsaNeural` |
| **peer106** | Isabella | `it-IT-IsabellaNeural` |

## Scripts

- `~/.hermes/scripts/tts-cast.py` — TTS + Google Cast (vedi skill `tts-cast`)
- `~/.hermes/scripts/hermes-talkshow/` — helper HMP scripts (su peer128/Mac)
- `~/.hermes/cache/tts-cast-device.json` — cache device per `--quick`

## Linked files

| File | Contenuto |
|------|-----------|
| [`references/hmp-message-format.md`](references/hmp-message-format.md) | Formato esatto dei messaggi HMP, polling, pattern di orchestrazione completo |
| [`templates/talkshow-round.sh`](templates/talkshow-round.sh) | Script template per eseguire un round completo (domanda → HMP → poll → lettura)

## Standard talk show workflow

### Nuovo formato: tema + domanda in unico messaggio

Si manda **un unico messaggio HMP** che contiene sia il tema che la prima 
domanda, con l'istruzione esplicita di rispondere in massimo 3-4 frasi.
Poi eventuali follow-up per approfondire.

```
1. PRE-SHOW:  invia tema+domanda a tutti i peer (unico messaggio)
              con "rispondi in massimo 3-4 frasi"
2. APERTURA:  tts-cast --device Pallino --voice Diego --quick "Benvenuti..."
3. POLL:      attendi risposte dai peer (via /hmp/poll/)
4. LETTURA:   tts-cast --device Pallino --voice Elsa --quick "Peer105 dice:..."
              tts-cast --device Pallino --voice Isabella --quick "Peer106 dice:..."
5. FOLLOW-UP (opzionale):
              invia nuovo messaggio HMP di approfondimento
              attendi risposta
              leggi con tts-cast
6. CHIUSURA:  tts-cast --device Pallino --voice Diego --quick "Chiudiamo..."
```

### Istruzioni per i peer (da includere nel messaggio HMP)

```
[TEMA + DOMANDA] 
Contesto: ...
Domanda: ...
⚠️ Rispondi in massimo 3-4 frasi, concreto e diretto.
Se hai altro da dire, lo approfondiamo al prossimo giro.
```

### Tempistiche

- **Apertura:** 15-20 sec di audio
- **Risposta peer:** 30 sec - 2 min di audio (3-4 frasi)
- **Poll interval:** 3-5 secondi
- **--quick mode:** dopo la prima discovery (8s), i round successivi 
  impiegano ~3-4 sec totali (TTS + cast)
- **Totale show:** 5-10 min per 2 round

## Pitfalls

0. **LEGGERE SEMPRE IL TESTO REALE DEI PEER** — Il talkshow ha senso solo se
   le risposte dei peer vengono effettivamente lette su Pallino. Non usare
   frasi fisse come "Peer105 ha risposto." — il pubblico sente solo quello.
   Invece: cattura la risposta del peer in una variabile e passala al TTS:
   ```bash
   R=$(bash ~/.hermes/scripts/hmp/hmp-send-and-wait.sh 105 "Domanda?" round)
   python3 ~/.hermes/scripts/tts-cast.py --device Pallino --voice it-IT-ElsaNeural --quick "$R"
   ```
   Un talkshow con solo "ha risposto" è un talkshow fallito.

1. **known_hosts può fallire** se il device cambia IP. In quick mode c'è 
   un fallback automatico a discovery completa.
2. **Zeroconf chiuso due volte** — nel fallback di quick mode usare 
   una seconda istanza Zeroconf, non riusare quella già chiusa.
3. **Peer in sessione lunga** — se un peer è già in una conversazione, 
   il nuovo messaggio HMP viene accodato. Il poll potrebbe durare a lungo.
4. **Messaggio tema + domanda singolo** — evita il problema del doppio 
   messaggio, il peer risponde una volta sola.
5. **edge-tts prima chiamata** — la prima generazione TTS carica il modello.
   Fai un warm-up silenzioso prima dello show.
6. **Messaggi HMP lunghi >3KB** bloccano il peer per minuti. La domanda
   talkshow completa (tema + domanda + istruzioni) deve stare sotto 2KB.
   Se serve più contesto, usa un secondo messaggio dopo la prima risposta.
7. **File transfer via HMP**: per installare script su un peer, codifica in
   base64 e mantieni il messaggio totale sotto 3KB. Oltre questo limite il
   peer impiega >5 minuti.
