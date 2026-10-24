# Secure-world replacement boundary

Observed 2026-10-24. Offline family-source and public-document review only. No TV access, module loading, secure-monitor invocation, key inspection or vendor-code execution occurred. The installed secure OS and its version remain unverified.

## Family-source evidence

The [dependency inventory](platform-dependency-inventory.json) now includes three additional bounded files from the acquired PontusM source: `tzdev_main.c`, its `CMakeLists.txt`, and the driver package specification. Their hashes and lexical locations reproduce with `tools/inspect_platform_dependencies.py`. Manual control-flow review, rather than marker matching alone, supports these findings:

| Location | Observation | Consequence |
| --- | --- | --- |
| `tzdev_smc.c`, lines 141-175 | Monitor initialization requests a secure-OS UUID and rejects a mismatching identity. | The normal-world driver expects a particular monitor interface; implementing a generic TrustZone call transport does not establish compatibility. No accepted boot authority is identified. |
| `tzdev_main.c`, lines 2782-2831 | Kernel-information exchange supplies and checks a structure size and ABI version; an optional log labels the returned build information TrustWare. | TrustWare is a family-specific lead. This is not an observed running version, nor a proof that the named update sections contain that implementation. |
| Same file, lines 2911-3118, 3183 | Module initialization deletes a marker, initializes monitor communication, fetches kernel information, initializes storage/RPC processing and creates/truncates a marker. | Loading the module to obtain version information is an active initialization sequence, not a passive read. Initialization itself has filesystem effects. Downstream secure-world/storage effects have not been bounded. |
| Same file, lines 2845-2908 | Marker helpers invoke unlink or create/read-write/synchronous/truncate file operations. | These are concrete file effects, not evidence of a fuse, rollback counter or RPMB write in these helpers. Do not conflate them. |
| `CMakeLists.txt`, lines 1-7, 18-31, 77-83; package specification, line 26 | Build configuration selects board definitions, references external `trustzone-common` headers, and conditionally selects RPMB behavior. | This is a normal-world integration package, not a standalone secure OS or complete board-support package. Build options do not establish the target's active RPMB policy. |

The package version `3.0` belongs to `trustzone-drivers`; it must not be relabeled as the installed TrustWare version. A declaration that the driver is nonremovable likewise does not establish immutable hardware or prove that a replacement system is impossible.

## Public TV-specific documentation and scope

The [V9.0 security target, pages 9-10](https://www.commoncriteriaportal.org/nfs/ccpfiles/files/epfiles/Smart%20TV%20and%20Monitor%20Security%20Solution%20V9.0%20for%20Samsung%20Knox%20Security%20Target%20Lite_V1.1.pdf) lists Tizen 10.0/Linux 5.4.261 32-bit and Samsung-developed TrustWare V3.5.0 as operating environment. Its hardware table states minimum requirements, not the fitted LS03F chip. Its evaluation target consists of security libraries and guidance; Update Manager, SQLite, OpenSSL and the crypto module are outside that physical scope.

The independent scheme's [certification report, page 11](https://www.commoncriteriaportal.org/nfs/ccpfiles/files/epfiles/KECS-CR-26-10%20Smart%20TV%20and%20Monitor%20Security%20Solution%20V9.0%20for%20Samsung%20Knox%20%28eng%29.pdf) confirms that boundary and explicitly limits evaluation to the identified software versions. It does not qualify the household TV, its boot ROM, independent OS acceptance or replacement recovery. Hashes and reviewed pages are recorded in [the evidence record](secure-world-evidence.json); complete relevant pages were rendered and visually reviewed.

The retained household SDK observation reports Tizen 9.0, not this document's Tizen 10.0. Neither a shared kernel version nor the TrustWare name closes that gap. Mobile Knox/TEEgris boot policy is not applied to this TV by analogy.

## Implementation decision

Treat the secure OS, monitor, normal-world transport, secure storage, trusted applications and provider provisioning as separate replacement dependencies. The existing wrapper/driver source supplies interface evidence; rebuilding it while keeping Samsung secure-world code would fail the owner's removal requirement.

An independent candidate must demonstrate boot authority, exact hardware support, interrupt/shared-memory/power behavior, independent storage/provisioning and the required protected-media applications. No candidate is selected or qualified by these findings. Monitor UUID/ABI checks are compatibility checks inside an existing kernel, not authorization to boot an independently built secure OS.

Before any future experiment, review the full initialization path and all storage/controller effects. Do not load this module, read its new sysfs entries or issue monitor calls on the household TV to fill missing fields. Board identity, earliest-stage trust, independent recovery and legitimate provider qualification remain indispensable dependencies. The mounted panel's inaccessible version label remains unknown; no movement or enclosure opening is requested.
