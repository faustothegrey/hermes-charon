# ARM SBC Disk Expansion (LVM+XFS on undersized partition)

Recover unallocated space on ARM single-board computers (Cortex-A53, Raspberry Pi clones, Pine64, etc.) where the root partition was created too small.

## When to Use

- You SSH into an ARM SBC and find the root filesystem is only ~5-6GB despite the microSD being 32-64GB
- `lsblk` shows 50+ GB unallocated after the last partition
- The OS is an older Fedora release (30, 31, 32) that you can't upgrade because newer distros lack aarch64 support for this hardware revision
- Filesystem is XFS on top of LVM, using MBR partition table

## The Root Cause

Many ARM SBC images use a minimal partition layout:

```
mmcblk0: 59.6G
├─p1: 200M /boot/efi (FAT16)
├─p2: 1G   /boot (ext4)
├─p3: 5.8G LVM → /  ← too small!
└─ ~52GB UNALLOCATED
```

The installer creates a small LVM PV with just enough space for the OS root, leaving the rest of the SD card completely unused.

## Expansion Steps

### 1. Check the layout

```bash
lsblk
fdisk -l /dev/mmcblk0
df -h /
```

### 2. Resize partition 3 with parted

```bash
parted /dev/mmcblk0 resizepart 3 100%
```

This resizes the partition to fill the rest of the disk. With `msdos` (MBR) partition table this works **online** — no reboot needed.

### 3. Resize the LVM physical volume

```bash
pvresize /dev/mmcblk0p3
```

### 4. Extend the LV and filesystem

```bash
lvextend -r -l +100%FREE /dev/fedora/root
```

The `-r` flag auto-grows the XFS filesystem (calls `xfs_growfs` internally).

### 5. Verify

```bash
df -h /
```

Before: `5.8G  4.6G  1.3G  79% /`
After:  `59G   4.6G   54G   8% /`

## Identity Check

Both peers share the **same LVM VG UUID** (`p3WSpe-92fY-WTAg-Ve4l-Ahkj-0xd7-iRRug5`) and the **same root FS UUID** (`241125d4-8661-44ab-91ae-d90c4c5f6edb`). This is because they were cloned from the same disk image. The expansion process works identically on both.

## Pitfalls

- **Don't try `resize2fs` on XFS** — XFS can only grow, not shrink, and must use `xfs_growfs` (which `lvextend -r` calls automatically). Never use `resize2fs` on an XFS partition.
- **Partition table must be msdos (MBR)** — the `resizepart` syntax above works for MBR. For GPT, use `parted /dev/mmcblk0 resizepart 3 100%` but verify the partition number.
- **Online resize** — `parted resizepart` works on live root partitions because LVM handles the device-mapper layer. The kernel sees the new partition size immediately via `partx`.
- **Old Fedora quirks** — Fedora 30 aarch64 has no `growpart` command, and `dnf`/`yum` may be completely non-functional due to EOL repos and high load. Don't rely on package manager for this operation.
- **No reboot needed** — the entire procedure is live. Verify immediately with `df -h`.