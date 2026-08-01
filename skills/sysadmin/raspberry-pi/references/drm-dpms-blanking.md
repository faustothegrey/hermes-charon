# DRM DPMS Blanking su vc4-kms-v3d

## Scoperta

**Data**: 2026-07-18
**Contesto**: Display DSI su Raspberry Pi, driver `vc4-kms-v3d`, applicazione netboard.py che scrive su `/dev/fb0`.

Il display si spegneva dopo periodi di inattività nonostante:
- `consoleblank=0` presente in `/boot/cmdline.txt` e in `/proc/cmdline`
- `fbcon=nodeblink` presente
- Applicazione che aggiornava il framebuffer continuamente

## Diagnosi

```bash
cat /proc/cmdline  # consoleblank=0 presente ✅
cat /sys/module/kernel/parameters/consoleblank  # 900 ❌ il parametro è ignorato!
cat /sys/class/drm/card1-DSI-1/dpms            # Off ❌ il display è in DPMS sleep
```

Solo il connettore DSI era in DPMS Off:
```bash
/sys/devices/platform/gpu/drm/card1/card1-DSI-1/dpms = Off     # ❌
/sys/devices/platform/gpu/drm/card1/card1-HDMI-A-1/dpms = On   # ✅
/sys/devices/platform/gpu/drm/card1/card1-HDMI-A-2/dpms = On   # ✅
```

## Tool investigati (non funzionanti)

| Tool | Risultato | Motivo |
|------|-----------|--------|
| `tvservice -s` | "tvservice is not supported when using the vc4-kms-v3d driver" | Deprecato |
| `vcgencmd display_power` | restituisce -1 | Incompatibile KMS |
| `setterm --blank 0` | "terminal does not support --blank" | Solo su TTY reali |
| `xset q` | "xset non disponibile" | Nessun X server |
| `echo "On" > /sys/class/drm/card1-DSI-1/dpms` | Permission denied | Non scrivibile |

## Soluzione: FBIOBLANK ioctl

L'ioctl `FBIOBLANK` (0x4611) sul dispositivo `/dev/fb0` forza il riaccensione del display DRM:

```python
import os, fcntl
fb = os.open("/dev/fb0", os.O_RDWR)
fcntl.ioctl(fb, 0x4611, 0)  # FBIOBLANK, FB_BLANK_UNBLANK
os.close(fb)
```

L'effetto è immediato: `dpms` torna a `On` senza permessi speciali (l'utente che apre il fb device ha già i permessi).

## Pattern finale

Il fix definitivo è un keepalive periodico (ogni 30 secondi) nell'applicazione che scrive sul framebuffer. Vedi SKILL.md sezione "Display blanking su vc4-kms-v3d (DRM DPMS)" per l'implementazione completa.

## Lezioni\n\n1. **`consoleblank=0` non funziona su vc4-kms-v3d** — il kernel ignora il parametro.\n2. **DPMS blanking è separato da consoleblank** — gestito dal driver DRM, non dal kernel scheduler.\n3. **FBIOBLANK è l'unica via** — l'ioctl standard del framebuffer funziona su tutti i driver KMS.\n4. **Keepalive necessario** — l'unblank non è persistente, va ripetuto ogni ~30 secondi.\n5. **Il service systemd DEVE avere Restart=always, non on-failure** — l'applicazione fb con gestore SIGTERM esce pulitamente (exit 0) e `Restart=on-failure` non riparte. Il display si spegne quando il keepalive smette. Vedi SKILL.md sezione apposita.
