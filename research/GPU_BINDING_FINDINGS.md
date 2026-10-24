# GPU driver selection boundary

Observed 2026-10-24, entirely offline. The [evidence record](gpu-integration-evidence.json) binds checked family trees/source and three primary Linux files at the already recorded Linux v6.18 commit `7d0a66e4bb9081d75c82ec4957c50034cb0ea449`. No driver was compiled, loaded or run; no register/device access or TV change occurred.

## Established declarations

All twelve structurally validated trees recovered from the wrapper declare the GPU compatible string `arm,mali-midgard`. A fixed allowlist also records TV HDMI, FRC/TCON, CEC and audio-codec interface strings without node paths, registers or arbitrary properties. The word `codec` does not by itself identify a video decoder. These are shared-artifact declarations, not an observation of installed hardware or active drivers.

The family `mali_kbase_core_linux.c` contains that generic compatible entry and product labels spanning several GPU families. Four fixed source files, including the SDP platform configuration/implementation, are CRC-read and hashed; selected lexical locations are recorded without copying vendor text. The `midgard` directory/compatible name is therefore insufficient to select a GPU generation, product or upstream driver. Compile-time branches and actual GPU detection remain unverified.

Manual review of `mali_kbase_config_sdp.c` shows its power-on callback delegates to SDP GPU power control. The platform file references custom SDP clock/reset access and PontusM build branches. A working render-core driver would still need independently implemented, exact-hardware initialization and power/clock/reset integration. The source is interface evidence, not a final component qualified for reuse or a safe GPU-ID probe.

## Independent implementation candidate

The [pinned upstream Panfrost match array](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7d0a66e4bb9081d75c82ec4957c50034cb0ea449/drivers/gpu/drm/panfrost/panfrost_drv.c), lines 930-955, contains specific Mali product strings and newer generic families, but no literal `arm,mali-midgard`. The [Midgard binding](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7d0a66e4bb9081d75c82ec4957c50034cb0ea449/Documentation/devicetree/bindings/gpu/arm,mali-midgard.yaml) specifies product/SoC-compatible sequences; the [Bifrost binding](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7d0a66e4bb9081d75c82ec4957c50034cb0ea449/Documentation/devicetree/bindings/gpu/arm,mali-bifrost.yaml) defines a different contract. Exact captured digests and the complete inspected match array are in the record.

**Decision:** Panfrost is an implementation family to evaluate after product identification, not a selected driver for this TV. This snapshot's binding mismatch does not prove physical GPU incompatibility. Renaming the compatible string merely to force a probe would invent hardware identity and could activate unsuitable initialization. No device-tree patch or kernel trial follows from this comparison.

An independently supported GPU also would not establish the TV's display scanout/composer, panel processing, video decoder, protected buffers, HDR/color behavior or provider acceptance. Keep those as separate component-ledger entries and acceptance results. No ABI/kernel branch is selected from these declarations.

## Reproduction and next discriminators

```sh
python3 tools/inspect_media_source.py reference/source/25_DTV_PontusM.zip \
  --gpu --output .local/gpu-source-inventory.json
python3 tools/inspect_seret_wrapper.py --file PRIVATE_SERET_BIN \
  --interfaces --output .local/seret-interface-inventory.json
```

Interface output is opt-in and restricted to a fixed set of non-unique names. The original root/CPU-only inspection stays unchanged. Tests check that unrelated compatible values and node addresses do not reach output. Source inspection checks unique bounded regular ZIP members and CRCs, emitting only hashes and lexical locations.

The decisive missing inputs remain the actual GPU product/revision, active execution interface and independent clock/reset/power support, alongside the earlier board/boot/recovery gates. These need exact evidence; they cannot be inferred from a similarly named Samsung model or a driver source's list of supported products. No hardware observation or existing safety restriction is relaxed by these findings.
