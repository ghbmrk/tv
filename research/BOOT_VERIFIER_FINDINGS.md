# Native update-verifier findings

Observed 2026-10-18 from the official shared update, offline. No household-TV connection, vendor-code execution, mount, flash or third-party message occurred. This is a deeper extension of the [filesystem investigation](RUNTIME_DEPENDENCY_FINDINGS.md), not an independent-boot milestone.

## Result and consequence

`SWUVerifierTV` is not qualified as a read-only diagnostic. Static analysis identifies actual call instructions to boot-partition getter/setter and reboot imports. Decompiler output associates the setter with update finalization and a configuration guard. Runtime reachability and the external implementation's exact effects remain unknown; the binary must not be run on the household TV to find out.

The userspace installation verifier delegates checks to finalizers. Its completion message does **not** establish the ROM's image-signature policy, independent-image acceptance or recovery. The next causal boundary is the finalizer implementations and the PPI power-control implementation beneath the imports, followed by early-stage boot evidence. An update application's name or success string cannot substitute for that evidence.

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

## Reproduce and challenge

Follow the pinned [native analysis workflow](../tools/rea/NATIVE_ANALYSIS.md). An original ARM fixture checks that the native decompiler recovers a known range/arithmetic predicate. This is a tool control, **not** vendor behavioral parity.

For a privately supplied verifier with the exact inventory digest:

```sh
python3 tools/check_native_calls.py --file PRIVATE_SWUVERIFIER_ELF
python3 -m unittest tests.test_native_calls -v
```

The checker independently validates the ELF mappings, four-byte hashes and direct branch targets without Ghidra or executing the input. It refuses mismatched digests, ambiguous/non-executable mappings, unsupported encodings and destination changes. Synthetic tests cover forward/backward branches, PC alignment, rebase mistakes and corrupted metadata. It does not validate decompiler semantics, indirect targets, external implementations, signatures or hardware safety.

REA and Ghidra analysis used an ephemeral project; the provider reports the target closed with no pending cleanup. The input hash is unchanged. Raw vendor code, pseudocode, assembly, catalog records, tool-session output and owner information remain private.

## Method boundaries

The useful part of the REA workflow is a narrow question, an exact artifact, tool-backed observations and an independently checkable predicate. Prioritize causal boundaries such as partition selection and authentication; xref frequency alone is not a measure of importance. One indirect call can matter more than a logging helper called hundreds of times.

This investigation is **not claimed as clean-room work**: public Samsung format source and native analysis have been read. A fresh chat cannot establish an enforced information boundary. Any future clean-room implementation needs a bounded behavioral specification, documented provenance and a separately enforced implementation environment; legal conclusions cannot be inferred from a social-media checklist.

No spare matching assembly is available. Static tracing can continue, but this evidence does not qualify destructive recovery rehearsal on the household TV. Exact board/variant correspondence, earliest-stage trust policy, Samsung-free hardware support and independently provisioned provider-quality playback remain separate unresolved gates. The final requirement still excludes Samsung software in every required stage, including immutable/peripheral/recovery components.
