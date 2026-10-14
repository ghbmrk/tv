# Native Android TV shell prototype

A Kotlin/Compose for TV application renders `experience.json`, supports focusable D-pad controls, imports a validated JSON experience through Android's document picker, saves it locally, and offers restore-default. Installed leanback activities are discovered before provider launch; package hints are not provider qualification. The manifest has no network permission and registers a TV launch entry, not a replacement system Home intent.

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

Export a saved experience from the host studio, transfer that JSON to the Android development device through its normal file mechanism, then choose Import experience. The current shell handles titles, theme, row/grid layouts, visible tiles and text scale. Artwork collections/timing, broader widgets/settings, production Home registration and the paired control service remain pending. Streaming apps are not bundled; playback/DRM/UHD/HDR support has not been established. Debug APKs are development artifacts only.

Build pins: [AGP 8.13 compatibility](https://developer.android.com/build/releases/agp-8-13-0-release-notes), [Compose BOM](https://developer.android.com/develop/ui/compose/bom), [Compose for TV releases](https://developer.android.com/jetpack/androidx/releases/tv). These user-interface build pins do not select the eventual TV's Android/kernel branch.
