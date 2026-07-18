# Framebuffer Dashboard per Display Locale

Costruire un dashboard di rete che scrive direttamente sul framebuffer Linux (`/dev/fb0`) — niente X11, niente Wayland, niente SDL, niente TTY. Funziona su un Raspberry Pi con display fisico collegato (HDMI o DSI), anche in assenza di un desktop environment.

## Quando usarlo

- Hai un display fisico attaccato al Pi (es. schermo HDMI 800×480)
- Non vuoi/Non puoi installare un desktop environment (Xfce, LXDE, ecc.)
- Vuoi un dashboard sempre visibile che consuma ~25-30MB di RAM
- Il classico `setterm -blank` (console blanking) non basta perché vuoi informazioni live

## Architettura

```
netboard.py
  ├── Pillow → disegna frame in RAM (RGB 800×480)
  ├── conversione RGB→RGB565 via numpy (vettorizzata, ~200× più veloce del loop Python)
  └── write() diretto su /dev/fb0

thread pinger (ogni 8s) — parallelo su 5 peer
  └── ThreadPoolExecutor lancia tutti i ping simultaneamente

screensaver (dopo 5 min di inattività)
  └── orologio con moto Lissajous

pixel orbit (ogni 30s)
  └── sposta tutto di 1-2px (ciclo di 8 posizioni)
```

## Implementazione

### Dipendenze

```bash
# Già presenti su Raspberry Pi OS Lite / standard:
python3-pil   # Pillow Image, ImageDraw, ImageFont
python3-numpy # Per conversione RGB565 vettorizzata
```

Serve `python3-pil` e `python3-numpy`. Niente pygame, niente SDL, niente X11.

### Scrittura su framebuffer — OTTIMIZZATA

Il framebuffer Linux usa formato **RGB565** (16 bit: 5R + 6G + 5B). Pillow lavora in RGB888 (8 bit per canale).

**NON usare il loop Python pixel-by-pixel** — 800×480 = 384.000 pixel, il loop Python consuma un intero core CPU (~95% su RPi4). Usa numpy per la conversione vettorizzata:

```python
import os
import numpy
from PIL import Image

fb_fd = os.open("/dev/fb0", os.O_RDWR)

def fb_write_rgb565(fd, img):
    """Convert PIL Image (RGB) to RGB565 e scrive su fb — vettorizzato con numpy."""
    arr = numpy.array(img, dtype=numpy.uint8)          # (H, W, 3)
    r = arr[:, :, 0].astype(numpy.uint16) >> 3
    g = arr[:, :, 1].astype(numpy.uint16) >> 2
    b = arr[:, :, 2].astype(numpy.uint16) >> 3
    rgb565 = (r << 11) | (g << 5) | b
    buf = rgb565.astype('<u2').tobytes()
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, buf)
```

**Risultato**: la conversione passa da ~95% CPU a <1% CPU. Non ci sono loop Python — tutta la matematica è vettorizzata in C da numpy.

### Pinger parallelo — ThreadPoolExecutor

Pingare 5 peer in sequenza con `subprocess.run` crea 5 fork/exec a catena, occupando CPU per 5-10 secondi ogni ciclo. **Parallelizza** con ThreadPoolExecutor:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

PING_POOL = ThreadPoolExecutor(max_workers=5)

def pinger_loop():
    while True:
        futures = {}
        for s in statuses:
            future = PING_POOL.submit(ping, s.ip)
            futures[future] = s
        for future in as_completed(futures, timeout=5):
            s = futures[future]
            try:
                ok, ms = future.result()
            except Exception:
                ok, ms = False, None
            # aggiorna stato con lock...
        futures.clear()
        time.sleep(REFRESH_SEC)
