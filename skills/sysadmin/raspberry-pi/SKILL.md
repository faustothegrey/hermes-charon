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

**Soluzione definitiva** — aggiungere in `/boot/cmdline.txt`:
```
fbcon=nodeblink
```
Sulla stessa riga, separato da spazio, dove già stanno gli altri parametri kernel.

**Alternative** (effetto solo fino al prossimo riavvio):
```bash
# Disabilita il blink via sysfs
echo 0 | sudo tee /sys/class/graphics/fbcon/cursor_blink

# Disabilita il cursore sulla console corrente
setterm -cursor off
```

**Verifica**: dopo riavvio, controlla che il cursore non lampeggi più. L'impatto è puramente visivo — la rimozione via `fbcon=nodeblink` è la soluzione più pulita e permanente.

## Console blank timeout (auto screen off)

**Problema**: Il display DSI si spegne automaticamente dopo un periodo di inattività della console.

**Causa**: Il parametro kernel `consoleblank=N` in `/boot/cmdline.txt` fa spegnere la console Linux (e quindi il display DSI) dopo N secondi senza input sulla console testuale.

**Fix**:
- Per **rimuovere** lo spegnimento automatico: cancella l'intero parametro `consoleblank=N` da `/boot/cmdline.txt`
- Per **cambiare** il timeout: modifica `consoleblank=900` (15 min) nel valore desiderato, es. `consoleblank=3600` per 1 ora
- Il valore è in secondi: `900` = 15 minuti, `3600` = 1 ora

**Nota**: `consoleblank` controlla solo il blanking della console testuale Linux, non il DPMS/standby del monitor HDMI. Su display DSI collegati via DPI/RGB, `consoleblank` è l'unico meccanismo che spegne lo schermo — non c'è un screensaver separato.

**Verifica**: dopo riavvio, il display non si spegne più (se rimosso) o si spegne dopo il timeout impostato.

**Pitfall**: Non confondere `consoleblank` con la rotazione o il blink del cursore. I tre parametri in cmdline.txt sono indipendenti:
- `video=DSI-1:800x480@60,rotate=180` — rotazione display
- `fbcon=nodeblink` — cursore lampeggiante
- `consoleblank=900` — auto-spegnimento dopo inattività

## Comandi utili per diagnostica display

```bash
# Stato connessioni DRM
cat /sys/class/drm/*/status

# Modi video supportati
cat /sys/class/drm/card1-DSI-1/modes

# Log kernel relativi a display
dmesg | grep -E "(drm|vc4|kms|dsi|hdmi)"

# Elenco device DRM
ls -la /sys/class/drm/
```

## Diagnostica schermo nero su Pi

| Sintomo | Causa probabile | Fix |
|---------|----------------|-----|
| Schermo nero dopo aver toccato config.txt | `display_lcd_rotate` o `display_rotate` incompatibile con KMS | Commentare la riga, riavviare |
| DSI non rilevato | Cavo flex allentato o `display_auto_detect=1` mancante | Verificare connessione fisica, aggiungere `display_auto_detect=1` |
| HDMI non funziona | Driver non rileva hotplug | `hdmi_force_hotplug=1` in config.txt |

## Riferimenti

- Vedi `references/display-rotation-kms.md` per la discussione completa su questo fix.
