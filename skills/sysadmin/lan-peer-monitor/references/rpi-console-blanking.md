# RPi Console Blanking

Prevent burn-in on a physical display connected to a headless Raspberry Pi running a TTY console (bash login screen). The display blanks after N minutes of inactivity.

## Method: `setterm` + `rc.local` (preferred)

**Immediate effect** (no reboot needed):
```bash
sudo /usr/bin/setterm -blank 15 >/dev/tty1 </dev/tty1 2>/dev/null
```

**Persist across reboots** via `/etc/rc.local`:
```bash
# /etc/rc.local — add before exit 0:
/usr/bin/setterm -blank 15 >/dev/tty1 </dev/tty1 2>/dev/null || true
```
Value is in **minutes**. `15` = 15 minutes.

## Method: `consoleblank` kernel parameter (requires reboot)

Add `consoleblank=900` to `/boot/cmdline.txt` (value in **seconds**, so 900 = 15 min):

```bash
sudo sed -i 's/$/ consoleblank=900/' /boot/cmdline.txt
```

Takes effect on next boot. The live `/sys/module/kernel/parameters/consoleblank` may still show `0` even with the kernel param — it only updates after reboot.

## Verification

Check that blanking is active:
```bash
cat /sys/module/kernel/parameters/consoleblank
# Should show the timeout in seconds (0 = disabled)
```
