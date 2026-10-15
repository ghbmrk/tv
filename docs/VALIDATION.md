# Validation evidence

Feasibility investigation, 2026-10-15:

- The [selected dependency inspector](../tools/inspect_platform_dependencies.py) ran against the previously hashed family source, recording 12 files in four packages without extraction or execution. The [inventory](../research/platform-dependency-inventory.json) provides nested/file hashes and lexical marker locations; [the verdict](../research/FEASIBILITY.md) separates manually reviewed source behavior from exact-board unknowns.
- A second random-access reader verified all 12 selected-file hashes and every recorded line hash against the archive. A related-model researcher report was pinned and hashed separately; its runtime claims remain author-reported.
- All 25 Python tests pass, including four new dependency-inspection cases for legacy source bytes, metadata-only output, unsafe paths, expansion limits, missing files, selected symlinks and duplicate selected tar entries. The initial sandboxed full-suite attempt could not bind four synthetic HTTP servers; the complete permitted rerun passed.
- Pinned offline Android JVM/build/lint checks pass, with Gradle reusing unchanged build/test outputs. No Android product code changed; existing emulator results remain historical and are not rerun or promoted to target evidence.
- A fixed read-only request to the Bonjour-discovered Samsung candidate still failed with OS error 65 under host-network permission. Its identity and the underlying failure cause remain unverified. Raw responses and endpoint details are excluded from public findings.

Development host, 2026-10-14:

- Python reference/API/source-index suite: 11 passing tests. Covers persistence/restart, stale revisions, concurrent writers, request deduplication, conflicting reuse, undo, invalid document bounds/code/URLs, authentication/Host/Origin, malformed requests, and archive path safety.
- Browser verification: load current revision, change title/theme/content visibility, preview without saving, apply and read back revision 2, undo to original content at revision 3, move focus by keyboard, reject an invalid theme, and successfully apply its correction. The studio explicitly reports that provider launching is preview-only.
- Publication checks: tracked-text checks for private artifact paths, large/binary artifacts and common credential patterns; manual review excludes owner photos, unique identifiers, original private specification, vendor downloads and local tokens/state. Pattern checks are not a comprehensive secret audit.
- Android: `:app:testDebugUnitTest :app:assembleDebug :app:lintDebug` passed locally using verified official Temurin JDK 17, Gradle 8.13, SDK platform 36 and build-tools 35.0.0. Two Android JVM unit tests passed. A development APK was produced. The native qualification package additionally passed four instrumented runtime tests on an official API 36 ARM64 Android TV emulator. These use D-pad activation and cover focus after activity recreation, synthetic document import, fresh-repository read-back, invalid/oversized documents, reset, legacy migration and corrupt-store fallback. The system picker response is stubbed; no physical remote or real provider client is exercised. Lint completed with zero errors and nine warnings (dependency updates, backup/vector compatibility, synchronous preferences and Kotlin style). The initial build also reported toolchain/deprecation warnings; see the limits below.

Build warnings: the original Kotlin `jvmTarget` DSL deprecation has been removed; the newer SDK tool metadata produces an XML-version warning in the pinned build stack; one third-party native library is packaged without symbol stripping. These did not fail compilation, tests or lint.

Still unverified: physical-device Android runtime, actual picker UI and provider launching/playback, complete source/platform correspondence, exact board/SoC/live ABI, independent boot, practical recovery, protected playback, each provider's quality, production agentOS executor/pairing, full household editing and final Samsung-software removal. Use CI and actual-device evidence to update these statuses; do not infer them from host tests.

Development APK SHA-256: `4de09ed6a1411879e861724588c95e7da1fc1556ff02e9803c5030f63562b6f0`. This identifies the latest locally built debug artifact only; CI debug signing can produce a different digest. The APK and debug keystore are excluded from Git.

Runtime environment: Android Emulator 37.2.12, API 36 Android TV ARM64 image revision 4, 1080p virtual profile, 2 GiB guest RAM, host Hypervisor.Framework and SwiftShader. ADB 37.0.1 required its documented `ADB_LIBUSB=1` backend on this Mac. These are functional checks, not target-TV performance measurements.

2026-10-15 continuation:

- PR #1 merged after [its final CI run](https://github.com/ghbmrk/tv/actions/runs/38657468276) passed reference checks, Android JVM/build/lint and four API 36 x86_64 TV instrumented tests. Local ARM64 and CI x86_64 runtime results agree for the tested shell paths.
- Offline Samsung archive: advertised byte count matched, SHA-256 recorded, all 24,883 outer ZIP members passed CRC checks. Bounded nested inspection traversed 71,624 kernel members and recorded four selected files' metadata/hashes without extracting or executing source. See [findings](../research/PONTUS_SOURCE_FINDINGS.md).
- The reference suite now includes three nested-kernel inspection tests for provenance/config interpretation, empty version fields, unsafe paths, symlinks and resource budgets. No Android product code changed in this research package.

Native transaction continuation, 2026-10-15:

