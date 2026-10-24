# Media/controller source review and read-side effects

Observed offline 2026-10-15 in the already acquired `25_DTV_PontusM.zip`. The [six-file inventory](media-source-inventory.json) records the archive SHA-256, selected file hashes, byte counts and lexical marker locations. It redistributes no source text. This is family source; exact-board use, active build branches and correspondence to installed 1301.0 remain unverified.

Manual review, beyond token matching, establishes these source-level facts:

1. `sdp_vdsp/pontusm/Makefile` lists CM7/controller and secure-world interface objects alongside VDSP processing objects. `sdp_vdsp_init.c` calls both VDSP and CM7 driver initialization. This is not an Android HAL or an independent firmware replacement.
2. `sdp_cm7_top.c` includes two microcode headers. Its `cm7_dbg_ew_test_show` callback, lines 79–145, maps controller result memory, performs writes, stops the controller, transfers test microcode with `memcpy_toio`, starts it, polls for completion, then stops/transfers normal microcode/starts again. Lines 146 and 151 connect this callback to a simple attribute and an `ew_test` debugfs file with mode `0444`.
3. Therefore, in this implementation, **reading that debug entry triggers hardware/controller effects**. Read-only file permissions do not imply observational semantics. No runtime mount/path, installed availability, persistent damage or actual-unit behavior is inferred. The entry has not been accessed. Do not probe debugfs/sysfs/procfs merely because `cat` or a read permission looks harmless; review the exact callback and target applicability first.
4. `sdp_vdsp_tzdev.c` resolves `tzdev_scm_watch` and uses the wrapper in a secure-world command path. A normal-world driver stub does not supply its secure-world implementation or legitimate independent provisioning.
5. The microcode header hashes establish additional executable-content candidates to account for in the provenance ledger. Their inclusion in a source archive does not establish independent authorship, rebuildable source, licensing permission for every use, exact-unit applicability or replaceability. Recompiling a driver around embedded arrays cannot demonstrate Samsung-software removal.

These findings exclude an unsafe diagnostic shortcut and add media/controller dependencies to the board investigation. They do not demonstrate a port, independent boot, recovery, or a fundamental incompatibility on the owner's unit.

Reproduce without extraction, compilation, execution or device access:

```sh
python3 tools/inspect_media_source.py reference/source/25_DTV_PontusM.zip --output .local/media-source-inventory.json
```

The tool limits the outer archive and selected member sizes, rejects duplicate/missing/nonregular selected entries, hashes the complete source archive and completes selected ZIP-member reads for CRC verification. It does not decompress/CRC-check every unrelated member or authenticate the publisher. Line hashes exclude LF and preserve CR/legacy bytes. The manual control-flow finding must be re-reviewed if the file hash changes.

## GPU follow-up, October 24

The [GPU binding investigation](GPU_BINDING_FINDINGS.md) adds CRC-checked GPU source locations and opt-in address-free interface declarations from the recovered wrapper trees. The generic Mali name does not identify a product or match the inspected upstream Panfrost table. This is a driver-selection boundary, not proof of physical incompatibility, and does not qualify the separate panel/decoder/protected-media paths.
