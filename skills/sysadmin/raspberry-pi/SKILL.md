---
name: raspberry-pi
category: sysadmin
description: Raspberry Pi system configuration — boot/config.txt, cmdline.txt, KMS/DRM display, DSI/HDMI tuning, GPIO overlays, and common Pi-specific pitfalls.
triggers:
  - raspberry pi
  - config.txt
  - cmdline.txt
  - display rotation
  - vc4-kms-v3d
  - DSI display
  - schermo nero
  - raspberry
  - undervoltage
  - get_throttled
  - throttled
  - weak psu
  - alimentatore
tags:
  - raspberry-pi
  - display
  - kms
  - drm
  - dsi
  - boot-config
---

# Raspberry Pi — System Configuration

## Principi generali

- `/boot/config.txt` = firmware/boot-level config (GPU/firmware controlla prima che il kernel parta)
- `/boot/cmdline.txt` = kernel command line parameters (passati al kernel Linux)
- Con driver `vc4-kms-v3d` (Kernel Mode Setting), molte impostazioni firmware in config.txt vengono **ignorate o causano conflitti** col driver kernel.
- Preferire sempre parametri kernel (`video=...` in cmdline.txt) quando si usa KMS.

## Display rotation via KMS (metodo funzionante)

**Problema**: `display_lcd_rotate=2` in `/boot/config.txt` causa schermo nero col driver `vc4-kms-v3d`.

**Causa**: Il firmware applica la rotazione a livello GPU/firmware, ma il driver KMS prende il controllo del display e non gestisce correttamente la rotazione già impostata → schermo nero.

**Fix**:
1. Commenta o rimuovi `display_lcd_rotate=2` da `/boot/config.txt`
2. Aggiungi alla fine di `/boot/cmdline.txt` (tutto sulla stessa riga, separato da spazio):
   ```
   video=DSI-1:800x480@60,rotate=180
   ```
   Per rotazione 90°: `rotate=90`, 270°: `rotate=270`
3. Riavvia: `sudo reboot`

**Verifica**: il display DSI è `card1-DSI-1` in `/sys/class/drm/`. Controlla lo stato con:
```bash
cat /sys/class/drm/card1-DSI-1/status
cat /sys/class/drm/card1-DSI-1/modes
```

## Cursor blink suppression su display DSI

**Problema**: Il display DSI mostra un cursore a blocchetto lampeggiante (tipo TTY) anche in assenza di una console attiva. Succede perché la console Linux (fbcon) è mappata sul framebuffer DSI e il kernel mostra il cursore testuale.

**Causa**: Il driver framebuffer console (fbcon) attiva il lampeggio del cursore sul dispositivo DSI quando KMS è in uso. Il blink è gestito a livello kernel, non dal firmware.

**⚠️ `fbcon=nodeblink` NON funziona su vc4-kms-v3d**: è un bug noto — il parametro kernel viene ignorato dal driver KMS. Il sysfs `/sys/class/graphics/fbcon/cursor_blink` rimane a `1` anche dopo averlo aggiunto a cmdline.txt e riavviato.

### Soluzione 1 (consigliata) — Disabilitare getty@tty1

Mascherando il servizio `getty@tty1` si elimina la console di login dal display. Il cursore scompare perché non c'è più un TTY attivo su tty1:

```bash
sudo systemctl mask getty@tty1.service
sudo systemctl stop getty@tty1.service   # effetto immediato, no reboot
```

