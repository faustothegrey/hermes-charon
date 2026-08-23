# FRITZ!Box SMB / NAS Access (FRITZ.NAS)

Session 2026-08-23: reachability + credential auth against 192.168.178.1, goal was
file-sharing with peer128.

## Identify a FRITZ!Box vs a standalone NAS by port signature

Probe ports; the combination is diagnostic:

| Port | Meaning on 192.168.178.1 |
|------|--------------------------|
| 445  | SMB — OPEN (FritzBox NAS) |
| 139  | NetBIOS — OPEN |
| 80   | router web UI — OPEN |
| 49000| TR-064 router API — OPEN ← the give-away it's an AVM FRITZ!Box |
| 22   | SSH — closed (no SSH on a FritzBox) |
| 5000/5001 | closed (those are Synology DSM) |

192.168.178.1 + TR-064(49000) + web UI on 80 → it's the router, not a standalone
NAS. The "NAS" is the router's built-in USB/SMB storage.

Anonymous/guest share listing is refused (`PermissionError` / NT_STATUS_ACCESS_DENIED).
Credentials = the router user (same fausto / ccll4372 used for data.lua / TR-064), not a
separate NAS login. If the user gives you router creds, reuse them for SMB.

## Enumerate shares — smbclient CLI (RELIABLE)

```bash
# install if missing (non-root user needs sudo; apt lock errors → use sudo -n)
sudo apt-get install -y smbclient

# list shares
smbclient -L //192.168.178.1 -U 'fausto%ccll4372'
#   → FRITZ.NAS   Disk   FRITZ!Box     (share name is UPPERCASE)

# list a share's contents
smbclient //192.168.178.1/FRITZ.NAS -U 'fausto%ccll4372' -c 'ls'
```

## Write access — CONFIRMED (read + write + delete)

Same credentials give full RW/delete on FRITZ.NAS. Verified recipe (put → ls → del):

```bash
echo "write-test $(date)" > /tmp/wtest.txt
smbclient //192.168.178.1/FRITZ.NAS -U 'fausto%ccll4372' \
  -c 'put /tmp/wtest.txt .wtest.txt; ls .wtest.txt; del .wtest.txt'
```

Upload is slow (~1.4 kb/s on the small stick) but works. Use `-c 'del <name>'` to
clean up test files. FRITZ.NAS is a usable drop-point between peers; the box also
has its own `.ssh/` on it, so be careful not to overwrite anything there.

Example listing showed: Software/, _OLDER/, .ssh/ dirs + stray files (.DS_Store, a stray .jpg).

**Free space trap:** `ls` prints blocks, NOT GB. "103936 blocks of size 4096. 92112
blocks available" = total ~425 MB, free ~360 MB. It's a small USB stick, not a big
NAS volume. Don't misread blocks×4096 as GB — good for passing files, not bulk storage.

## Mounting (client side) — VERIFIED CIFS automount

This box (peer70 RPi) has the CIFS client stack: `cifs-utils` → `/usr/sbin/mount.cifs`,
kernel module `cifs.ko` loads (`modprobe -n -v cifs` shows it). Server side
(`samba`/`smbd`) is NOT installed here — only install it if this box must SERVE a
share to peers.

### Recipe: mount a FRITZ.NAS subdir onto a local dir (RW, automount)

```bash
# 1. credentials file (password NEVER in fstab)
printf 'username=fausto\npassword=ccll4372\n' > ~/.smbcredentials
chmod 600 ~/.smbcredentials

# 2. one-off mount (uid/gid 1000 = fausto; mount the SUBPATH to bind one folder)
sudo mount -t cifs //192.168.178.1/FRITZ.NAS/Software ~/Software \
  -o credentials=/home/fausto/.smbcredentials,uid=1000,gid=1000,iocharset=utf8,noperm

# 3. persist in fstab (automount = lazy, no boot hang if NAS is off)
echo '//192.168.178.1/FRITZ.NAS/Software /home/fausto/Software cifs credentials=/home/fausto/.smbcredentials,uid=1000,gid=1000,iocharset=utf8,noperm,nofail,x-systemd.automount,noauto 0 0' \
  | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
```

