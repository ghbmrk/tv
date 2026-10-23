# Native update-verifier findings

Observed 2026-10-18 from the official shared update, offline. No household-TV connection, vendor-code execution, mount, flash or third-party message occurred. This is a deeper extension of the [filesystem investigation](RUNTIME_DEPENDENCY_FINDINGS.md), not an independent-boot milestone.

October 23 continuation: the [controller initialization and embedded recovery findings](CONTROLLER_AND_RECOVERY_FINDINGS.md) trace the message ioctl, identify implicit watchdog/rollback behavior in family source and validate a Linux-bearing XZ payload inside `seret.bin`. They do not qualify a RAM boot or independent recovery.

## Result and consequence

`SWUVerifierTV` is not qualified as a read-only diagnostic. Static analysis identifies actual call instructions to boot-partition getter/setter and reboot imports. Decompiler output associates the setter with update finalization and a configuration guard. Runtime reachability and the external implementation's exact effects remain unknown; the binary must not be run on the household TV to find out.

The userspace installation verifier delegates checks to finalizers. Its completion message does **not** establish the ROM's image-signature policy, independent-image acceptance or recovery. The power-control trace now reaches a `/prd` backend and MICOM library. The October 23 follow-up finds storage-write calls inside the pre-switch helper and an ioctl dependency in the controller-message transport. Actual controller firmware, early-stage trust and installed-unit correspondence remain unresolved. An update application's name or success string cannot substitute for that evidence.

## Evidence

The [inventory](boot-verifier-inventory.json) binds inputs, tool versions, evidence IDs, private-report hashes and conclusions. The stored verifier is 708,488 bytes; its checked VDFS layout-6 wrapper decodes to a 1,495,976-byte ELF32 little-endian ARM object, SHA-256 `a91946004bdc886eef1ca541b2ca86c9df320ee6002c16c0ff8408782708694e`. All 12 stored-chunk hashes, descriptor hash and descriptor CRC match. Its RSA signature is **not authenticated**.

Ghidra's default completed analysis identifies 2,859 procedures, 3,378 strings and 30 segments. These are analysis-database counts, not proof of complete recovery. The ELF's lowest load address is zero; Ghidra rebased it to `0x10000`. All addresses below are **analysis coordinates in this exact file**, never device RAM, register or flash locations.

| Observation | Call-site coordinate | Original ELF file offset | Import thunk |
| --- | --- | --- | --- |
| Direct boot-partition setter call | `0xba378` | `0xaa378` | `0x2d058`, `ppi_powercontrol_set_boot_partition` |
| Direct boot-partition getter call | `0xba18c` | `0xaa18c` | `0x2d590`, `ppi_powercontrol_get_boot_partition` |
| Direct reboot-request call | `0x8909e` | `0x7909e` | `0x2c7cc`, `device_power_request_reboot` |

These are stronger than an import-name search: the call-site bytes match the original file, the ELF program headers independently reproduce the offsets after rebasing, and a separate Thumb-2 BLX decoder reproduces all three destinations. Symbol binding still depends on the imported binary's metadata; destination agreement does not prove what an external function does.

Ghidra associates the setter with function `0x604c4`, whose body has disjoint ranges `0x604c4–0x60507` and `0xba308–0xba49b`. Treating the entire enclosing span as that function would be wrong. Pseudocode suggests a configuration check before the call, Boolean normalization of the requested slot and error handling for a nonzero result. The log's flag name is a clue, not proof of the installed configuration or a safe bypass.

The getter belongs to `0xba16c`; inferred output is normalized to two states after a successful external result. Do not infer physical partition numbering from that Boolean. Ghidra reports no enclosing function for the reboot call; its caller/control conditions remain unresolved. No function boundary was invented to fill that gap.

At `0x5cacc`, pseudocode shows an installation-finalization loop with an indirect verification call and early failure. The loop's concrete runtime objects remain unresolved. Function `0x407fc` orchestrates userspace verification and completion; `main` calls it. Neither trace establishes pre-userspace trust enforcement. A keyword search not finding secure-boot strings would not establish their absence.

The small `libSWUProductionConfig.so` was also decoded and imported separately; that alone does not identify active flag values. It is recorded as an additional input, not evidence that partition switching is disabled.

## Power-control dispatch boundary

