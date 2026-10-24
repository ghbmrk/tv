# Static wrapper-to-kernel handoff

Observed 2026-10-24. This is offline analysis of the checked shared update's `seret.bin`, not a trace of the household TV. No vendor code, monitor call, device operation, mount or hardware write was executed. Raw bytes, native reports and decompiled code remain private.

## What the new evidence establishes

The [inventory](seret-wrapper-inventory.json) binds a 32,768-byte prefix, SHA-256 `01b9d14b09051ef127a59b742a4463bdc765b9a56f63cb7f555e568d30886103`, to the previously checked complete section. The prefix is analyzed as ARM little-endian A32 with a caller-imposed neutral coordinate. Neither architecture nor entry mapping is promoted to an observed device fact.

A direct A32 call at **file offset 1,184** targets **file offset 32,768**, exactly the start of the [validated nested zImage header](CONTROLLER_AND_RECOVERY_FINDINGS.md#arm-compressed-image-follow-up-october-24). A separate decoder checks the complete input digest, original four-byte digest, file-coordinate mapping, condition field, link bit and signed branch displacement. It also checks the entry-relative branch and the call to a decoding helper. These are file offsets, not flash or live memory addresses.

This replaces a filename/adjacency hypothesis with static control-flow evidence connecting the prefix to the nested image. It does not establish that the path executes, its initial CPU/device state, the acceptance of this section by an earlier verifier, or an independently bootable recovery mechanism. The analyzed entry body has two noncontiguous ranges; its enclosing span must not be treated as wholly executable function code.

## Post-image device trees

At the declared zImage end, file offset 2,049,920, a 12-byte envelope declares 163,859 packed bytes and 1,032,208 decoded bytes. Its first word is `0x2020`; its wider meaning is unknown. The wrapper's inferred decode-call arguments agree with these sizes and the packed payload position. The surrounding prefix is not claimed to implement a particular upstream decompressor.

Independent bounded raw-DEFLATE decoding reaches EOF with exactly the declared size, no unused bytes and no unconsumed input. The decoded SHA-256 is `98899d88ebe971f0aacee314b1dc973862238d1349704cc7896b73357178321b`. The existing structural FDT parser validates **twelve nonoverlapping device trees**. They declare the PontusM TV family and four CPU nodes compatible with Cortex-A57/ARMv8. These remain declarations in a shared artifact, not fitted silicon or the selected household variant. None is byte-identical to the twelve trees in the separate main `dtb.bin` item; this does not itself prove different physical boards. Another 1,448,033 section bytes after the envelope remain uninterpreted. Raw DEFLATE has no checksum or signature; successful decoding and FDT structure do not authenticate the publisher.

Decompiler inference shows a fixed-stride tree-selection path with a byte index and an above-nine fallback to zero. The selector byte's upstream origin and actual value are unresolved. Twelve trees do not imply twelve supported household boards, and the fallback is not a safe way to choose this TV's tree. No selector, GPIO, memory, controller or sysfs read is authorized by this finding.

## Raw-analysis control and independent checks

The original [ARM control](../tools/rea/fixtures/raw_arm_control.S) implements an unsigned range/arithmetic predicate. With raw file offset zero mapped to analysis zero, Ghidra assigned an exception-vector name to its ordinary branch target and split the function body: 16 bytes instead of the original 28. The decompiled predicate alone looked correct. Repeating at a neutral coordinate recovered the complete 28-byte body and ordinary branch label. The control's bytes and both report digests are retained in the inventory.

This demonstrates why provider-assigned vector names and function boundaries are observations to challenge, not hardware roles. The neutral coordinate is a tool setup, not discovery of the actual load address. Default signatures, pointer types, absolute references and dynamic paths remain unqualified.

The A32 branch checker follows the signed immediate/PC-relative encoding described in [LLVM LLDB's primary implementation](https://lldb.llvm.org/cpp_reference/EmulateInstructionARM_8cpp_source.html). It independently decodes only B/BL, reports conditions without evaluating them, and refuses BLX, Thumb, bad alignment, wraparound, mismatched digests, ambiguous record bounds and altered destinations. It neither executes instructions nor proves runtime reachability.

```sh
python3 tools/check_raw_arm_branches.py --file PRIVATE_SERET_BIN \
  --inventory research/seret-wrapper-inventory.json
python3 tools/inspect_seret_wrapper.py --file PRIVATE_SERET_BIN \
  --output .local/seret-wrapper-envelope.json
python3 -m unittest tests.test_raw_arm_branches tests.test_seret_wrapper -v
```

The envelope inspector requires one supported zImage header, derives the next file position from that header, bounds compressed/output sizes, rejects trailing/truncated streams and requires structurally valid trees. It exports metadata only. Tests include input translation, signed branches, interworking rejection, corrupted scopes, partial/trailing input, excessive expansion, duplicate FDT properties, ambiguous image headers and private-canary omission. Neither tool selects a hardware image or authorizes execution.

## Implementation consequence

The update contains a wrapper with a static handoff to an ARM Linux image and a separately compressed family DTB bundle. An independent replacement needs its own correct startup/DTB preparation, earlier boot acceptance and hardware support; retaining this Samsung wrapper or its kernel would fail the original requirement. The earlier boot stages, their accepted authority, selected variant, controller/secure-world initialization and independent restore mechanism remain unresolved. The native provider closed with no pending cleanup, and the original section hash is unchanged.
