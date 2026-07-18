---
name: tts-cast
description: TTS + Google Cast — Hermes parla sui Google Home della rete
type: custom
version: 1.0.0
---

# tts-cast: Text-to-Speech via Google Cast

Script Python che fa parlare i Google Home/Nest Mini della rete locale usando
edge-tts (gratuito, locale) o OpenAI TTS.

**Bug fix importante**: Il server HTTP deve essere inizializzato passando `directory=base_dir`
al costruttore di `SimpleHTTPRequestHandler` — impostare `server.directory = ...` non funziona
e il device prende 404 (fa "bleep" invece di parlare).

## Prerequisiti

- Raspberry Pi (o Linux nella stessa LAN dei Google Home)
- Pacchetti: `pychromecast`, `edge-tts`, `zeroconf`

## Script

`~/.hermes/scripts/tts-cast.py`

## Uso base

```bash
# Elenca dispositivi disponibili
python3 ~/.hermes/scripts/tts-cast.py --list-devices

# Parla su un dispositivo specifico
python3 ~/.hermes/scripts/tts-cast.py --device Pallino "Ciao mondo!"
python3 ~/.hermes/scripts/tts-cast.py --device Cucina "Il caffè è pronto"

# Con OpenAI TTS (se hai OPENAI_API_KEY)
python3 ~/.hermes/scripts/tts-cast.py --engine openai --device Pallino "Test"

# Personalizza voce edge-tts
python3 ~/.hermes/scripts/tts-cast.py --device Cucina --voice it-IT-ElsaNeural "Test"
```

## Modalità Quick (`--quick`)

Elimina il lag della discovery mDNS riutilizzando il device in cache.
Tempo totale: ~3-4s invece di ~12s.

```bash
# Prima chiamata: fa discovery piena (8s) e salva il device in cache
python3 ~/.hermes/scripts/tts-cast.py --device Pallino "Prima volta"

# Chiamate successive: salta discovery, usa known_hosts (~0.5s)
python3 ~/.hermes/scripts/tts-cast.py --device Pallino --quick "Veloce!"
```

La cache è in `~/.hermes/cache/tts-cast-device.json`. Si aggiorna
automaticamente a ogni scoperta.

## Talkshow Orchestration

Strategia per uso talkshow (N round consecutivi, vedi anche skill `hmp-talkshow`):

1. **Primo giro** (annuncio tema / setup): chiamata normale (8s discovery)
2. **Round successivi**: `--quick` su ogni intervento (~3s l'uno)
3. La connessione a Pallino NON va tenuta aperta — ogni chiamata
   riconnette in ~1s grazie a known_hosts

Pattern:
```bash
# Annuncio tema (con discovery)
python3 tts-cast.py --device Pallino --voice it-IT-DiegoNeural "Tema stasera..."

# Domanda a peer105 (quick)
python3 tts-cast.py --device Pallino --voice it-IT-DiegoNeural --quick "Domanda..."

# Risposta di peer105 (quick, voce Elsa)
python3 tts-cast.py --device Pallino --voice it-IT-ElsaNeural --quick "Risposta..."
```

## Architettura

1. edge-tts genera MP3 da testo (locale, gratuito, voci neurali)
2. Server HTTP Python temporaneo serve il file sulla LAN
3. PyChromecast scopre il Google Home per nome
4. Cast dell'URL audio al dispositivo
5. `--quick`: evita mDNS bulk, usa `known_hosts` con IP dalla cache

## Dispositivi noti sulla rete

| Nome | IP | Tipo |
|------|-----|------|
| Pallino | 192.168.178.54 | Google Home Mini |
| Cucina | 192.168.178.64 | Google Home Mini |
| Camera Grande | 192.168.178.22 | Google Home Mini |
| Salotto 2 | 192.168.178.124 | Chromecast |

## Voci edge-tts italiane

- `it-IT-ElsaNeural` — femminile, naturale (default)
- `it-IT-IsabellaNeural` — femminile
- `it-IT-DiegoNeural` — maschile, usata come moderatore talkshow
- `it-IT-GianniNeural` — maschile

## Voci OpenAI TTS

- `nova`, `alloy`, `echo`, `fable`, `onyx`, `shimmer`

## Pitfall: Zeroconf instance riutilizzato nel fallback `--quick`

Quando `known_hosts` fallisce (es. device cambiato IP), il codice di
fallback deve creare un NUOVO Zeroconf instance (`z2`), non riusare
quello già chiuso dal `finally` del primo `try`. Usare lo stesso
Zeroconf chiuso causa `RuntimeError: The event loop is not running`.

```python
# SBAGLIATO: z è già stato chiuso
z = Zeroconf()
try:
    casts, browser = discover_chromecasts(timeout=2, zeroconf_instance=z)
    browser.stop_discovery()
    ...
finally:
    z.close()  # z chiuso!
# ... più avanti
discover_chromecasts(timeout=3, zeroconf_instance=z)  # BOOM!

# GIUSTO: ogni scoperta col suo Zeroconf
z = Zeroconf()
try:
    ...
finally:
    z.close()

z2 = Zeroconf()
try:
    ...
finally:
    z2.close()
```

## Pitfall: server HTTP serve directory sbagliata

Il `SimpleHTTPRequestHandler` ignora `server.directory = ...` (proprietà
dell'istanza server non letta dal handler). Il fix è passare `directory=`
al costruttore della sottoclasse:

```python
class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=base_dir, **kwargs)
```

Senza questo fix, Chromecast riceve l'URL `/tmp/file.mp3` ma il server
serve dalla CWD → 404 → Google Home fa "bleep" invece di parlare.

## Pitfall: nome voce edge-tts

edge-tts vuole il nome completo: `it-IT-DiegoNeural`, non solo `Diego`.
Il nome abbreviato causa `CalledProcessError` (exit 1).
