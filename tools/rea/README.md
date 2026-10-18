# Bounded offline firmware inspection

Native ELF research now has a separate pinned [REA/Ghidra workflow](NATIVE_ANALYSIS.md), an original ARM control and an independent call-destination checker. The container below remains tied to the earlier firmware-region evidence; it has not been silently upgraded.

This is a tool-only container recipe, not a TV image. It installs REA 6.5.0 without package lifecycle scripts or optional native agents and compiles Binwalk 3.1.0 with its published Cargo lock. Base image digests are pinned. Apt resolution and npm transitive dependencies are not completely frozen; record the resulting executable/package/image hashes for each run.

The recorded local run used Linux ARM64 on Docker Desktop. Upstream documents its firmware milestone on Linux x64; ARM64 validation here consists of a known synthetic control and the observed static scans. No global REA/MCP setup is needed.

Build:

```sh
docker build --platform linux/arm64 -t sovereign-tv-rea:6.5.0-binwalk3.1.0 tools/rea
```

Provide a nonempty regular research input of at most 128 MiB, with its source hash and derivation range already recorded. Do not supply the full 1.4 GiB update to this provider. Start with a known synthetic fixture and confirm the expected result. Then run one input at a time, retaining raw output privately:

```sh
mkdir -p .local
TV_RESEARCH_INPUT=/absolute/path/to/bounded-input.bin
docker run --rm --platform linux/arm64 --network none \
  --cap-drop ALL --security-opt no-new-privileges --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=300m --memory 2g --cpus 2 --pids-limit 128 \
  --mount "type=bind,src=$TV_RESEARCH_INPUT,dst=/input/firmware.bin,readonly" \
  sovereign-tv-rea:6.5.0-binwalk3.1.0 \
  inspect-firmware-regions /input/firmware.bin --format json --full-output \
  > .local/rea-report.json
```

Review the JSON envelope's `ok` result and limitations, input digest, actual engine version/executable digest, and reported coverage. A producer signature, confidence or size is a candidate requiring independent validation. Do not turn marker offsets into flash addresses or execute a returned artifact. This recipe includes no extractor and grants no device, network or host-directory access beyond the one read-only input mount.

Use `tools/inspect_update_container.py` for whole-ZIP CRC/hash and bounded outer-table inspection. Published results belong in sanitized metadata records; raw reports, vendor inputs, key material and extracted source remain outside Git.
