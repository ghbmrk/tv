plugins { id("com.android.application") }
android {
    namespace = "local.sovereigntv.controlprobe"
    compileSdk = 36
    defaultConfig { applicationId = "local.sovereigntv.controlprobe"; minSdk = 26; targetSdk = 36; versionCode = 1; versionName = "test-only" }
    buildFeatures { aidl = true }
    sourceSets.getByName("main").aidl.srcDir("../app/src/main/aidl")

}

// Never ship the probe; it is a separate-UID instrumentation fixture only.
androidComponents { beforeVariants(selector().all()) { it.enable = it.buildType == "debug" } }

val probeApk by configurations.creating { isCanBeConsumed = true; isCanBeResolved = false }
artifacts.add(probeApk.name, layout.buildDirectory.file("outputs/apk/debug/control-probe-debug.apk")) { builtBy("assembleDebug") }