```

**Risultato**: tutti i 5 ping completano in ~1-2 secondi invece di 5-10. Il thread dorme 6-7 secondi invece di girare sempre.

### Frame rate — ridotti all'essenziale

Su RPi4, frame rate alti non servono (nessun occhio umano beneficia di 8fps per una dashboard di rete). Usa frame rate rilassati:

| Modalità | Frame rate | Sleep | Note |
|---|---|---|---|
| Dashboard attivo | **1 fps** | 1.0s | Più che sufficiente per stato rete |
| Screensaver | **4 fps** | 0.25s | Movimento Lissajous fluido a 4fps |
| Screensaver ASCII | 2 fps | 0.5s | Messaggio ASCII statico |

Dimezzando il frame rate si dimezza anche il carico CPU della generazione immagine.

### Perché NON pygame/SDL

Su Pi4 con driver vc4drmfb:

| Driver | Problema |
|---|---|
| `fbcon` | Richiede un TTY attivo. Fallisce con "Unable to open a console terminal" in servizi systemd. |
| `kmsdrm` | Richiede permessi DRM e TTY. Stessi problemi in background. |
| **Pillow direct** | Nessuna dipendenza da TTY. Scrive byte su `/dev/fb0`. Funziona da qualsiasi contesto. |

### Anti burn-in

Due meccanismi indipendenti:

1. **Pixel orbit**: sposta tutto il rendering di 1-2px ogni 30 secondi in un ciclo di 8 posizioni (destra, giù, sinistra, su, ecc.). L'occhio non se ne accorge ma nessun pixel rimane sempre allo stesso colore.

2. **Screensaver**: dopo N minuti (default 5) senza cambiamenti nello stato dei peer, passa a schermo nero con un orologio che si muove su traiettoria Lissajous. Il dashboard si riaccende al primo cambio di stato.

Nota: **keyboard wake** su framebuffer puro non funziona (non c'è input subsystem). Il screensaver si risveglia solo quando un peer cambia stato.

### systemd service

Il servizio non ha bisogno di `TTYPath`, `chvt`, o `openvt`. Basta eseguire lo script:

```ini
[Unit]
Description=netboard — network status dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fausto
Group=fausto
ExecStart=/home/fausto/.hermes/scripts/netboard.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Font

Pillow ha bisogno di font TrueType. Su Raspberry Pi OS:

```python
def load_font(name, size):
    paths = [
        f"/usr/share/fonts/truetype/{name}",
        f"/usr/share/fonts/truetype/dejavu/{name}",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()
```

I font DejaVu sono preinstallati su Raspberry Pi OS.

## Ottimizzazione CPU — Riepilogo

Su RPi4, un dashboard framebuffer non ottimizzato può consumare un intero core (25% del totale). Le tre ottimizzazioni chiave:

| Ottimizzazione | Prima | Dopo | Guadagno |
|---|---|---|---|
| Conversione RGB565 | Loop Python 384K pixel/frame | numpy vettorizzato | ~95% → <1% CPU |
| Pinger | 5 ping sequenziali (5-10s) | 5 ping paralleli (1-2s) | ~60% → ~10% CPU |
| Frame rate | 2fps / 8fps | 1fps / 4fps | Carico dimezzato |

**Risultato combinato**: Load average scende da ~1.6 a ~0.75 su RPi4, il display smette di scattare.

## Verifica

```bash
# Test rapido — scrive rosso su tutto lo schermo per 3 secondi
python3 -c "
import os
import numpy
fb = os.open('/dev/fb0', os.O_RDWR)
buf = numpy.full((480, 800), 0xF800, dtype='<u2').tobytes()
os.write(fb, buf)
os.close(fb)
"

# Monitoraggio CPU in tempo reale
watch -n 1 'ps aux | grep netboard.py | grep -v grep'

# Controllo servizio
sudo systemctl status netboard.service --no-pager -l
journalctl -u netboard.service --no-pager -n 20
```

## Pitfall: display resolution sconosciuta

`fbset` mostra la risoluzione attuale. Su Pi4 con display HDMI, se non rileva l'EDID correttamente, potrebbe cadere a 640×480. Forzala in `/boot/config.txt`:

```ini
hdmi_group=2
hdmi_mode=87
hdmi_cvt=800 480 60 6 0 0 0
```

## Riferimenti

- `references/rpi-console-blanking.md` — blanking classico via setterm/consoleblank
- `scripts/netboard.py` — implementazione di riferimento in ~/.hermes/scripts/ (usa numpy + threading parallelo)