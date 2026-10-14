# Validation evidence

Development host, 2026-10-14:

- Python reference/API/source-index suite: 11 passing tests. Covers persistence/restart, stale revisions, concurrent writers, request deduplication, conflicting reuse, undo, invalid document bounds/code/URLs, authentication/Host/Origin, malformed requests, and archive path safety.
- Browser verification: load current revision, change title/theme/content visibility, preview without saving, apply and read back revision 2, undo to original content at revision 3, move focus by keyboard, reject an invalid theme, and successfully apply its correction. The studio explicitly reports that provider launching is preview-only.
- Publication checks: tracked-text checks for private artifact paths, large/binary artifacts and common credential patterns; manual review excludes owner photos, unique identifiers, original private specification, vendor downloads and local tokens/state. Pattern checks are not a comprehensive secret audit.
- Android: `:app:testDebugUnitTest :app:assembleDebug :app:lintDebug` passed locally using verified official Temurin JDK 17, Gradle 8.13, SDK platform 36 and build-tools 35.0.0. Two Android JVM unit tests passed. A development APK was produced; no Android emulator/device runtime test has been performed. Lint completed with zero errors and nine warnings (dependency updates, backup/vector compatibility, synchronous preferences and Kotlin style). The initial build also reported toolchain/deprecation warnings; see the limits below.

Build warnings: the Kotlin `jvmTarget` DSL is deprecated; the newer SDK tool metadata produces an XML-version warning in the pinned build stack; one third-party native library is packaged without symbol stripping. These did not fail compilation, tests or lint.

Still unverified: Android runtime, source-archive contents, exact board/SoC/ABI, independent boot, practical recovery, protected playback, each provider's quality, production agentOS executor/pairing, full household editing and final Samsung-software removal. Use CI and actual-device evidence to update these statuses; do not infer them from host tests.

Development APK SHA-256: `ef1878d4dc155dfe7bcff5aec26907556cf6420499b21751fd2e6b3da8123d16`. This identifies the local debug artifact only; CI debug signing can produce a different digest. The APK and debug keystore are excluded from Git.
