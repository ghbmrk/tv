# Early-memory package boundary

Observed 2026-10-24, offline against the checked public update. The package named `ddr.init` contains a bounded table and three disjoint payload ranges. Their roles, instruction sets, executing loader and correspondence to the household board remain unknown. No payload or vendor utility was executed, patched, repackaged or installed.

## Recovered structure

The complete 55,808-byte input reproduces SHA-256 `03f5a3cf865c366f60ab174368ba3142d04a2164098de39ef838af9072c893c5` from the previously CRC-checked [update inventory](decrypted-update-inventory.json). A separately written inspector validates a 16-byte little-endian header, three 40-byte entries and a null-identifier terminator. Entry identifiers are retained only as hashes; the header serial field is not exported. The [evidence record](ddr-package-inventory.json) contains digests and ranges.

| Entry | File offset | Payload bytes | Role |
| --- | ---: | ---: | --- |
| 0 | 512 | 16,384 | Unknown |
| 1 | 16,896 | 10,240 | Unknown |
| 2 | 27,136 | 28,672 | Unknown |

Every payload fits the complete input and is disjoint from the table and other payloads. The terminator's end field agrees with the file length. Another 336 bytes between the table and payloads are uninterpreted; they are not presumed to be padding, a signature or a key. Table consistency and hashes do not authenticate the package.

## Primary format comparison

The inspected [TF-A header at the pinned revision](https://github.com/ARM-software/arm-trusted-firmware/blob/eb60949df191608e1a5a707fc175fa74c39c245c/include/tools_share/firmware_image_package.h) defines the same header/entry field widths but a different magic: `0xAA640001`. The observed package uses `0xAA320001`. The [inspected I/O driver's header check](https://github.com/ARM-software/arm-trusted-firmware/blob/eb60949df191608e1a5a707fc175fa74c39c245c/drivers/io/io_fip.c) requires the upstream magic and a nonzero serial. Its unmodified check would therefore not accept this package's marker. This is a format comparison, not proof that Samsung uses this TF-A revision or that TF-A can boot the TV.

Exact-byte comparison finds no match for the three identifiers among the 35 canonical identifier definitions in that one header. The header also permits platform-specific definitions; those are not covered by this comparison. No BL2/BL31/trusted-OS/DRAM-training role is assigned from filenames, payload sizes or marker resemblance. In particular, the `AA32` marker is not treated as proof of a CPU instruction set. The third primary reference records the upstream name/identifier catalogue; no upstream tool was executed or copied into the product.

## Consequence for a replacement

The early-memory initialization domain must be accounted for separately from an Android kernel and UI. This artifact supplies three concrete candidates for further analysis, not an independent implementation, complete early boot chain or recovery backup. The actual selection/loading mechanism, payload meaning, hardware variant, provenance and accepted signing authority remain unresolved. Copying or rewriting this container would not establish any of them.

Any experiment that could prevent DRAM initialization needs recovery that can still operate without that successful initialization. A recovery service inside Linux or an ordinary update app cannot, by itself, establish that coverage. This is a dependency requirement, not a proposed SRAM, USB or programmer procedure. No DDR/boot experiment is qualified on the household TV.

## Reproduce and challenge

```sh
python3 tools/inspect_fip_table.py --file PRIVATE_DDR_INIT \
  --output .local/ddr-table-review.json
python3 -m unittest tests.test_fip_table -v
```

The inspector bounds input and entry counts, requires unique nonzero identifiers, checks a complete terminator and rejects overlaps, header/table intersections, zero/oversized ranges and truncation before hashing payloads. It recognizes only the two stated marker forms and does not export identifiers, the serial field, payloads or keys. Tests distinguish marker recognition from compatibility, exercise malformed/overlapping/duplicate tables and verify private-text omission. No signing, extraction, conversion or hardware writer is provided.
