# Read-only target identification

Collection permission is about the reviewed operation's actual effects, not whether a command is named `cat` or a file has read-only permissions. The [family media-source review](../research/MEDIA_SOURCE_FINDINGS.md) found a readable debug callback that stops controller cores and transfers microcode. Do not enumerate/read unreviewed debugfs, sysfs, procfs or device nodes, invoke vendor diagnostics, or use register/RPMB interfaces as a fallback to missing identity. The fixed operations documented below do not grant broader diagnostic access.

`tools/identify_tv.py` makes one fixed `GET /api/v2/` request on port 8001 at an owner-supplied private LAN IPv4 address. It performs no discovery, authentication attempt, shell command, remote-key action, setting change, sideload or firmware write. Public addresses, hostnames, subnets and implicit loopback are refused. Redirects are not followed; JSON/body bounds and socket timeouts apply.

Replace `TV_PRIVATE_IPV4` with the actual address shown in the TV's ordinary network settings:

```sh
python3 tools/identify_tv.py TV_PRIVATE_IPV4
```

The default output is ignored `.local/tv-identification.json`. Only allowlisted fields survive: recognized full SKU or LS03F family model, matching software-family build syntax, optional developer/Frame flags and bounded reported UI resolution. Unknown model/build strings become null. Raw responses, serials, device IDs, MAC addresses, network details, household names, tokens and arbitrary fields are discarded. Errors never echo raw server status lines or bodies. Review sanitized evidence before publishing it.

