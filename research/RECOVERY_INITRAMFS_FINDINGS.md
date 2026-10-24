# Embedded early-userspace recovery boundary

Observed October 24, 2026, offline in the checked shared update. The Linux-bearing payload inside `seret.bin` contains another valid XZ stream with a complete early-userspace archive. This narrows recovery investigation to a concrete updater and startup files. It does not qualify booting that recovery, restoring the TV or retaining it in the replacement.

## Structure and independent check

The parent decoded payload is 4,952,320 bytes, SHA-256 `a60e1b13bd45c952647427d15799d01d72bde6fdc531a9205a574f1d3ad76e51`. At **parent-file offset 4,279,572**, a complete 468,796-byte XZ stream passes CRC32 and decodes to 1,171,968 bytes, SHA-256 `a99d9c5faa39edc307c589f4e5e0663e209fbff4fa7652234f803aaf0d9accb3`. Another XZ marker is invalid. These are decoded-file coordinates, never device memory or flash addresses.

The decoded stream has 272 newc members, a complete trailer and only zero bytes afterward. The separately written parser checks syntax, boundaries, alignment, types, link counts, uniqueness and budgets. Host `bsdcpio 3.5.3` / `libarchive 3.5.3` independently lists the archive and agrees on all 272 normalized names. Neither reader extracts a filesystem or creates device nodes. The 97 block-device and 24 character-device entries are archive records, **not observed physical devices or a live storage map**.

[Linux's primary format documentation](https://www.kernel.org/doc/html/v5.4/driver-api/early-userspace/buffer-format.html) defines newc headers, alignment, trailers and hard links. This inspector deliberately supports a narrower subset: one archive with a trailer, no concatenation, zero checksum field and no hardlinked nondirectories. Refusal does not mean Linux cannot load another form. [Early-userspace documentation](https://www.kernel.org/doc/html/v5.4/driver-api/early-userspace/early_userspace_support.html) describes linking such an archive into a kernel to supply `/init`. Format correspondence does not prove this payload's boot path runs.

The [inventory](recovery-initramfs-inventory.json) binds parent/stream/member hashes, reader comparison and primary references. Raw archive listings, scripts and program bytes remain private.

## Startup boundary

| Member | Static observation | Limit |
| --- | --- | --- |
| `/init`, `/bin/sh` | Symlink data names `/bin/toybox`, including a stored terminating NUL. | Not an observed exec or proof of applet behavior. |
| `/bin/toybox` | 987,396-byte file with an ELF32 little-endian ARM header. | Filename/header do not establish upstream provenance or configuration. |
| `/etc/inittab` | A sysinit entry names `/etc/init.d/rcS`. | Actual init interpretation and reachability are unverified. |
| `/etc/init.d/rcS` | A standalone `upgrade_mgr` command accompanies proc/sysfs mount commands. | Script observation only; it has not been run. |
| `/bin/upgrade_mgr` | 149,124-byte file with an ELF32 little-endian ARM header. | Side effects and restore behavior are not qualified. |

This updater-bearing candidate must not be treated as a passive rescue shell. Its accepted boot route, prerequisites, installed-unit correspondence and relevant side effects remain unknown. No diagnostic, RAM boot or recovery trial on the household TV follows from finding these files. An independent kernel trial cannot use this image as its sole recovery proof.

The owner requires independent replacement of recovery copies too. Retaining or repackaging this vendor payload would fail that requirement. The archive supplies research material, not a released replacement component.

## Updater storage-write trace

Pinned REA/Ghidra static analysis identifies a storage routine at analysis coordinate `0x1a444`. Its inferred boot-storage branch opens `/dev/mmcblk0boot0` and its `force_ro` attribute, requests removal of read-only protection, writes data and later attempts to restore that protection. Error paths differ; successful restoration must not be assumed. The other storage branch and complete startup/partition-selection behavior remain unresolved. No path was opened on the TV.

Three direct Thumb BLX calls in that routine, at `0x1a512`, `0x1a53c` and `0x1a59a`, independently map through the original ELF headers and decode to `0x20fdc`. These are analysis coordinates in this exact ELF, never physical addresses or flash offsets. The existing call checker reproduces their mappings, four-byte hashes and destinations. Ghidra's wrapper analysis shows syscall number four passed through a thunk to an ARM supervisor-call sequence. The primary [ARM syscall table](https://github.com/torvalds/linux/blob/v5.4/arch/arm/tools/syscall.tbl) assigns four to `write`; [ARM entry source](https://github.com/torvalds/linux/blob/v5.4/arch/arm/kernel/entry-common.S) documents EABI syscall-number handling. These corroborate the interpretation, not the target's installed kernel identity.

Direct instruction checks establish calls; the storage/protection sequence remains static inference, not successful execution or a complete effect inventory. Ghidra could not associate one write-error string reference with an enclosing function; no boundary was invented to conceal that gap. The native session closed with no pending cleanup and unchanged input hash. Raw reports and vendor code stay private. This updater is not qualified as a read-only diagnostic or independent recovery route.

## Reproduce and challenge

```sh
python3 tools/inspect_recovery_initramfs.py --file PRIVATE_DECODED_SERET_LINUX \
  --output .local/recovery-initramfs-review.json
python3 -m unittest tests.test_recovery_initramfs -v
```

Input, candidates, decoder memory, individual/aggregate expansion, members and names are bounded. Output includes counts and metadata for a fixed path allowlist. Unknown paths, symlink targets, script contents and payload bytes are omitted. The inspector does not extract, follow links, mount, execute, sign, modify images or access the TV. Hashes/compression checks establish byte consistency, not authenticity, authorship, boot authority or recovery.
