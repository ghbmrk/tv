# PontusM source findings

Observed 2026-10-15. The official family archive is now available offline in the ignored `reference/source/25_DTV_PontusM.zip`. Its 1,071,208,323 bytes match the portal's advertised byte count. SHA-256: `7ec0b6fbe6ff8273d93fc7e6b9ddf8c84f9959a45884313b3d3a6f94d235b94e`. All 24,883 outer ZIP members passed CRC checks. CRC and a locally computed hash establish integrity/repeatability, not a publisher signature or exact installed-build correspondence.

The archive includes `linux.tgz`, media source and separate MICOM, HDMI, audio-amplifier, boot-mode, network and TrustZone-driver packages. [The portal listing](https://opensource.samsung.com/uploadSearch?searchValue=LS03F) covers `QN**LS03FA****`; its listing version remains 1000, versus the owner's installed 1301.0. The archive's arrival resolves acquisition, not that version relationship.

## Concrete observations

The bounded nested inspection traversed 71,624 kernel members (913,044,593 declared expanded bytes), reading seven selected text files in memory after the board-contract extension. [The machine-readable inventory](pontus-kernel-inventory.json) records their hashes and selected metadata; no source is redistributed or executed.

| Evidence | Observation | Consequence |
|---|---|---|
| `linux-5.4/Makefile` | Linux 5.4.261 | A kernel-family baseline for comparison with the target; not a selected Android kernel. |
| `arch/arm/configs/PONTUSM_release_defconfig` | ARM, ARMv7, Cortex-A15 configuration symbols, AEABI, SDP/Pontus platform selected | Investigate a 32-bit platform first. These are build settings, not an exact chip or board identification. The ARM64 emulator used for shell development is not target-ABI evidence. |
| Same defconfig | `CONFIG_ANDROID=y`, Binder IPC explicitly disabled | The word Android in a kernel configuration does not establish a runnable Android BSP. Binder and the other framework/device integrations need independent qualification. |
| Same defconfig | MICOM controller/mailbox, IR input, MMC, thermal, shared memory and media/GPU dependencies selected | Map these boundaries before any hardware experiment. Remote, standby and panel behavior may depend on controller firmware beyond the application CPU. |
| Media source paths | Multiple platform directories and embedded DSP firmware arrays/binaries occur in the release | Presence does not prove which variant the owner's board uses, that complete source is available, or that blobs satisfy the no-Samsung-software requirement. Treat this package as research evidence. |

The source does not yet establish board revision, exact SoC/GPU, live ABI, storage layout, installed configuration, controller identities, boot-ROM policy, independent boot, recovery, or protected-provider provisioning. Those fields remain unverified in the device profile. No stock firmware, kernel, driver or microcode from this release has been incorporated into the product.

## Machine fingerprint and CPU bring-up boundary

The selected `arch/arm/mach-sdp/board-pontus-dt.c` is 4,910 bytes, SHA-256 `cf83256d707d45d0bfe2b3e383394a00ada79c8a29796bfba16cd99dc86462dd`. Manual review finds `samsung,sdp-pontusm` in its machine-compatible array and that array referenced by the machine registration. The expanded inventory also hashes the machine Makefile and `platsmp.c` and records allowlisted marker line hashes. Marker locations alone are lexical evidence; the control-flow interpretation comes from reading the identified files.

The Pontus path registers Linux SMP power operations. Its entry-install function selects the secondary CPU startup routine; `platsmp.c` invokes that operation from the secondary-CPU boot path. These are running-kernel CPU bring-up hooks, not proof of primary cold-boot acceptance, an owner signing authority, recovery or an alternate-OS loader. No register operation, driver build or vendor code is executed or incorporated into the product.

The existing fixed read of `/proc/device-tree/compatible` can now check for an exact match to this source-family string. A match corroborates this machine-family hypothesis only; it cannot identify board revision, prove installed-source correspondence, select drivers, or pass an installation gate. A nonmatch records that this specific fingerprint was not observed, not universal incompatibility. Failed, unterminated or malformed string-list reads remain unknown. Raw runtime strings stay private; the public collector adds only a nullable match boolean. Live board collection is still unavailable.

## Reproduction

Run from the repository root with the privately acquired archive:

```sh
python3 tools/index_source.py reference/source/25_DTV_PontusM.zip --output .local/source-index.json
python3 tools/inspect_kernel_source.py reference/source/25_DTV_PontusM.zip --output .local/kernel-inventory.json
```

The nested inspector uses explicit file selection, path/link/duplicate checks and member/size budgets. It never extracts to a filesystem or runs build scripts. The archive-wide CRC check was performed separately using Python `ZipFile.testzip()`. Only metadata, not vendor source, belongs in public Git.

Next, correlate the Pontus platform definitions and controller interfaces with non-unique target hardware/runtime evidence, then establish the boot trust and recovery boundary. Keep the existing independent-boot and provider qualification gates; a kernel reconfiguration alone cannot satisfy them.