The endpoint appears in [primary research on a 2019 Q60R](https://labs.reversec.com/posts/2019/12/opening-up-the-samsung-q60-series-smart-tv); later read-only requests on the owner's LS03F reported the matching full SKU, Frame support and a 3840×2160 UI surface. The software-build field was unrecognized and remains null; the photographed build remains the installed-build evidence. A reported resolution is not decoded stream resolution or quality evidence. HTTP is unauthenticated, so matching reported fields do not establish physical board identity or permission for writes.

A bounded standard SSDP attempt was also made from the development host on 2026-10-15. Both the default route and an explicitly selected active physical interface rejected multicast send with OS error 65 (No route to host). No response or matching TV was obtained. This does not establish that the TV is offline or that a direct request to its actual IP will fail. No routes, privacy settings, VPN configuration or TV settings were changed. Private interface addresses remain outside Git.

A reachable path subsequently became available; this is historical discovery context, not the current blocker. If the endpoint is unavailable, preserve that outcome and review documented developer-access prerequisites; do not turn the failure into automatic rooting or a request to change firmware. Exact SoC/board/ABI, storage, boot trust, controller provenance and recovery still require their own evidence beyond this endpoint.

A subsequent Bonjour-discovered Samsung candidate also failed the same fixed GET with OS error 65, including one retry with host-network permission on 2026-10-15. No model response establishes that candidate as the owner's LS03F. The ordinary command sandbox alone does not explain the permitted retry's failure; the underlying network/host/TV cause remains undetermined. The [safe hardware-session procedure](../research/FEASIBILITY.md#safe-collection-for-the-next-hardware-session) starts with the address shown by the TV, without automatic network or Developer Mode changes.


## Current access boundary

[Sanitized retained observations](../research/target-access-observations.json) record the later successful HTTP reports, developer-mode transition and eventual reachability of ports 8001 and 26101. Official SDB 4.2.36 failed to establish a device session. A passive connection to 26101 received no unsolicited bytes and was closed by the peer after approximately 63 ms, before client application data. That proves connection/closure behavior only, not a firewall, allowlist, firmware or protocol diagnosis.

The API-reported developer-host field was valid IPv4 and matched neither the current Mac address nor the TV address in the private comparison. The owner reports entering one of the supplied addresses; the discrepancy remains unresolved because the API field may be stale or represent something different. No incorrect user entry is inferred. The earlier `0.0.0.0` value was a placeholder, not evidence of a working developer-host configuration.

No additional reboot or setting change is prescribed while off-TV implementation continues. A later access session should first reconcile the displayed Developer Mode host field with the retained comparison, then attempt one bounded official SDB connection if authorized. Preserve the outcome; do not escalate automatically to root, sideloading or firmware changes. Public records exclude all private addresses and unique device identifiers. No new TV connection was made to reconcile these documents.

A subsequent read-only check at 2026-10-15 16:27 UTC again reported the full target SKU and Developer Mode enabled. Official SDB 4.2.36 connection still failed (exit 1). No TV shell command, setting change or installation was attempted. HTTP reachability does not resolve the developer-access blocker.

## Prepared normal-SDB board collection

On 2026-10-15 at 21:04 UTC, after the owner corrected the Developer Mode host entry, official SDB connected and the HTTP endpoint again confirmed the full SKU. All five fixed Unix shell queries returned exit 0 with **empty output**; an additional fixed `uname -m` diagnostic also had empty stdout and stderr. No board identity was obtained. A separate standard `sdb capability` read reported `intershell_support: disabled`, `rootonoff_support: disabled`, `cpu_arch: armv7`, `profile_name: tv`, and `platform_version: 9.0`. These are SDK-reported capabilities, not independent kernel/SoC/board evidence. Connection setup is resolved; do not prescribe more owner setup or repeat these shell reads without a new evidence-backed reason. No installation, root, reboot or persistent write was performed by the tools.

The original collector classified five zero exits as completed reads. That was incorrect: empty results now produce `reads_empty`, zero successful/validated reads and unknown CPU data. Nonempty unrecognized output is partial; completion requires all five parsed results. Earlier private reports remain immutable and must be interpreted with this correction.

Samsung documents shell restrictions in its [debugging FAQ](https://developer.samsung.com/tizen/Smart-TV/FAQ/Smart-TV/How-to-debug.html), but that page specifically discusses 2018 models; it is context, not exact-model proof. The current TV capability report and empty responses are the applicable observations. No assumption is made that enabling Developer Mode enables a general Unix shell.

```sh
python3 tools/collect_board_identity.py TV_PRIVATE_IPV4
```

The CLI uses only the locally retained official macOS SDB 4.2.36 binary at `.local/toolchain/sdb-4.2.36/sdb`, with SHA-256 `05db410d2e36e85147f95b20bae6296a71c54dab0e1ec79f9e11b89c4b6bd2cd`. There is no executable-path or digest override. Missing or mismatched binaries are refused. The [official SDK package](https://download.tizen.org/sdk/tizenstudio/official/binary/sdb_4.2.36_macos-64.zip) is a tool provenance reference, not a TV compatibility guarantee.

The collector requires the exact full-SKU HTTP report, makes one ordinary connection attempt to the supplied private IPv4 on port 26101, and requires exactly one matching `device` entry in SDB's device list. It cannot fall back to another connected device. Only then does it issue these fixed normal-user reads:

1. `uname -m`
2. `uname -r`
3. `getconf LONG_BIT`
4. `cat /proc/cpuinfo`
5. `cat /proc/device-tree/compatible`

Each SDK process has a five-second absolute deadline and 64 KiB stdout limit; stderr is discarded. Budget failures kill only that client process. No shell interpreter, discovery, root command, settings change, installation, reboot, firmware write, arbitrary path, or device-output-derived command is used. Some files or commands may be unavailable to the normal developer account. Failed or empty reads stay unknown; a partial or empty collection is not success. `successful_reads` counts nonempty exit-zero responses, while `validated_reads` counts recognized results; neither proves physical board identity.

Each run creates a new directory under ignored `.local/board-identity`, mode 0700, with mode-0600 `private.json` and `public.json`. Existing collections cannot be overwritten. Raw CPU information can contain serials; raw reads, the supplied address and device-tree strings stay in `private.json`. Never publish that file. The public summary allows only recognized kernel architectures, a numeric kernel-version core, 32/64-bit userspace reports, numeric CPU implementer/part/architecture values a count of reported processor entries, and `source_family_compatible_match` (`true`, `false` or `null`). The last field compares a bounded, NUL-terminated string list with the manually reviewed family-source machine fingerprint `samsung,sdp-pontusm`; malformed or unavailable reads remain `null`. It does not identify the board or establish boot support. Unknown strings, build suffixes and raw-content hashes are omitted. Review even the allowlisted summary before publication.

Kernel architecture and reported userspace bit width answer different questions. CPU implementer/part values identify CPU components, not the complete SoC or board. Processor entries do not establish physical core count. Private device-tree strings require separate provenance review and corroboration before updating the target profile. These reads cannot establish boot ownership, recovery, independent drivers or protected playback.
