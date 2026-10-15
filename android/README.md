# Native Android TV shell prototype

A Kotlin/Compose for TV application renders `experience.json`, supports focusable D-pad controls, previews a validated JSON experience through Android's document picker, applies or cancels it, and offers restore-default and persistent undo. Installed leanback activities are discovered before provider launch; package hints are not provider qualification. The manifest has no network permission and registers a TV launch entry, not a replacement system Home intent.

Build on a workstation with JDK 17, Android SDK platform 36/build-tools 35.0.0 and Gradle 8.13:

```sh
gradle -p android :app:assembleDebug
```

A Gradle wrapper is not committed yet. Use the exact Gradle version above or the CI workflow. Build outputs are under `android/app/build/outputs/apk/debug/`. With an authorized Android TV emulator/development device visible in `adb devices`, install the APK:

```sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n local.sovereigntv/.MainActivity
```

These commands target Android development devices only. They do not install onto stock Samsung Tizen or flash an operating system. Do not use `adb` against the TV until an independently qualified Android target exists.

Export a saved experience from the host studio, transfer that ZIP (or a legacy JSON document) to the Android development device through its normal file mechanism, then choose Import experience and Apply preview or Cancel preview. The shell handles titles, themes, row/grid layouts, visible tiles, app/artwork collections, local slideshow timing and text scale. Import artwork also stages a local PNG without applying it. [Artwork and bundle limits](../docs/COLLECTIONS_AND_ARTWORK.md) apply. Broader widgets/settings, production Home registration and the paired control service remain pending. Streaming apps are not bundled; playback/DRM/UHD/HDR support has not been established. Debug APKs are development artifacts only.

Build pins: [AGP 8.13 compatibility](https://developer.android.com/build/releases/agp-8-13-0-release-notes), [Compose BOM](https://developer.android.com/develop/ui/compose/bom), [Compose for TV releases](https://developer.android.com/jetpack/androidx/releases/tv). These user-interface build pins do not select the eventual TV's Android/kernel branch.

## Runtime qualification

The native shell uses an activity-retained view model and a single background worker for document I/O, parsing, transactional persistence, legacy configuration migration and installed-app discovery. Returning to the activity restores the last focused tile using stable IDs. Home renders without waiting for app discovery. These mechanisms do not establish actual-TV latency or remote compatibility.

On a dedicated API 36 Android TV emulator, run:

```sh
gradle -p android :app:connectedDebugAndroidTest
```

Use a test-only environment with no owner accounts or other attached devices. The suite exercises D-pad focus/recreation, synthetic document import, persisted read-back, invalid/oversized input rejection, default reset, legacy migration and corrupt-store fallback. The document picker response is stubbed with an exported read-only fixture provider that exists only in the test APK; actual system picker navigation and provider playback are outside this suite. Tests never launch a real streaming client.

The CI workflow runs the same suite on an x86_64 Android TV emulator, alongside Python tests, Android JVM tests, APK assembly and lint. It explicitly requests `platform-tools` rather than the setup action's retired `tools` package default.

Native editing now uses a revision journal with preview/apply/cancel, restart-safe receipts and undo. See [transaction semantics and storage limits](../docs/NATIVE_TRANSACTIONS.md). The runtime suite also covers concurrent edits, retained-history limits, durable replay, stale undo, and corruption preservation.
