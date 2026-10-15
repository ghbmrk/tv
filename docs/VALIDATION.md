# Validation evidence

Development host, 2026-10-14:

- Python reference/API/source-index suite: 11 passing tests. Covers persistence/restart, stale revisions, concurrent writers, request deduplication, conflicting reuse, undo, invalid document bounds/code/URLs, authentication/Host/Origin, malformed requests, and archive path safety.
- Browser verification: load current revision, change title/theme/content visibility, preview without saving, apply and read back revision 2, undo to original content at revision 3, move focus by keyboard, reject an invalid theme, and successfully apply its correction. The studio explicitly reports that provider launching is preview-only.
- Publication checks: tracked-text checks for private artifact paths, large/binary artifacts and common credential patterns; manual review excludes owner photos, unique identifiers, original private specification, vendor downloads and local tokens/state. Pattern checks are not a comprehensive secret audit.
- Android: `:app:testDebugUnitTest :app:assembleDebug :app:lintDebug` passed locally using verified official Temurin JDK 17, Gradle 8.13, SDK platform 36 and build-tools 35.0.0. Two Android JVM unit tests passed. A development APK was produced. The native qualification package additionally passed four instrumented runtime tests on an official API 36 ARM64 Android TV emulator. These use D-pad activation and cover focus after activity recreation, synthetic document import, fresh-repository read-back, invalid/oversized documents, reset, legacy migration and corrupt-store fallback. The system picker response is stubbed; no physical remote or real provider client is exercised. Lint completed with zero errors and nine warnings (dependency updates, backup/vector compatibility, synchronous preferences and Kotlin style). The initial build also reported toolchain/deprecation warnings; see the limits below.

Build warnings: the original Kotlin `jvmTarget` DSL deprecation has been removed; the newer SDK tool metadata produces an XML-version warning in the pinned build stack; one third-party native library is packaged without symbol stripping. These did not fail compilation, tests or lint.

Still unverified: physical-device Android runtime, actual picker UI and provider launching/playback, complete source/platform correspondence, exact board/SoC/live ABI, independent boot, practical recovery, protected playback, each provider's quality, production agentOS executor/pairing, full household editing and final Samsung-software removal. Use CI and actual-device evidence to update these statuses; do not infer them from host tests.

Development APK SHA-256: `8f87a008d0417973d4ac04458ab99b1ffa04e298abb30d3d8e22a856f2cc99a7`. This identifies the latest locally built debug artifact only; CI debug signing can produce a different digest. The APK and debug keystore are excluded from Git.

Runtime environment: Android Emulator 37.2.12, API 36 Android TV ARM64 image revision 4, 1080p virtual profile, 2 GiB guest RAM, host Hypervisor.Framework and SwiftShader. ADB 37.0.1 required its documented `ADB_LIBUSB=1` backend on this Mac. These are functional checks, not target-TV performance measurements.

2026-10-15 continuation:

- PR #1 merged after [its final CI run](https://github.com/ghbmrk/tv/actions/runs/38657468276) passed reference checks, Android JVM/build/lint and four API 36 x86_64 TV instrumented tests. Local ARM64 and CI x86_64 runtime results agree for the tested shell paths.
- Offline Samsung archive: advertised byte count matched, SHA-256 recorded, all 24,883 outer ZIP members passed CRC checks. Bounded nested inspection traversed 71,624 kernel members and recorded four selected files' metadata/hashes without extracting or executing source. See [findings](../research/PONTUS_SOURCE_FINDINGS.md).
- The reference suite now includes three nested-kernel inspection tests for provenance/config interpretation, empty version fields, unsafe paths, symlinks and resource budgets. No Android product code changed in this research package.