The verifier declares `libpower-control.so.0` as a link dependency. Its catalog identifies `libpower-control.so.0.1`, whose ELF SONAME matches that dependency. The checked 20,984-byte compressed file decodes to 64,288 bytes, SHA-256 `11bee8dec64f00f5ef35f61910404511ffb7b1f386742ec86108de1c5cd650bb`. This is a candidate resolution from shared-update metadata, not a runtime loader observation. Its compression CRC/hashes match; its signature remains unauthenticated.

Decompiler inference: both exported boot-slot operations initialize a backend lazily, check its callback table and delegate via indirect calls (getter table offset `0x1c`, setter `0x20`). These are **structure offsets in the analyzed wrapper**, not device addresses. Ghidra emits indirect jump/jumptable-recovery warnings, so the concrete callees remain unverified. The wrapper has only libc, libdl, dlog and GCC support as declared dependencies; it is not the board implementation.

The defined backend-loader symbol has Thumb-tagged ELF value `0x444262cd`; exact entry `0x444262cc` disambiguates it from the PLT thunk. Its pseudocode identifies `dlopen` of `/prd/usr/lib/libpower-control-impl.so`, then registration/version checks. That file name is absent from the platform catalog but present in the separately inspected `prd_t.img`. No backend path was executed and no global library search path was changed.

The 58,720,256-byte `/prd` image range matches its previously checked header. Its snapshot CRC/header reference, all 58 catalog-node CRCs/versions, rooted graph, height and reciprocal siblings pass; 2,865 leaf records are not a unique-file count. Three bounded inline symlinks resolve the loader path to `libpower-control-impl-sec.so.0.1`. The final regular file fits its one checked extent; its 21,240-byte compressed wrapper decodes to 50,638 bytes, SHA-256 `d1c4e12f3b768c4b8c29dfa94547d32c1ad1312d32dca83934de28cc73d2ebe2`. CRC and hashes match; signature authenticity remains unverified. These are ranges inside the shared update, never a live-device map.

Backend decompiler inference: initialization function `0x11b4c` registers the getter and setter at table words seven/eight, matching the wrapper's byte offsets. Getter `0x155ac` calls `micom_get_boot_partition` and accepts returned values zero/one. Setter `0x15524` checks that range, calls `restore_fake_magic`, and only on a nonnegative result continues to `micom_set_boot_partition`. The MICOM library is a declared link dependency. The helper's name does not establish what it restores, where it writes or whether it is safe.

The getter call and pre-switch-helper call have independently checked original-file mappings, instruction hashes and direct BLX destinations in the inventory. The setter tail transfer goes through a Thumb/ARM thunk with incomplete function-body/call coverage; its MICOM semantics remain decompiler inference. No claim of dynamic execution, complete call recovery or physical storage effects follows. The controller protocol/firmware, helper implementation, mount selection and installed-unit correspondence remain unresolved. This is a concrete peripheral dependency for the Samsung-free requirement, not a proposal to retain the vendor backend.

## MICOM and storage-write boundary, October 23

The same CRC-checked `/prd` catalog contains a two-link library chain ending at `libmicom.so.0.1`. Its single bounded extent yields a 64,296-byte compressed file and a 142,302-byte ELF32 ARM library, SHA-256 `040372dfd200205f18c56067c2d57af7d0af64bd51a995ded0ac5c39b6c51763`. Both chunk hashes, the descriptor hash and descriptor CRC pass; signature authenticity remains unverified. Its SONAME matches the backend's declared MICOM dependency. This is candidate resolution inside the shared update, not observed binding on the household TV.

Static call evidence: `restore_fake_magic` contains calls to the `pwrite64` and `fsync` import thunks. A separate decoder reproduces both direct BLX destinations from the original ELF and independently checks file mapping and instruction hashes. This closes the previous uncertainty about whether the helper contains storage-write operations. It does **not** prove when they execute, their actual target on the installed unit, a successful write or recoverability. Do not run this helper as a diagnostic or infer a safe slot-switch procedure from it.

Decompiler inference: the exported boot-partition getter and setter delegate to `micom_send_msg`; that transport contains an `ioctl` dependency and device initialization. Diagnostic strings refer to uImage-header restoration and CRC checks. These clues do not establish the live storage map, controller protocol semantics or ROM authentication policy. CRC checks are not signature authentication. The original controller firmware remains a replacement dependency, rather than a component qualified for reuse.