- Pinned Android JVM/build/test-APK/lint checks pass. Twelve API 36 ARM64 TV runtime tests pass: seven journal tests and five shell tests. Coverage includes unsaved preview, cancel/apply/undo via D-pad, activity recreation, committed read-back, durable duplicate receipts, conflicting ID reuse, concurrent writers, stale undo, document/history bounds, receipt-capacity refusal, old-store migration and preservation of corrupt databases/documents.
- Python reference suite: 14 tests pass. The native domain is not a paired network service or production agentOS integration; [native transaction semantics](NATIVE_TRANSACTIONS.md) state its exact limits.

Full firmware/offline analysis continuation, 2026-10-15:

- PR #3 merged after [final CI qualification](https://github.com/ghbmrk/tv/actions/runs/38730046944) passed, including all 12 API 36 x86_64 TV runtime tests. Local ARM64 proof remains separate from real-TV qualification.
- The complete 1,465,434,949-byte official update and all five members are hashed and CRC-checked. The bounded MSDU11 parser validates outer-table count/label/range/overlap/coverage constraints without authenticating them as partitions. The reference suite now has 18 tests, adding chunk-boundary marker handling, unsafe paths, CRC damage and malformed MSDU11 tables.
- REA 6.5.0 with Binwalk 3.1.0 passed a synthetic gzip control, then scanned two bounded firmware derivations inside an offline resource-limited Linux ARM64 container. All three reported zlib candidates failed independent decompression checks; no payload or publisher signature is accepted. Ten legacy update-key profiles yielded no recognized metadata header. See [the scoped evidence](../research/FIRMWARE_AND_BOOT_FINDINGS.md).

Read-only target identification preparation, 2026-10-15:

- The combined reference suite has 21 passing tests. Three new synthetic identification tests cover field allowlisting/removal of unique identifiers, private-address constraints, exact GET behavior, no authorization headers, refusal of redirects and response-size bounds. The CLI accepts no arbitrary endpoint/path or write operation; raw errors/responses are not emitted or saved.
- A bounded standard SSDP attempt failed with OS error 65 using both default and explicit physical-interface paths. No real TV endpoint or reported fields were obtained. No networking/privacy/VPN/TV settings were changed. Actual endpoint behavior remains unverified; the required next input is a reachable address for this TV.
- PR #4's [final CI run](https://github.com/ghbmrk/tv/actions/runs/38731304825) passed all reference and Android checks, including 12 x86_64 TV runtime tests, before merge.

Local collections and artwork continuation, 2026-10-15:

- The complete host suite passes 29 tests. New coverage includes PNG CRC/scanline/expansion validation, immutable upload retries, integrity and quota refusal, missing assets, schema v2 references, preview/apply/restart/undo, authenticated image endpoints and exact portable ZIP contents.
- Android JVM checks, debug/test APK assembly and lint pass. All 16 API 36 ARM64 TV runtime tests pass, including four artwork tests. Coverage adds actual decoded pixel read-back, a 129-image ZIP and short stream reads, malformed paths/bundles, unsaved import, hidden entries, D-pad gallery navigation and focus restoration, slideshow advancement/pause, restart and undo. A focused rerun of all four artwork tests also passes with an added STARTED/RESUMED lifecycle suspension check. System picker responses remain stubbed; no streaming client or physical TV is exercised.
- Browser verification used a generated 1280×720 test pattern and isolated local state: PNG chooser import, unsaved preview, collection/image rendering with preserved aspect ratio, apply/read-back at revision 2 and undo to v1 at revision 3. Export returned its success state; the in-app browser's download-event hook timed out, so downloaded-file delivery is not claimed from that UI check. The HTTP integration test independently validates the actual ZIP bytes and member contents.
- The pre-design-iteration local debug APK SHA-256 was `a07136183a040183918bc0bedd49361fcfd87a9818c6aeb856ad1786c01d2141`. Artifact bytes, generated images, screenshots and local state remain outside Git.
- No TV connections, settings changes, installs or persistent hardware writes occurred in this implementation continuation. Native gallery rendering does not qualify low-power Art Mode, HDR artwork, original remote hardware, target responsiveness, native streaming quality or agentOS production control.

Local studio and immersive artwork refinement, 2026-10-15:

- Replaced the primary JSON workbench with visual title, appearance, scale, interval, visibility and entry-order controls. Preview and Save remain explicit; advanced JSON remains available. The preview and editing actions stay visible on desktop, and a 390 px viewport has 390 px content width with a 346 px preview (no horizontal page overflow).
- Browser checks with isolated state verified title/theme edits, hidden YouTube, reordered Prime Video, preview, save/read-back at revision 4, and undo at revision 5. A generated PNG was imported and rendered without cropping; artwork controls hid after inactivity and Enter revealed them while retaining the viewer. The saved gallery survived a studio reload and reconnect. Screenshots and generated test data remain private local artifacts.
- The 29-test host suite, Android JVM tests and lint pass. All 16 API 36 ARM64 runtime tests pass after fixing a reveal-key release that initially activated the newly focused Back button. Coverage now verifies unobstructed artwork and consumes the complete reveal gesture. Android uses its accessibility timeout recommendation.
- Static resource inspection found no external studio assets or network destinations. Android still declares no network permission and disables platform backup. This is a source-level boundary, not a claim of packet-capture qualification for streaming providers or the eventual device firmware. No TV connection or modification occurred.
- The final browser typography check changed text scale from 1.0 to 1.5 and measured the Home heading from 33.28 px to 49.92 px. Fixed the previous preview styling that left explicit pixel sizes unaffected by inherited scale.

