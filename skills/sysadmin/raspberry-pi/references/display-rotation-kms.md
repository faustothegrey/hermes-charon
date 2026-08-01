# Display DSI Rotation + Blink Fix — Full Discussion

## Contesto

Raspberry Pi 4 con display DSI ufficiale 800×480, driver `vc4-kms-v3d` (KMS attivo).
Sistema: Debian Bullseye, kernel 5.15.61-v8+.

## Problema: schermo nero dopo display_lcd_rotate

### Sintomo

Impostando `display_lcd_rotate=2` in `/boot/config.txt` per ruotare il display DSI di 180°,
allo schermo nero. Il display è acceso (retroilluminazione presente) ma non mostra nulla.

### Diagnosi

Il parametro `display_lcd_rotate` è gestito dal **firmware GPU** (prima che il kernel parta).
Con `dtoverlay=vc4-kms-v3d` attivo, il driver KMS prende il controllo del display dopo
il boot. La rotazione già applicata dal firmware non è gestita correttamente dal driver
KMS → conflitto → schermo nero.

### Soluzione

Usare il parametro kernel `video=` in `/boot/cmdline.txt` invece di `display_lcd_rotate`
in config.txt:

```
video=DSI-1:800x480@60,rotate=180
```

Il formato è: `video=<connector>:<width>x<height>@<refresh>[,rotate=<deg>]`

- `DSI-1` è il nome del connector DRM (verificabile in `/sys/class/drm/`)
- rotate=180 per rotazione di 180°
- Altri valori: rotate=90, rotate=270

Non serve nessun altro parametro in `/boot/config.txt` per la rotazione.

## Problema: cursore lampeggiante (blink)

### Sintomo

Un cursore a blocchetto lampeggia sul display DSI anche quando il sistema è in esecuzione
e un'applicazione scrive su `/dev/fb0`.

### Diagnosi

La console Linux (fbcon) è mappata su tty1 che è attiva sul display DSI.
Il lampeggio del cursore è gestito dal kernel.

### Tentativo fallito: fbcon=nodeblink

Aggiungere `fbcon=nodeblink` a `/boot/cmdline.txt` **non funziona** con vc4-kms-v3d.
È un bug noto del driver: il sysfs `/sys/class/graphics/fbcon/cursor_blink` rimane a `1`
anche dopo riavvio col parametro.

### Soluzione adottata: maskare getty@tty1

```bash
sudo systemctl mask getty@tty1.service
sudo systemctl stop getty@tty1.service   # effetto immediato
```

Il cursore scompare all'istante perché non c'è più una console di login attiva su tty1.
L'accesso al sistema avviene via SSH/HMP, non serve la console locale.

### Alternativa: vt.global_cursor_default=0

Aggiungere `vt.global_cursor_default=0` in cmdline.txt. Richiede riavvio.
Funziona a livello kernel VT, indipendentemente da fbcon.

## Ricapitolo: cmdline.txt finale

```
console=serial0,115200 console=tty1 root=PARTUUID=xxx rootfstype=ext4 fsck.repair=yes rootwait
video=DSI-1:800x480@60,rotate=180
vt.global_cursor_default=0
```

Nota: `fbcon=nodeblink` è stato rimosso perché inefficace.
`consoleblank=900` è stato rimosso per evitare lo spegnimento automatico del display
mentre netboard è attivo (il kernel non considera gli aggiornamenti fb0 come "attività").

## Riferimenti incrociati

- Salvato anche in: Holographic Memory (fact_store, entity_resolution)
- Salvato anche in: Obsidian vault → `peer70 Health/2026-07-18.md`
