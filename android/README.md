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

Export a saved experience from the host studio, transfer that ZIP (or a legacy JSON document) to the Android development device through its normal file mechanism, then open Settings → Import experience. Apply preview and Cancel preview remain available above the viewing surface during an edit. The shell handles titles, themes, row/grid layouts, visible tiles, app/artwork collections, local slideshow timing and text scale. Settings → Import artwork also stages a local PNG without applying it. Settings contains Restore default and Undo last change. Back returns to the prior Home/collection and restores its selected tile; Settings survives activity recreation. [Artwork and bundle limits](../docs/COLLECTIONS_AND_ARTWORK.md) apply. Broader widgets/settings, production Home registration and the paired control service remain pending. Streaming apps are not bundled; playback/DRM/UHD/HDR support has not been established. Debug APKs are development artifacts only.

Build pins: [AGP 8.13 compatibility](https://developer.android.com/build/releases/agp-8-13-0-release-notes), [Compose BOM](https://developer.android.com/develop/ui/compose/bom), [Compose for TV releases](https://developer.android.com/jetpack/androidx/releases/tv). These user-interface build pins do not select the eventual TV's Android/kernel branch.

## Runtime qualification

The native shell uses an activity-retained view model and a single background worker for document I/O, parsing, transactional persistence, legacy configuration migration and installed-app discovery. Returning to the activity restores the last focused tile using stable IDs. Home remains composed behind Settings, with its focus and semantics disabled while hidden. Its selection and list position survive the return. Home renders without waiting for app discovery. App tiles show CHECKING, INSTALLED or NOT INSTALLED from the local launch-activity catalog; INSTALLED does not qualify provider sign-in or playback. These mechanisms do not establish actual-TV latency or remote compatibility.

On a dedicated API 36 Android TV emulator, run:

```sh
gradle -p android :app:connectedDebugAndroidTest
```

Use a test-only environment with no owner accounts or other attached devices. The suite exercises D-pad focus/recreation, synthetic document import, persisted read-back, invalid/oversized input rejection, default reset, legacy migration and corrupt-store fallback. The document picker response is stubbed with an exported read-only fixture provider that exists only in the test APK; actual system picker navigation and provider playback are outside this suite. Tests never launch a real streaming client.

The CI workflow runs the same suite on an x86_64 Android TV emulator, alongside Python tests, Android JVM tests, APK assembly and lint. It explicitly requests `platform-tools` rather than the setup action's retired `tools` package default.

The debug APK also contains a disabled-by-default `LabHome` activity alias. Installation does not select it or disable another launcher; release builds contain no lab alias. `LabHomeRuntimeTest` is restricted to an emulator and two known stock TV launcher packages. It saves the current Home role and package-enabled state, enables the lab alias, temporarily disables the stock launcher package in that emulator, and selects the lab Home. It exercises three actual system Home-button returns from the separate-UID synthetic TV app, requiring the original activity and selected card to survive. Nested `finally` blocks restore the exact stock package state, previous Home role and lab alias state, with read-back assertions. No app is uninstalled; this temporary package switch is confined to the account-free emulator.

The emulator package switch is needed because the lab image's privileged Home has priority 2 while the effective priority of the third-party lab candidate is 0. Android's [resolver chooses differing priorities before saved preferences](https://github.com/aosp-mirror/platform_frameworks_base/blob/99b01a65cc4c104933788b3143285ab6bae65827/services/core/java/com/android/server/pm/ResolveIntentHelper.java); a successful Home-role command alone did not change the observed resolver. This fixture models a platform whose Home belongs to the project. It is not a deployment procedure, stock-platform takeover qualification, Samsung Home-button reception test, boot or standby test. Run it only in the dedicated account-free emulator described above.

Native editing now uses a revision journal with preview/apply/cancel, restart-safe receipts and undo. See [transaction semantics and storage limits](../docs/NATIVE_TRANSACTIONS.md). The runtime suite also covers concurrent edits, retained-history limits, durable replay, stale undo, and corruption preservation.

`HomeExperienceTest` exercises 30 Settings/Home round trips, verifies selection restoration after every Back, and records `FrameMetrics.TOTAL_DURATION` plus full test round-trip durations. It writes `home-diagnostics.json` and `home-proof.png` into the test app’s private files directory. These are synthetic debug-emulator diagnostics: round trips include focus requests, injected keys and test idle waits. They are not physical button-to-display latency or release performance budgets.

The owner-signed `IExperienceControl` bridge runs in a dedicated `:domain` process and uses the same journal as manual editing. Its [contract and authority limits](../docs/NATIVE_TRANSACTIONS.md#owner-signed-native-bridge) describe binding permission, deadlines, receipts, file descriptors and reconciliation. `ControlRuntimeTest` uses actual IPC and an unauthorized fixture process; it kills only this test application's domain process to verify durable receipts. No test binds to or changes the Samsung TV.

Runtime qualification automatically installs `:control-probe`, a debug-only, test-only APK signed by the same development key under a distinct UID. It verifies authorized cross-application edits, durable retries and read-back. An unpermitted fixture verifies the probe cannot relay its requests. The probe has no network permission or release variant and is absent from the launcher artifact. CI lints it separately.

## Paired local controller

Build `:control:assembleDebug` and `:control:assembleDebugAndroidTest` alongside Home. This separate app holds network permission and reaches Home through the owner-signature Binder boundary; Home still has no network permission. Settings → Household control opens its discovered same-signature activity. [Pairing, executor setup and exact protocol limits](../docs/LOCAL_CONTROL.md) cover remote approval, revocation and lost-reply reconciliation. Run `:control:connectedDebugAndroidTest` for its Android runtime suite and `tools/qualify_control_interop.py --serial EMULATOR_SERIAL` with Python/OpenSSL 3 for the emulator-only cross-runtime probe. Neither command installs on the Samsung TV.
