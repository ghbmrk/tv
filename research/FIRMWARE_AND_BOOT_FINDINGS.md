# Full update integrity and offline analysis

Observed 2026-10-15. The complete [official T-PTMFAKUC-0090 update](https://downloadcenter.samsung.com/content/FM/202609/20260908143326448/T-PTMFAKUC-0090.zip) is retained privately under `reference/firmware/`. Its 1,465,434,949 bytes match the advertised length. SHA-256: `e15357631ee015215a096690f5e9b2bb9419400044572c59fa344f9730194164`. All five ZIP entries passed CRC checks; decompressed members were streamed and hashed without extraction or execution. Publisher signatures are unverified. An update archive is not a complete device backup or recovery procedure.

The [full inventory](full-update-inventory.json) supersedes earlier partial-acquisition limits. The historical range record still describes only its original byte ranges. `info.txt` has the same hash as the earlier CRC-checked copy. The complete `upgrade.msd` is 1,465,203,794 bytes, SHA-256 `cb0b87a332c4d4138af5bc875f535e56b6600738cb0546ba0e269bb677cbfb38`.

## What the container establishes

An independently implemented bounded parser checked the public MSDU11 outer-table layout against this archive. It finds nine section ranges, one metadata-header range labelled `T-PTMFAKUC-0090`, and a 234-byte table. The metadata range starts at 234 and spans 4,056 bytes; the first section starts at 4,290. All declared ranges are nonoverlapping, within the file, contiguous after the table and end exactly at EOF. IDs, file offsets and sizes are recorded in the inventory.

These are unauthenticated update-file ranges. They do not identify runtime partitions, executable architecture, flash addresses, boot stages or writable storage. The parser does not decrypt, mount or install anything. Layout research was cross-checked against [bugficks/msddecrypt at c5e6d661](https://github.com/bugficks/msddecrypt/tree/c5e6d661640521ab292f7cedc329b092d805906b); no implementation or key values were copied into public source.

The raw complete-member marker scan finds `MSDU11` once at offset zero and `Salted__` once at 242. It finds none of the scanned ELF, Android boot, AVB, SquashFS or FDT markers. Absence of these signatures cannot prove absence of code, boot verification or a component: the contents may be encrypted, compressed or encoded differently.

## REA execution and validation

[REA](https://github.com/morluto/rea/tree/c9f9b83c6f5878f1d5b102ab206a2ce214749258) 6.5.0 and Binwalk 3.1.0 ran in a project-local Linux ARM64 container. The installed package integrity, engine hash, inputs and bounded results are in [the analysis record](rea-firmware-inspection.json). The source commit was reviewed; the published npm package does not identify its Git revision. It is pinned separately by version and registry integrity.

The runtime had networking disabled, no device mounts, all capabilities dropped, no-new-privileges, a read-only root filesystem, one read-only input-file mount, bounded temporary storage, memory/CPU/PID caps and REA's own worker/deadline/prlimit controls. No extractor, mount, emulation, key extraction or vendor-program execution occurred. No global agent setup was changed. Upstream's documented firmware qualification was Linux x64; this ARM64 run adds only the observed local validation below.

A deterministic synthetic gzip control was recognized at offset zero. REA then scanned the previously retained 261,520-byte prefix and a first-MiB derivation from the complete member; both input hashes are recorded. It reported an OpenSSL marker candidate with confidence zero and a tiny zlib candidate at 256,063. That candidate and both additional zlib candidates in the first-MiB scan failed independent bounded decompression checks. A reported GPG marker is unverified and is not evidence of an authenticated signature. None is accepted as a usable payload. Provider sizes and confidence values are preserved as reported, not promoted to validated boundaries.

The [container recipe](../tools/rea/Dockerfile) pins base image digests and primary tool versions. The observed Binwalk executable hash and npm dependency-lock hash identify this build. Apt package resolution and npm transitive dependencies are not fully frozen by the recipe; an identical rebuild is not claimed. The image contains tools, not vendor artifacts, and has not been published.

## Compatibility and boot boundary

A bounded offline compatibility check tried the ten published legacy update-key profiles from the pinned decryptor against only the metadata envelope. The published AES-CBC/MD5-IV recipe yielded no recognized OUIT header. Published reference source remains ignored; key values were not logged or copied into public artifacts; no device credentials or provider DRM material were used. This rules out acceptance by that tested legacy recipe, not every possible decryption route.

The [2019 Q60R research](https://labs.reversec.com/posts/2019/12/opening-up-the-samsung-q60-series-smart-tv) and [current root-tool research](https://github.com/chris-ritsen/samsung-tv-root/blob/4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b/docs/research-notes/AES_EXTRACTION.md) show device-dependent firmware analysis paths. They are evidence about their tested devices; neither proves access, key compatibility or boot policy on this LS03F.

No target bootloader, DTB, secure-world image, live storage map or controller identity has been recovered from these artifacts. The next critical dependency is exact-TV evidence through a separately reviewed, read-only access path. Ordinary settings and documented developer access come first; root tooling is not run merely because another model supports it. Any subsequent persistent experiment still requires exact identification and demonstrated recovery for its failure mode. Decrypting an update would enable further analysis, not automatically permit independent boot or qualified provider playback.