Native Home refinement, 2026-10-15:

- PR #7 passed [hosted reference and Android checks](https://github.com/ghbmrk/tv/actions/runs/38766776198) before merge.
- Home now prioritizes viewing; file import, restore and undo live in Settings. Pending preview and uncertain-change controls stay visible. Settings retains the current experience context, survives recreation, and Back restores the previously selected Home/collection tile. App availability comes from an observable local activity catalog, not hard-coded success assumptions.
- All 17 API 36 ARM64 runtime tests pass, including 30 repeated Settings/Home round trips, per-round focus assertions, rendered focus-color pixel verification, Settings recreation and missing Netflix activity presentation. Host suite: 29 passing tests. Android JVM and lint pass. The initial Settings context regression was found and corrected before publication.
- The instrumented debug test records real frame durations and harness-inclusive round-trip time. Decorative focus scaling and the full-screen gradient were removed. Measurements are emulator diagnostics and do not qualify physical remote latency, release frame budgets or streaming performance.
- A subsequent bounded read-only request again reported the exact SKU and Developer Mode enabled; the official SDB handshake returned failure. No TV shell commands, settings changes, installs or persistent hardware writes occurred. See the sanitized target observation record.
- Screenshot review found semantic selection without a visible highlight in the headless test environment. Tile color now follows its observed focus explicitly; the runtime test verifies both the focus node and a pixel inside its rendered tile.
- The final retained-Home implementation passes the complete native suite. Home is not removed when Settings opens; hidden descendants cannot receive focus or expose semantics. The heading and action feedback remain outside the scrolling body. Ordinary success notices expire; errors and unconfirmed operations remain visible.
- The final [synthetic frame record](../research/native-home-emulator-diagnostics.json) retains raw samples, component distributions, report-drop count and both APK digests. The focused test rerun also passes; the screenshot verifies visible selection after routine success feedback has expired.

## Native control bridge continuation — 2026-10-15

- All 24 API 36 ARM64 TV runtime tests pass, including seven real-IPC bridge cases. Android JVM tests and lint pass using the pinned offline toolchain. The 29-test host suite passes with loopback test listeners permitted.
- New runtime evidence covers a separate domain PID; denied binding and denied forwarded Binder use from another UID; one-way effect rejection; concurrent callers with exactly one base-revision winner; durable receipts after domain-process death; idempotent default restore; expiry while blocked on a writer; PNG digest/descriptor bounds and byte read-back; live Home refresh and stale manual-preview refusal. Picker results remain synthetic.
- No TV connection, install, settings change, reboot, exploit or hardware write occurred. Launcher and bridge retain no network permission. A same-signature controller under a separate application UID, paired transport, capture enforcement and broker dispatch still need independent qualification; instrumentation's successful calls use the target app UID.
- The owner quality/continuation rule is recorded in `AGENTS.md`. Emulator success does not establish original-board Android support, provider quality, remote hardware, target speed or complete agentOS interaction.

## Separate controller qualification — 2026-10-15

- The complete 25-test ARM64 TV suite passes with a separately installed owner-signed caller under a different UID. It binds to the domain service, edits the saved experience, reads back the exact document, retries the same ID without a second commit and restores the original document. The unpermitted test application cannot use that fixture as a privileged relay. Android JVM checks and both app/probe lint pass.
- The probe is marked `testOnly`, has no release variant, network permission or backup, and is installed only as `androidTestUtil`. Manifest inspection confirms the launcher also retains no network permission. Neither artifact is a paired network controller.
- An additional manual-preview cancellation case checks that an intervening external commit becomes the displayed saved state after Cancel. The final focused nine-case IPC suite verifies this alongside the other control boundaries; hosted full-suite verification remains required.

## Lossless document boundary — 2026-10-15

- A new regression failed on the original implementation: two different unpaired-surrogate documents encoded to the same replacement bytes while parsing accepted them. Native parsing now rejects malformed Unicode before fingerprinting, labels reject escaped unpaired surrogates, and file/bundle import decoding reports invalid UTF-8. Valid emoji remain supported; Android's label bound now counts Unicode code points, matching the host.
- The host suite passes all 30 tests. Four native JVM tests cover the shared format, invalid imports, the demonstrated fingerprint alias, strict file decoding and the 120/121-character supplementary-Unicode boundary. The full 26-case ARM64 runtime suite passed after the text fix; the final focused nine-case IPC rerun additionally covers definite invalid responses for malformed JSON, timestamp overflow and a correct-CRC PNG with invalid zlib data. These validation failures remain distinct from an uncertain committed effect.
- No target TV access or changes occurred. Hosted full-suite checks remain necessary before merge. These checks do not establish board/DRM/provider support or production agentOS control.
