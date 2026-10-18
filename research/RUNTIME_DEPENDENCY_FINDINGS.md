# Recovered filesystem and protected-media dependency findings

Observed 2026-10-18. These are offline facts from the official shared update, not observations of the household TV. No TV connection, mount, vendor-code execution, third-party message or hardware write occurred. Raw vendor files and catalog contents remain private. No provider key/provisioning file was opened for this investigation.

## What is now established

The earlier [fixed-header inspection](DECRYPTED_UPDATE_FINDINGS.md) is extended by two bounded, independently written inspectors. The [inventory](runtime-dependency-inventory.json) binds their results to the previously checked archive/member and published format-source hashes. The GPL format sources were read to understand the data structures; no upstream implementation was copied into the product or executed.

The platform VDFS snapshot table passes its CRC and the superblock checksum reference. All 3,083 declared catalog nodes pass CRC and snapshot-version checks. Translation and record ranges fit their bounds; the index graph reaches every non-head node exactly once, all leaves have the declared height, and sibling links are reciprocal. There are 22 index nodes, 3,060 leaf nodes and 166,831 leaf records across folder, file, hard-link and inverse-link record types. These record counts are not unique file counts. Arbitrary catalog names, values and file extents are not exported.

Two selected regular-file records identify compressed shared libraries. Bounded private reads used their checked catalog extents inside the update image, not guessed live-device offsets. Each selected file fits one declared contiguous extent, starts at logical file block zero and fits the catalog size. The public library inspector accepts only already supplied file bytes; it cannot extract files, decrypt encrypted chunks or access a device.

VDFS layout-6 zlib descriptors, descriptor CRCs, stored-chunk hashes and descriptor hashes all match. Decompression ends within the declared size; trailing bytes are limited to zero alignment padding. RSA signatures remain **unverified**. Digest consistency is not authenticity or boot acceptance.

| File | Stored bytes | Decoded bytes | Static result |
| --- | ---: | ---: | --- |
| `libcapi-drm-widevinecdm.so.0.1.1` | 8,888 | 17,708 | ELF32, little-endian ARM, shared object |
| `libdrm-service.so.0.1.0` | 23,736 | 46,856 | ELF32, little-endian ARM, shared object |

The Widevine C API wrapper declares dependencies on `libmuse-core.so.0`, `libdrm-muse-proxy.so.0`, `libdlog.so.0`, `libgcc_s.so.1`, `libc.so.6` and `ld-linux.so.3`. The DRM service additionally names `libwvcdm.so.0`, `libplayready.so.0`, `libdrmdecrypt.so.0`, `libmuse-server.so.0`, `liblegacy-drm.so.0`, GLib/GObject/GIO and TBM libraries. These are declared link dependencies, not proof that every library loads, executes or supplies the installed unit's playback path.

**Consequence:** copying the small Widevine wrapper does not supply a self-contained protected player or establish an Android DRM plugin. The actual dependencies below the wrapper, their framework/ABI interfaces, secure-world calls, independent provenance and provisioning route remain to be qualified. The existing [Android DRM boundary](https://source.android.com/docs/core/media/drm) still requires a scheme integration; a filename containing Widevine does not provide one. No Samsung binary is proposed as a final-system component.

The file `org.tizen.netflix-app.sh` is an update-migration hook. Static inspection shows update-environment helper imports and a vconf reset operation; it is not evidence of an application-launch API. Its bytes were not executed or published. This corrects the initial filename-based candidate classification.

## Reproduce the bounded inspections

Use privately prepared, already decrypted inputs from the previously checked shared update. The metadata input must exactly cover the single metadata extent declared by the checked VDFS headers. Unsupported geometry or multiple extents are refused rather than guessed.

```sh
python3 tools/inspect_vdfs_catalog.py \
  --platform-prefix PRIVATE_PLATFORM_PREFIX \
  --metadata PRIVATE_METADATA_EXTENT \
  --image-bytes 1430257664 \
  --output .local/catalog-review.json

python3 tools/inspect_vdfs_library.py \
  --file PRIVATE_SELECTED_STORED_LIBRARY \
  --output .local/library-review.json
```

Both commands refuse nonregular/link inputs and output aliases, bound memory/input sizes and emit metadata only. The catalog has a fixed research-target allowlist; no arbitrary name-export option exists. The library inspector rejects encrypted chunks, unknown codecs/layouts, overlapping ranges, oversized inflation, bad hashes/CRCs, ambiguous ELF tables and unsafe dependency strings. Synthetic tests exercise these refusals and graph corruption. Neither command executes, mounts, signs, installs or validates protected-media eligibility.

## Remaining work in dependency order

1. Trace the real media-service, secure-world and controller interfaces beneath these wrappers. Establish independent implementation/provenance for each required interface. The catalog and ELF graph now identify concrete artifacts; public absence alone must not be treated as impossibility.
2. Establish the selected hardware/DTB variant and ROM/early-stage trust policy. A checked shared update cannot prove which variant is installed or that an owner-built image will be accepted.
3. Qualify recovery outside every stage a proposed experiment could damage, on a proven matching lab assembly. No recovery command, installer, fuse/counter/RPMB operation or household write is justified by these results.
4. Only after boot/recovery and independent support are credible, select board build inputs and demonstrate display, original remote, audio, power and thermal behavior. Qualify independently provisioned protected playback, then all four providers' stock-supported UHD/HDR and exact-title/stop-at-end behavior.
5. Complete production agentOS broker registration, grants, audience/disclosure enforcement and every required owner/provider workflow. The existing TLS/Binder/executor component tests remain useful, but do not prove the household agent route.

The [board integration table](../docs/deployment/board-integration.csv) now records the available static evidence without inventing hardware or implementations. The [recovery gates](../docs/deployment/recovery-plan.md) remain unchanged. No target image or household installation is qualified.
