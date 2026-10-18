# Public-update decryption and bounded device-tree inspection

Observed 2026-10-18. This is an offline result from the shared official update, not an owner-unit dump. No vendor inquiry, TV connection, payload execution, mount or device write occurred. Raw references, public update-key profiles and decrypted vendor bytes remain private and untracked; no provider DRM material was used.

## What changed

The earlier [legacy compatibility check](FIRMWARE_AND_BOOT_FINDINGS.md) covered ten profiles from an older decryptor and found no accepted metadata. That bounded negative result did not rule out newer profiles or a different cipher path. The pinned [unixtract reference](https://github.com/theubusu/unixtract/tree/144cf51e3e1b6e832119fde60f676a6def8266f7) includes a published 2025 profile and an AES-256 path using the first 16 bytes of SHA-256 of the salt as the IV. The format implementation also handles a 256-byte signature preceding the Tizen 1.9 metadata tree.

An independent bounded checker tried its 17 MSD11 profiles against only the retained update's metadata envelope. Exactly one, named PontusM 2025, produced both valid PKCS7 padding and the expected Tizen 1.9 marker. The metadata is 4,027 bytes. Every parsed descriptor fits its parent, the descriptor counts end exactly at EOF, and all nine item IDs match the previously inspected outer table.

The complete public archive SHA-256 and streamed upgrade-member SHA-256 were recomputed and match the earlier inventory. All nine sections then decrypted with valid padding and matched their declared plaintext size and CRC32. The large platform image was streamed for digest/CRC verification without retaining its plaintext; only the kernel, DTB bundle and DDR initialization were retained privately for bounded static inspection.

This establishes a reproducible update-container analysis route without outreach. CRCs, known structure and decryption do **not** authenticate Samsung's signatures or establish boot-image acceptance.

## Recovered package declarations

The metadata group names T-PTMFAKUC-0090, version 1301.0, device type Common. These are package declarations, not measurements of installed storage.

| Item ID | Name | Plaintext bytes |
| --- | --- | ---: |
| 1001 | platform.img | 1,430,257,664 |
| 1002 | uImage | 10,472,704 |
| 1003 | secos.bin | 8,380,416 |
| 1004 | factory_peq.img | 7,667,712 |
| 1005 | seret.bin | 3,661,824 |
| 1006 | secos_drv.bin | 3,137,536 |
| 1007 | dtb.bin | 1,564,672 |
| 1008 | ddr.init | 55,808 |
| 1009 | sign.bin | 1,024 |

The [bounded evidence inventory](decrypted-update-inventory.json) binds each section to the public archive by IDs, file ranges, sizes, hashes and consistency results. These ranges are **update-file offsets**, not flash addresses, writable partitions or a restore recipe. Presence of an item name does not identify its execution stage or authorship.

## Kernel and DTB findings

The recovered kernel has a valid legacy uImage header, matching header/data CRCs, the name Linux-5.4.261 and the format's ARM/Linux/kernel identifiers. Its declared data is 10,369,948 bytes. The remaining 102,692 bytes are not interpreted as a signature, partition or boot stage. The header's load/entry values are deliberately omitted from the public inventory. A valid legacy header does not establish that the TV accepts a replacement image.

The DTB bundle contains twelve nonoverlapping, structurally parsed FDTs. Each declares `samsung,dtv` and `samsung,sdp-pontusm`, and four CPU-compatible nodes containing `arm,cortex-a57` and `arm,armv8`. These are device-tree declarations; do not promote them to a measured Cortex-A57 silicon identity, assume AArch64 boot support, or infer the installed variant. They do strengthen the correspondence between this update and the family source's PontusM machine support. An ARMv7 kernel/interface report is not inconsistent with ARMv8-capable hardware running a 32-bit software stack.

The official source archive’s kernel Makefile also declares version 5.4.261, matching both the update’s uImage name and its embedded Linux-version string. The inventory binds that Makefile and PontusM board source by hashes. This establishes a matching version declaration, not an exact build: the executing configuration, toolchain, patch equivalence and selected DTB are not yet established. A bounded scan of the recovered kernel found no `IKCFG_ST` marker; this does not prove that no configuration can be recovered by another method. Build-host/user/compiler strings are not exported.

The exact variant-selection mechanism, executing board/revision, ROM trust policy, earlier boot stages and independent restore route remain unresolved. Neither the catalog's chip names, the source's Cortex-A15 configuration symbol nor another device's benchmark can replace those observations.

## Platform-image wrapper

A retained 2 MiB prefix contains a GPT with valid primary-header and partition-entry-array CRCs. It declares two image partitions: `pltf_t.img` starts at byte 1,048,576 and spans 1,369,440,256 bytes; `prd_t.img` starts at byte 1,370,488,832 and spans 58,720,256 bytes. These are ranges **inside the update image**, not the live TV partition map. GUIDs are omitted and the backup GPT has not been checked.

The first partition starts with `VDFS`. Static comparison with `vdfs-tools.opensource.tgz` from the retained official `25_DTV_PontusM.zip` identifies layout `2007`. The published layout, flush and CRC sources define six 512-byte headers plus primary/copy extended superblocks. Every header CRC and both extended-header CRCs match, the extended-checksum references match, and primary/copy superblocks are equal. The source uses the reflected CRC32 polynomial with initial zero and no final complement, distinct from the usual ZIP CRC convention.

The superblock declares a read-only image, 4,096-byte blocks, 16,384-byte metadata nodes, 334,114 volume blocks and signature-type ID 1 (the source enum names RSA1024). This verifies fixed-header consistency only: no signature authentication, catalog traversal, complete filesystem validation or mount occurred. Builder command/identity, UUID and signature bytes are excluded. The source-reference hashes are recorded in the inventory; no reference implementation was executed or copied into the product.

## Reproduce bounded plaintext inspection

The public inspector contains no decryption keys, network/device/subprocess calls, source execution, extraction, mounting or installer. It takes **already decrypted private files**. The pinned reference identifies the public format/profile provenance; its implementation was read, not executed. The private compatibility checker independently applied the published cipher recipe; no upstream implementation was incorporated into the MIT product.

```sh
python3 tools/inspect_update_metadata.py \
  --metadata PRIVATE_METADATA_FILE \
  --dtb PRIVATE_DTB_BUNDLE \
  --kernel PRIVATE_KERNEL_IMAGE \
  --platform-prefix PRIVATE_PLATFORM_PREFIX \
  --output .local/update-metadata-review.json
```

The tool bounds input sizes, descriptor counts/ranges, node depth, properties, strings, reservation blocks and image CRCs. It refuses nonregular/link inputs and output aliases of inputs. It reports selected model/compatible strings and counts only; it excludes raw salts, keys, signatures, address values and unrelated device-tree properties. Synthetic tests cover truncation, overflow, unsafe names, duplicate IDs/properties, overlapping blocks, excessive nesting, CRC damage, GPT range/overlap constraints, VDFS fixed-header corruption and preservation of input files. This tool does not reproduce decryption or all-section CRC checking; those separate results are recorded with their input/reference provenance.

## Consequence for the implementation plan

Firmware encryption is no longer the immediate offline-analysis blocker for this update. Continue from the recovered kernel/device-tree declarations and identifiable software domains to exact source/build correspondence, variant selection and boot/secure-world dependency analysis. Do not substitute another UI feature or a vendor email for that work.

No independent boot, complete Samsung-software removal, recovery, protected-media eligibility or household installation is qualified. The next hardware proposal still needs exact-unit evidence and matching-lab recovery; update decryption does not relax those gates.
