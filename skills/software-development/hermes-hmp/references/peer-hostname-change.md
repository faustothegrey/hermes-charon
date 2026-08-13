# Peer hostname change (safe procedure) — trixie → Diet, 2026-08-13

## When
User asks to rename a peer on the LAN (non-Hermes device: pi.dev / DietPi / any Linux box).

## Safe procedure (Debian 13, systemd)
1. Verify access: `ssh -o ConnectTimeout=6 -o BatchMode=yes <user>@<ip> 'hostname; hostnamectl status | head -4'`
2. Check passwordless sudo FIRST: `sudo -n true && echo OK` — abort if it prompts for a password
   (a background script cannot answer a sudo prompt).
3. Apply: `sudo -n hostnamectl set-hostname <NewName>`
   systemd → NO service restart needed. HMP/pi.dev bind 0.0.0.0, unaffected.
4. Keep the old name as alias in /etc/hosts:
   `sudo -n sed -i 's/^127\.0\.1\.1.*/127.0.1.1 <NewName> <OldName>/' /etc/hosts`
5. Verify: `hostname` shows new name AND listeners still bound:
   `ss -tln | grep -E ':18643|:18644'` (count > 0).
6. Reversible: `sudo hostnamectl set-hostname <OldName>` + revert /etc/hosts.

## FRITZ!Box DNS caveats
- Old name stays in DNS until the DHCP lease renews; new name appears only after reconnect.
- After rename the old name's IPv4 record can decay: `getent hosts <oldname>` then resolves
  ONLY via IPv6 (fd00::...) while the IPv4 entry is gone. Expected, not a fault.
- HMP peer identity (peer id, e.g. "trixie") is INDEPENDENT of hostname — the mesh keeps
  working unchanged. Only documentation (skill peer tables) needs a manual touch.

## Environment quirks observed (2026-08-13)
- SSH banner-exchange timeout on a loaded RPi 3B+ (pi.dev) is normal — retry; the machine is up.
- Machines on this LAN go flaky in groups (peer106 AND trixie unreachable in the same ~07:45
  window, peer138 unaffected). Always pair a remote change with an idempotent wait-for-up
  script — see SKILL.md section "Flaky/offline peers — idempotent wait-and-deliver pattern".