**Vantaggio**: effetto immediato, permanente, zero effetti collaterali (l'accesso avviene via SSH/HMP, non dal display locale).

**Ripristino**:
```bash
sudo systemctl unmask getty@tty1.service
sudo systemctl start getty@tty1.service
```

### Soluzione 2 — Parametro kernel vt.global_cursor_default=0

Aggiungere a `/boot/cmdline.txt` (sulla stessa riga, separato da spazio):
```
vt.global_cursor_default=0
```
Richiede riavvio.

### Soluzione 3 — setterm (solo per la sessione corrente)

```bash
setterm -cursor off
```
L'effetto dura solo fino al prossimo riavvio o reset del TTY.

⚠️ **Pitfall**: `setterm -cursor off > /dev/tty1` può in alcuni casi **pulire lo schermo** o innescare un evento di console-blank che spegne il backlight (`bl_power=4`). Preferire le soluzioni 1 o 2 per un fix pulito.

### Soluzione 4 (robusta) — netboard.py startup fix

Quando si usa un'applicazione che scrive su `/dev/fb0` (es. netboard), la soluzione più robusta è integrare nel suo avvio:

1. Spegnere il cursore VT
2. Riaccendere il backlight (se era stato spento da consoleblank o altro)

Ecco il pattern da aggiungere nel `main()` dell'applicazione:

```python
# Spegne il cursore lampeggiante del VT
os.system("setterm -cursor off > /dev/tty1 2>/dev/null")
try:
    with open("/sys/class/graphics/fbcon/cursor_blink", "w") as f:
        f.write("0")
except Exception:
    pass
# Riaccende il backlight (consoleblank o setterm a volte lo spengono)
try:
    for d in os.listdir("/sys/class/backlight"):
        with open(f"/sys/class/backlight/{d}/bl_power", "w") as f:
            f.write("0")
except Exception:
    pass
```

### Verifica
Dopo aver mascherato getty@tty1, il display mostra solo il contenuto scritto su `/dev/fb0` (es. netboard) senza cursore lampeggiante. Il login prompt non appare più.

## Display blanking su vc4-kms-v3d (DRM DPMS)

**Problema**: Il display DSI si spegne (schermo nero, backlight acceso) dopo un periodo di inattività. Su driver vc4-kms-v3d, il blanking è gestito a livello **DRM/KMS** (DPMS = Display Power Management Signaling), NON dal kernel consoleblank.

**Diagnosi differenziale** — come capire se è consoleblank o DPMS:

```bash
# 1. consoleblank value
cat /sys/module/kernel/parameters/consoleblank

# 2. DPMS state del connettore DSI
cat /sys/class/drm/card1-DSI-1/dpms
# "On" = acceso, "Off" = blanked via DRM
```

Se `dpms = Off` ma `consoleblank = 0`, il problema è **DRM DPMS**, non consoleblank.

### 🔴 Il vero problema: DRM DPMS su vc4-kms-v3d

Il driver `vc4-kms-v3d` ha il suo proprio meccanismo di power saving che mette il connettore DSI in stato `Off` indipendentemente dal parametro `consoleblank` in cmdline.txt. **`consoleblank=0` non risolve il blanking su display DSI con KMS** — il parametro viene ignorato perché il driver DRM non lo consulta.

Lo si verifica con:
```bash
cat /proc/cmdline        # consoleblank=0 è presente
cat /sys/module/kernel/parameters/consoleblank  # mostra 900 comunque!
cat /sys/class/drm/card1-DSI-1/dpms            # mostra Off
```

### Fix immediato: FBIOBLANK ioctl

Il framebuffer device (`/dev/fb0`) espone l'ioctl `FBIOBLANK` (0x4611) che forza il riaccensione del display:

```python
import os, fcntl
FBIOBLANK = 0x4611
FB_BLANK_UNBLANK = 0
fb = os.open("/dev/fb0", os.O_RDWR)
fcntl.ioctl(fb, FBIOBLANK, FB_BLANK_UNBLANK)
os.close(fb)
```

Dopo l'ioctl, verificare:
```bash
cat /sys/class/drm/card1-DSI-1/dpms
# → "On" ✅
```

### Fix permanente: keepalive periodico in applicazione fb

L'effetto di FBIOBLANK non è permanente — il driver DRM può rispegnere il display dopo un po'. La soluzione robusta è un **keepalive periodico** (es. ogni 30 secondi) dentro l'applicazione che scrive su `/dev/fb0`:

```python
# Nel main loop dell'applicazione framebuffer
last_unblank = time.monotonic()
while running:
    now = time.monotonic()
    
    # DPMS keepalive — ogni 30 secondi sblocca il display
    if now - last_unblank > 30:
        last_unblank = now
        try:
            fb_d = os.open("/dev/fb0", os.O_RDWR)
            fcntl.ioctl(fb_d, 0x4611, 0)  # FBIOBLANK UNBLANK
            os.close(fb_d)
        except Exception:
            pass
    
    # ... resto del loop ...
```

**Non serve sudo**: `/dev/fb0` è leggibile/scrivibile dall'utente che esegue l'applicazione framebuffer.

### All'avvio dell'applicazione

Oltre al keepalive, all'avvio eseguire un unblank + riaccensione backlight:

```python
# Sblocca DPMS
try:
    fb_d = os.open("/dev/fb0", os.O_RDWR)
    fcntl.ioctl(fb_d, 0x4611, 0)
    os.close(fb_d)
except Exception:
    pass

# Riaccende backlight
try:
    for d in os.listdir("/sys/class/backlight"):
        with open(f"/sys/class/backlight/{d}/bl_power", "w") as f:
            f.write("0")
except Exception:
    pass
```

### ⚠️ Pitfall: Restart=on-failure non basta — usare Restart=always

Se l'applicazione fb ha un gestore di segnali (SIGTERM/SIGINT) che termina pulitamente il loop, `Restart=on-failure` non la riavvierà → display si spegne quando il keepalive smette di funzionare.

**Il sintomo**: display si spegne dopo un po' ma il service risulta `inactive (dead)` con `code=exited, status=0/SUCCESS` — nessun errore, solo uscita pulita. Journal mostra `=== netboard: terminato ===` senza traceback.

```bash
sudo systemctl status netboard.service
# → Active: inactive (dead) since ...  (code=exited, status=0/SUCCESS)
```

**Fix nel service file**: cambiare `Restart=on-failure` in `Restart=always`, poi daemon-reload:

```bash
sudo sed -i 's/Restart=on-failure/Restart=always/' /etc/systemd/system/netboard.service
sudo systemctl daemon-reload
sudo systemctl restart netboard.service
```

**Proteggere il loop principale** con un inner try/except, così eccezioni isolate (es. un peer irraggiungibile, un json corrotto) non terminano l'intero processo togliendo il keepalive:

```python
import traceback
from datetime import datetime

while running:
    try:
        # ... tutto il codice del loop ...
    except Exception:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] ERRORE ciclo:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        time.sleep(2)
```

Lo sleep(2) evita un loop di log rapido in caso di errore persistente, limitando il journal.
Il `traceback.print_exc()` dà lo stack trace completo, non solo il messaggio — fondamentale per diagnosi senza accesso interattivo al service.
Il timestamp ISO8601 su stderr finisce nel journal di systemd (con `journalctl -u netboard.service`).

### ⚠️ Pitfall: consoleblank=0 in cmdline.txt è inaffidabile su vc4

Il kernel ignora il parametro `consoleblank=0` su Raspberry Pi con vc4-kms-v3d. Il parametro è presente in `/proc/cmdline` ma il modulo kernel mostra ancora 900. Non fare affidamento su questo per display DSI.

### Undervoltage (alimentatore sotto-dimensionato)

Sintomo: `vcgencmd get_throttled` con bit 0/16 attivi + `measure_volts`
basso (~0.85V invece di ~1.2V) + temp normale → NON è calore, è PSU/cavo.
Il SoC throttla e la SD rischia corruzione a ogni picco di scrittura.

Mitigazione da remoto (tutte soft/revertibili, persistite in rc.local):
1. Governor `powersave` (600MHz fisso) → elimina i picchi di corrente
2. Swap su **zram** invece del file su SD (zero usura SD)
3. Dirty writeback aggressivo (1500/1000/10) → meno dati persi su crash
4. Journal systemd limitato (100M/7gg) → systemd --user è spesso il top writer SD

Ricetta completa, decode dei bit, watchdog cron e checklist di restore:
`references/undervoltage-protection.md`.

## Riferimenti

- Vedi `references/drm-dpms-blanking.md` per la discussione completa sul blanking DPMS su vc4-kms-v3d.

## Backlight management (DSI display)

Il backlight dei display DSI ufficiali Raspberry Pi è controllato via sysfs sotto `/sys/class/backlight/`.

### Status e controllo

```bash
# Identificare il controller del backlight
ls /sys/class/backlight/
# Tipicamente: 10-0045

# Leggere lo stato
cat /sys/class/backlight/10-0045/brightness      # 0-255
cat /sys/class/backlight/10-0045/max_brightness   # 255
cat /sys/class/backlight/10-0045/bl_power         # 0=acceso, 4=spento
```

### Riaccensione dopo blank

Quando il backlight viene spento da `consoleblank` o da eventi sulla console TTY, `bl_power` viene impostato a `4`. Per riaccendere:

```bash
echo 0 | sudo tee /sys/class/backlight/10-0045/bl_power
```

### Pitfall: bl_power non torna automaticamente a 0

Il kernel non riaccende automaticamente il backlight quando un'applicazione riprende a scrivere su fb0 — va reimpostato manualmente. Per questo, un'applicazione che scrive su `/dev/fb0` (es. netboard) dovrebbe forzare `bl_power=0` all'avvio.
## Diagnostica schermo nero su Pi

| Sintomo | Causa probabile | Fix |
|---------|----------------|-----|
| Schermo nero dopo aver toccato config.txt | `display_lcd_rotate` o `display_rotate` incompatibile con KMS | Commentare la riga, riavviare |
| DSI non rilevato | Cavo flex allentato o `display_auto_detect=1` mancante | Verificare connessione fisica, aggiungere `display_auto_detect=1` |
| HDMI non funziona | Driver non rileva hotplug | `hdmi_force_hotplug=1` in config.txt |
| Schermo nero dopo 15 min di inattività | `consoleblank` default 900 attivo anche senza parametro | Aggiungere `consoleblank=0` in cmdline.txt, riavviare |
| Schermo nero, dpms=Off, consoleblank=0 presente in cmdline | DRM DPMS blanking del driver vc4-kms-v3d | Usare FBIOBLANK ioctl + keepalive periodico ogni 30s |
| Schermo nero, backlight acceso, fb0 tutto zeri | Console blanking del kernel attivo | Scrivere su /dev/tty1 o chvt 2 && chvt 1 per refresh immediato |

### Comandi diagnostici display

```bash
# Valore attuale consoleblank
cat /sys/module/kernel/parameters/consoleblank

# Stato blank del framebuffer
cat /sys/class/graphics/fb0/blank

# Backlight status (0=acceso, 4=spento)
cat /sys/class/backlight/*/bl_power

# Contenuto framebuffer (se tutto 0000 -> blank attivo)
dd if=/dev/fb0 bs=1k count=1 2>/dev/null | xxd | head -5

# Forza risveglio display
echo "test" | sudo tee /dev/tty1
sudo chvt 2 && sleep 1 && sudo chvt 1

# Log kernel relativi a display
dmesg | grep -E "(drm|vc4|kms|dsi|hdmi)"

# Stato connessioni DRM
cat /sys/class/drm/*/status

# Modi video supportati
cat /sys/class/drm/card1-DSI-1/modes
```

## Python version constraints (Raspberry Pi OS)

**RPi OS Bullseye** (kernel 5.15.x) monta **Python 3.9.2** di serie. `pip3` non è sempre presente. Il sistema Debian-based non supporta upgrade di Python senza rischiare di rompere apt/systemd.

### Sintassi non disponibile su Python 3.9

| Sintassi Python 3.10+ | Equivalente Python 3.9 | Dettaglio |
|---|---|---|
| `def fn() -> dict \| None:` | `def fn() -> Optional[dict]:` | Richiede `from typing import Optional` |
| `def fn() -> str \| None:` | `def fn() -> Optional[str]:` | |
| `def fn() -> int \| None:` | `def fn() -> Optional[int]:` | stessi sintomo/errore: `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` |
| `match/case` (pattern matching) | `if/elif` chain | non usare |
| `X \| Y` in isinstance | `isinstance(x, (X, Y))` | |

### Pitfall: systemd service + Python error

Quando uno script Python usato da un **systemd service** crasha per un SyntaxError Python 3.10+, systemd entra in **restart loop**:

```
Active: activating (auto-restart) (Result: exit-code)
```

Il journal mostra il Traceback:
```bash
journalctl -u nome-service.service --no-pager -n 20
```

**Diagnosi rapida**: provare a lanciare lo script manualmente col Python di sistema per vedere l'errore prima di guardare i log. Il diff tra errore locale e errore in systemd è zero — se lo script non parte a mano, non partirà via systemd.

### Side-by-side Python (se serve)

Se un giorno servisse Python più recente (es. 3.11), installare **side-by-side** senza toccare quello di sistema:

```bash
# Da deadsnakes PPA (sperimentale su RPi)
sudo apt install python3.11 python3.11-distutils

# Oppure compilare da sorgente (lento su Pi ma sicuro)
wget https://www.python.org/ftp/python/3.11.x/Python-3.11.x.tgz
tar xzf Python-3.11.x.tgz && cd Python-3.11.x
./configure --prefix=/usr/local/python311
make -j4 && sudo make install
# Usare: /usr/local/python311/bin/python3.11
```

Il system Python (`/usr/bin/python3`) **non va mai sostituito** — è usato da apt, systemd, e tool di sistema.

## Software rendering su display DSI (NetBoard overlay)

Il display DSI ufficiale ha risoluzione **800×480 px**. La pipeline software che scrive su `/dev/fb0` (netboard) usa Pillow per disegnare testo e grafica.

### Font e dimensioni carattere

| Elemento | Font | Dimensione | Caratteri per riga (~) |
|----------|------|-----------|----------------------|
| Testo principale | DejaVuSans-Bold.ttf | **64px** | **18-20** caratteri |
| Sottotitolo | DejaVuSans.ttf | 28px | ~40 caratteri |
| Footer | DejaVuSans.ttf | 18px | ~60 caratteri |

**⚠️ Pitfall critico**: a 64px, un testo di 40+ caratteri (es. "Check In Aereo & Docs Erasmus Fausto") viene **clippato fuori dallo schermo** se messo su una riga sola. L'overlay DEVE fare word wrapping.

### Word wrapping — implementazione

Il file `~/.hermes/scripts/netboard_overlay.py` contiene la funzione `draw_overlay()` che disegna messaggi della coda prioritaria sul framebuffer.

**Pattern obbligatorio** per testi su display DSI:

1. Calcolare la larghezza disponibile: `max_w = W - MARGIN * 2` (720px con MARGIN=40)
2. Misurare ogni riga candidata con `draw.textbbox()` (PIL 10+) o `draw.textsize()` (PIL <10)
3. Fare word wrapping parola per parola con `_wrap_lines()`
4. Centrare verticalmente il blocco di N righe

```python
def _get_textsize(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)

def _wrap_lines(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        tw, _ = _get_textsize(draw, test, font)
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines if lines else [text]
```

### Messaggi ricorrenti — pattern cron

Per mostrare un messaggio sul display a intervalli regolari:

1. Creare uno script shell wrapper in `~/.hermes/scripts/` (perché il cron job esegue script, non comandi diretti in PATH):
   ```bash
   # ~/.hermes/scripts/mio-msg.sh
   #!/usr/bin/env bash
   /usr/local/bin/netboard-msg "Testo del messaggio" --priority 10 --duration 30 -s "sottotitolo"
   ```

2. Creare un cron job `no_agent=true` che esegue lo script:
   ```bash
   # Via cronjob tool: schedule="every 5 min", script="mio-msg.sh", no_agent=true
   ```

3. Verificare che il testo stia in 18-20 caratteri per riga, o fare word wrapping lato overlay.

### Verifica rapida

Prima di inviare un messaggio al display, controllare:
- **Quanto è lungo il testo?** `echo "testo" | wc -c`
- **A 64px bold DejaVu:** lunghezza_px ≈ caratteri × 38
- **800px - 80px margine = 720px** → ~19 caratteri per riga
- Se il testo è più lungo, prevedere il wrapping (il sistema lo gestisce automaticamente dalla versione con `_wrap_lines`)
- Oppure accorciare il testo per farlo stare su 1-2 righe

## Undervoltage detection & software mitigation (weak PSU)

**Symptom**: SoC throttles, system feels slow, `dmesg` floods with
`hwmon hwmon1: Undervoltage detected!`. Cause is a PSU/cable that can't
deliver enough current — NOT temperature (check temp to confirm: if
temp is sane, it's power).

### Detection

```bash
vcgencmd get_throttled   # hex bitmask
vcgencmd measure_volts   # core voltage — ~1.2V under load, ~0.85V idle is too low
vcgencmd measure_temp    # confirm heat is NOT the cause
dmesg | grep -i "undervoltage" | tail
```

`get_throttled` bit decoding (0x50005 = 0x1 + 0x4 + 0x10000 + 0x40000):

| Bit | Meaning |
|-----|---------|
| 0 | Under-voltage **NOW** |
| 1 | Arm frequency capped NOW |
| 2 | Currently throttled NOW |
| 3 | Soft temp limit NOW |
| 16 | Under-voltage has occurred (latched) |
| 17 | Freq capping has occurred (latched) |
| 18 | Throttling has occurred (latched) |
| 19 | Soft temp limit has occurred (latched) |

**Pitfall**: the "occurred" bits (16-19) stay set until reboot — a
`0x50005` long after the event does NOT mean under-voltage is happening
now. The watchdog must check bit 0 (NOW) for live alerts; report the
occurred bits as history.

**Count events per 24h** from dmesg timestamps (boot + uptime offset) —
this shows severity: 100+ events/day means the SoC throttles constantly.

### Software mitigation when you CAN'T fix the PSU physically

All reversible; run as root. Reduces current demand so the weak PSU
stops sagging:

```bash
# 1. Governor powersave → fixed 600MHz, minimal current draw
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
  echo powersave > "$c"
done

# 2. Swap OFF the SD card → zram in RAM (no SD wear, no corruption risk)
modprobe zram && echo 512M > /sys/block/zram0/disksize
mkswap /dev/zram0 && swapon /dev/zram0 && swapoff /var/swap

# 3. Aggressive dirty writeback → smaller, more frequent flush (less data
#    lost if a write is interrupted by a power sag)
sysctl -w vm.dirty_writeback_centisecs=1500 vm.dirty_expire_centisecs=1000 vm.dirty_ratio=10
```

Persist all three in `/etc/rc.local` (before `exit 0`). Back up rc.local
first. The gate is: hardware fix = official 5V/3A PSU + short thick USB
cable (26 AWG or less); software mitigation is a stopgap, not a cure.

### Undervoltage watchdog (Telegram alert)

Same no_agent cron pattern as the DSI watchdog: script reads
`get_throttled`, alerts only when bit 0 (NOW) is set, with a cooldown
state file (max 1 alert / 60 min so a persistent sag doesn't spam).
Include volts, temp, and 24h event count in the alert. Script must be
Python 3.9-safe (`Optional[int]`, not `int | None` — see Python version
constraints section). Restore the full-speed governor (`ondemand`) once
the PSU is replaced.

### DSI Bridge Crash (tc358762 timeout) — Conosciuto e non recuperabile senza reboot

**Problema**: Il bridge DSI tc358762 (chip sul Raspberry Pi 7" display ufficiale) va in timeout dopo ore di funzionamento continuo. Il display diventa nero ma backlight rimane acceso e netboard.service è attivo.

**Sintomo in dmesg:**
```
vc4_dsi fe700000.dsi: transfer interrupt wait timeout
vc4_dsi fe700000.dsi: instat: 0x00000000
[drm:vc4_dsi_host_transfer [vc4]] *ERROR* DSI transfer failed, resetting: -110
tc358762 fe700000.dsi.0: error initializing bridge (-110)
```

### 🔴 Perché il recupero senza reboot NON funziona su kernel 5.15.x

Il tentativo di unbind/rebind del bridge via sysfs fallisce perché:

1. `unbind` funziona: `echo "fe700000.dsi.0" > /sys/bus/mipi-dsi/drivers/tc358762/unbind` — rimuove il driver dal device
2. `rebind` fallisce con `-EBUSY`: l'HVS (Hardware Video Scaler, `fe400000.hvs`) è trattenuto dal DRM master, anche dopo aver fermato netboard.service. Il modulo `vc4` è built-in nel kernel (non caricabile) e le sue risorse non vengono rilasciate.
3. `modprobe -r vc4` fallisce perché il modulo è "in use" (dipendenze da cec, snd_soc_core, drm_kms_helper)

**Conclusione**: su Raspberry Pi OS Bullseye con kernel 5.15.61-v8+, l'unico recovery per un DSI bridge crashato è un **reboot completo**.

### Rilevamento automatico

Script `dsi_watchdog.py` che ogni 5 min:
1. Legge dmesg cercando errori tc358762 / DSI transfer failed
2. Se trova errori nuovi: mostra avviso sul display NetBoard (priorità 90)
3. Se non notificato nelle ultime 12h: invia Telegram

```python
# Pattern di rilevamento:
def check_dmesg():
    errors = []
    for line in subprocess.run(["dmesg"], capture_output=True, text=True).stdout.split('\n'):
        if "DSI transfer failed" in line or "transfer interrupt wait timeout" in line:
            errors.append(line)
        if "tc358762" in line and ("error" in line or "fail" in line):
            errors.append(line)
    return errors
```

Cron job:
```yaml
schedule: "every 5m"
script: "dsi_watchdog.py"
no_agent: true
deliver: local
```

Stato persistito in `~/.hermes/dsi_watchdog_state.json` per evitare notifiche duplicate.

### Tool di diagnostica e recovery

`dsi-recover` (in `/usr/local/bin/dsi-recover` → `~/.hermes/scripts/dsi-recover.py`):

```bash
sudo dsi-recover          # diagnostica + tentativo recovery
sudo dsi-recover status    # solo diagnostica
sudo dsi-recover force     # forza recovery anche senza errori recenti
```

Mostra:
- Stato netboard.service
- Connettore DSI (status, dpms)
- Backlight (bl_power)
- Errori dmesg recenti
- Se recovery automatico possibile (reboot come fallback)

### Prevenzione: ridurre freqeunza FBIOBLANK keepalive

FBIOBLANK UNBLANK ogni 30s può contribuire all'usura del bridge DSI. Ridurre la frequenza:

```python
# Anziché 30 secondi:
if now - last_unblank > 120:  # ogni 2 minuti
    ...
```

## Riferimenti