The `micom_library` inventory record binds the checked file and two calls; raw vendor code and analysis reports remain private. No vendor code, controller operation, mount or household-TV connection was executed. The native-analysis provider closed with no pending cleanup.

## Update-core trust boundary, October 23

The same catalog yields a unique rooted `/usr/bin/SWUCoreTV` regular file with one checked extent inside the declared VDFS volume. Its 2,293,240-byte compressed file decodes to a 4,737,944-byte ELF32 little-endian ARM executable, SHA-256 `c538eb0d686dd1d4b336e11262b81ecab2af3b34d1dc3f6ae0ef827eb3d4e731`. All 37 chunk hashes, descriptor hash and CRC match; signature authenticity remains unverified. This is a shared-update artifact, not an observed running implementation on the TV.

Static call evidence: analysis coordinate `0x308b8e`, original ELF offset `0x2f8b8e`, calls the `EVP_PKEY_verify` import thunk at `0x5f0b8`. Independent mapping, instruction hashing and Thumb BLX decoding reproduce the destination. Function `0x308b54` has an inferred comparison of that result against one. [OpenSSL's API documentation](https://docs.openssl.org/3.0/man3/EVP_PKEY_verify/) defines one as verification success, zero as a failed signature and negative values as other errors. The call check does not independently prove the comparison, error propagation or dynamic reachability.

Nearby context setup imports verification/signing initialization, RSA-padding and signature-digest configuration. These are code dependencies, not proof of active parameters, key origin, available signing authority or a trusted owner-build path. No key material was inspected or exported. No update-section signature was authenticated by this investigation.

The literal `RSASignatureSink` is present, but a bounded RTTI-layout attempt did not establish a complete class/vtable binding. No image-specific role is assigned from that name. Incoming procedure references also contain internal jumps and data pointers; treating every entry as a dynamic caller would be wrong. The exact update-item binding and the earliest-stage verifier remain unresolved.

**Consequence:** a userspace signature-check call is now independently located. It does not establish ROM policy, acceptance of an independently signed kernel/secure OS, or recovery. An updater cannot qualify its own replacement boot chain merely by containing cryptographic code. The `update_core` inventory record preserves the narrower claim, the evidence and the unknowns. Native analysis closed without pending cleanup and the input hash is unchanged.

## Reproduce and challenge

Follow the pinned [native analysis workflow](../tools/rea/NATIVE_ANALYSIS.md). An original ARM fixture checks that the native decompiler recovers a known range/arithmetic predicate. This is a tool control, **not** vendor behavioral parity.

For a privately supplied verifier with the exact inventory digest:

```sh
python3 tools/check_native_calls.py --file PRIVATE_SWUVERIFIER_ELF
python3 -m unittest tests.test_native_calls -v
```

The checker independently validates the ELF mappings, four-byte hashes and direct branch targets without Ghidra or executing the input. It refuses mismatched digests, ambiguous/non-executable mappings, unsupported encodings and destination changes. Synthetic tests cover forward/backward branches, PC alignment, rebase mistakes and corrupted metadata. Its `inspect(data, record)` entry point also checks the inventory's `power_control_backend`, `micom_library` and `update_core` records against their respective private ELFs. It does not validate decompiler semantics, indirect targets, external implementations, signatures or hardware safety.

REA and Ghidra analysis used an ephemeral project; the provider reports the target closed with no pending cleanup. The input hash is unchanged. Raw vendor code, pseudocode, assembly, catalog records, tool-session output and owner information remain private.

## Method boundaries

The useful part of the REA workflow is a narrow question, an exact artifact, tool-backed observations and an independently checkable predicate. Prioritize causal boundaries such as partition selection and authentication; xref frequency alone is not a measure of importance. One indirect call can matter more than a logging helper called hundreds of times.

This investigation is **not claimed as clean-room work**: public Samsung format source and native analysis have been read. A fresh chat cannot establish an enforced information boundary. Any future clean-room implementation needs a bounded behavioral specification, documented provenance and a separately enforced implementation environment; legal conclusions cannot be inferred from a social-media checklist.

No spare matching assembly is available. Static tracing can continue, but this evidence does not qualify destructive recovery rehearsal on the household TV. Exact board/variant correspondence, earliest-stage trust policy, Samsung-free hardware support and independently provisioned provider-quality playback remain separate unresolved gates. The final requirement still excludes Samsung software in every required stage, including immutable/peripheral/recovery components.