### Verify the automount lifecycle (do this after every fstab edit)

```bash
sudo systemctl start home-fausto-Software.automount   # unit name = escaped path
systemctl is-active home-fausto-Software.automount    # → active
ls /home/fausto/Software/                             # access triggers the mount
sleep 2 && df -h /home/fausto/Software                # → shows the CIFS share
```

The automount unit only engages ON ACCESS — `systemctl list-automounts` can show
nothing before it is started, so don't read "none shown" as failure. Reboot-proof
check: `stop` the automount+mount units → `df` shows local root → `start` automount →
`ls` → `df` shows CIFS again.

### PITFALL: "target is busy" on umount

A CIFS mount can't be `umount`ed while any shell has its cwd inside it (a prior
`cd ~/Software` blocks it). `fuser -v` / `lsof +D` reveal the offender; use
`sudo umount -l` (lazy) to detach immediately.

### Measured speeds (small USB stick inside the router)

Write ~1.6 MB/s, read ~5.8 MB/s (10 MB file). The tiny-file "1.4 kb/s" figure was
protocol overhead, not a real limit — benchmark with a real-size file, never a
44-byte probe.

### macOS junk on the share

The share carries AppleDouble/`.DS_Store` files (`.DS_Store`, `._<name>`). Harmless;
leave them or clean with `find <dir> -name '._*' -o -name '.DS_Store'`.

## PITFALL: kernel CIFS mount goes STALE on many small files (bulk copy)

The CIFS kernel mount (`mount -t cifs`) works for small RW ops but goes stale under
bulk reads: `cp -a` over a tree with many small files / .git objects spams
`Stale file handle`, and even `cat`/`md5sum` of source files eventually fails with
`No such file or directory` / hangs. This happened after automount stop/start cycles
and is aggravated by the FRITZ!Box SMB server. Remounting (`sudo umount -l` then
`mount ... vers=3.0,cache=none`) clears it temporarily but it recurs.

**Robust bulk-copy recipe — bypass the kernel mount, use smbclient tar mode:**

```bash
# server-side recursive pull of a whole tree into a tar, then extract locally
smbclient //192.168.178.1/FRITZ.NAS -U 'fausto%ccll4372' -Tc /tmp/tree.tar 'Software/scripts-ai'
mkdir -p /home/fausto/scripts-ai
tar -xf /tmp/tree.tar -C /home/fausto/scripts-ai --strip-components=N
```

smbclient tar reads straight from the server (no kernel CIFS), so it survives where
the mount fails. **Note the tar path prefix:** entries look like `./Software/scripts-ai/...`
(leading `./`), so count the components carefully:
- `--strip-components=2` → leaves `scripts-ai/` under the dest
- `--strip-components=3` → puts the tree's contents directly in the dest

Verify with `find ... -type f | wc -l` (counts must match source) + `md5sum` of a few
files pulled via `smbclient ... -c 'get <path> <local>'` — NOT via the stale mount.

`python3-smbc` 1.0.23 on this RPi is a trap for enumeration:

- The API method `set_auth_data_fn` does NOT exist — this version uses the
  **`functionAuthData` attribute** (`c.functionAuthData = cb`).
- Callback signature: `def auth(srv, shr, wg, un): return (workgroup, user, password)`.
- `c.debug` is an int attribute in this lib, not a method; `optionDebugToStderr` takes
  a bool.
- **Even with correct credentials** it returns `SystemError PermissionError` /
  `NT_STATUS_WRONG_CREDENTIAL_HANDLE` / "attempted logon is invalid" — while
  `smbclient` authenticates fine with the same user/pass on both ports 445 and 139.

Lesson: **prefer `smbclient` CLI for SMB auth/enumeration on this box.** Don't burn
time fighting the Python wrapper's auth layer; its SPNEGO/NTLMSSP handling vs the
FritzBox is unreliable. Use python3-smbc only if you're sure the creds were already
rejected by the server, not by the wrapper.
