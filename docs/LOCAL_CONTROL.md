# Paired local control

The separate `:control` Android app connects an owner-approved local executor to the native experience journal. It supports the current Home, collection and artwork operations through mutual TLS and the signature-protected Binder bridge. The launcher retains no network permission. This is an Android development implementation; it is not an installed Samsung port or a qualified agentOS broker route.

## Pair with the physical remote

Use an authorized Android emulator/development target with both APKs signed by the same owner key. These APKs cannot install Android onto stock Samsung Tizen. The [original TV deployment gates](deployment/PLAN.md) still apply.

1. Build `:app:assembleDebug` and `:control:assembleDebug` with the pinned workstation toolchain. Install them only on the authorized Android development target. Debug signing is development authority, not a production identity policy.
2. Open Home → Settings → Household control. Home discovers the installed controller activity and checks its signing identity before opening it.
3. Select **Export TV certificate**. Transfer that public PEM certificate to the isolated executor. The private TV key remains in Android Keystore and is never exported.
4. On the executor, use Python linked to OpenSSL 3 or later. Run `python3 -m sovereign_tv.control_client identity .local/executor`. This creates a private key and public certificate offline; it refuses to replace existing material. Keep the directory private. Transfer only `client-public.pem` to the Android target through its normal file mechanism.
5. Select **Import agent certificate** on the TV. Compare the complete SHA-256 certificate fingerprint with the executor's displayed fingerprint. The review explains the editing/read scope and initially focuses **Cancel**. Select **Trust this agent** to approve it. Pairing still leaves the listener off.
6. Select **Enable on** the intended private IPv4 interface. The service listens on that specific address at port 9443. It uses a visible connected-device foreground service and continues while the controller UI is closed. There is no boot receiver, automatic restart, public listener or network pairing operation.

Only one certificate is trusted. Remove it locally before approving a replacement. Corrupt/expired trust disables authorization; it cannot be silently overwritten through import. **Remove agent** closes connections and waits for an already-started command before completing revocation. After that confirmation, an admitted old session cannot apply another change. **Turn local control off** closes the listener but is not rollback of a command already started; reconcile any lost reply.

The controller UI and Home remain usable offline. Starting the controller after process death/reboot is currently an explicit owner action. This service does not establish standby wake or availability when Android is stopped.

## Configure the isolated executor

Create a private profile beside the exported certificates and key. This example contains placeholders; no device address or identity belongs in the public repository.

```json
{"address":"TV_PRIVATE_IPV4","port":9443,"device_certificate":"tv-public.pem","client_certificate":"executor/client-public.pem","client_key":"executor/client-key.pem"}
```

`Client.from_profile(path)` accepts an explicit private IPv4 address and the configured port. It trusts only the supplied TV certificate, verifies its exact certificate digest, and uses the client key for mutual TLS. DNS, public CA trust, first-contact trust, cloud discovery and automatic effect retries are absent. The key must be a regular file owned by the current user with no group/other permissions. The system Python on some Macs uses an older LibreSSL runtime and is explicitly unsupported by this client; use a Python linked to OpenSSL 3 or later.

Example executor-side read:

```python
import time
from sovereign_tv.control_client import Client
client = Client.from_profile('.local/tv-control.json')
response, image = client.request('state', expires_at_ms=int(time.time() * 1000) + 10000)
```

Effects require a caller-supplied stable request ID. An uncertain transport result raises `Unconfirmed`; it never generates a new ID or repeats the command. Query `receipt` with the original ID and a fresh read expiry, then compare the receipt with current state. Asset upload retries use the same content hash. CLI requests use `python3 -m sovereign_tv.control_client request PROFILE REQUEST_JSON`; image downloads require an explicit, new private output path.

This client is for the owner/isolated executor. An agentOS guest must not receive its profile, key, socket access or direct invocation capability. Broker dispatch, operation classification, grants, audience/private-data routing, capture policy and event integration still require the owning agentOS team's reviewed implementation. No agentOS repository files are changed here.

## Protocol and limits

The provisional transport is one typed request per TLS connection, using TLS 1.2/1.3 and an exact pinned self-signed identity at each end. A four-byte unsigned network-order length precedes each UTF-8 JSON frame. Request metadata is a strict flat JSON object; duplicate fields, nonstandard syntax, undeclared fields and trailing content are rejected. JSON metadata is bounded to 512 KiB to accommodate an escaped 64 KiB document. No paths, intents, executable payloads, URLs or shell commands are accepted.

Every request contains `v=1`, the pinned certificate digest as `device_id`, `operation`, and integer `expires_at_ms`. The deadline is strictly future UTC milliseconds, at most 30 seconds away. The native journal rechecks the converted monotonic deadline after obtaining its writer lock and after validation.

| Operation | Additional request fields |
|---|---|
| `capabilities`, `state` | None. |
| `preview` | `base_revision`, exact `document` string. Validation only; not displayed or saved. |
| `apply` | `request_id`, `base_revision`, exact `document` string. |
| `undo` | `request_id`, `base_revision`, `restore_revision`. |
| `restore_default` | `request_id`, `base_revision`. |
| `receipt` | `request_id`. |
| `artwork.put` | `sha256`, integer `bytes`; followed by one binary frame of exactly that length. |
| `artwork.open` | `sha256`. |

Responses contain `v`, `device_id`, `status`, and optional `result` with the native domain metadata. An artwork read includes `blob_bytes` and a following binary frame, both bounded to 8 MiB. The client checks the returned bytes against the requested content hash. Uploaded content is hashed before passing a bounded regular-file descriptor to the native PNG validator; controller cache files are removed after use and abandoned upload files are cleaned on service start.

Validation completes before Binder invocation. A later exception closes the connection rather than claiming that an effect was refused or undone. Durable receipts and revisions remain in the native SQLite journal, not a second controller database. [Native transaction semantics](NATIVE_TRANSACTIONS.md) define exact retries, conflicts, history/receipt capacity and corruption preservation.

The listener allows two concurrent workers with no unbounded request queue, a four-connection listen backlog, five-second socket read timeouts, a ten-second request-input budget and a 45-second absolute connection lifetime. Parsing and network work stay outside the launcher's UI/frame path. Accept and command workers request Android background CPU priority. Cancelled watchdog tasks are removed immediately, and shutdown closes sockets and terminates workers/timers. Revocation serializes only with invocation, not a peer slowly supplying a request. Controller code does not log request bodies, exception text, certificates, addresses or assets.

An artwork read returns image content. The capability response explicitly reports that broker capture enforcement is absent; the future agentOS route must enforce image capture and private-data policy before exposing this operation. There is no screen capture endpoint or access to protected provider frames, accounts, navigation, hardware settings or DRM material.

## Verification and platform boundary

Runtime tests use a separate app UID, Android Keystore keys, real TLS sockets and the real Binder journal. They exercise paired edits/read-back/undo, exact retries, lost replies, unpaired/changed-device denial, revocation after handshake, corrupt trust, strict request framing, artwork transfers, remote approval/cancel/revocation and foreground-service survival outside its activity. Picker responses are synthetic. The host suite independently tests the Python TLS client.

`tools/qualify_control_interop.py --serial EMULATOR_SERIAL` installs only on a target reporting `ro.kernel.qemu=1`. It creates temporary executor keys offline, transfers only the public certificate to a test fixture, forwards the emulator's loopback endpoint and proves Python/OpenSSL-to-Android/Keystore editing, receipt lookup, exact retry and undo. It does not qualify a real LAN or the original TV. Test fixtures are packaged exclusively in the test APK.

The current target SDK is 36. Android 17/SDK 37 requires a runtime local-network permission path before increasing that target; the platform's [local-network guidance](https://developer.android.com/privacy-and-security/local-network-permission) distinguishes the versions. The foreground service follows [connected-device requirements](https://developer.android.com/develop/background-work/services/fgs/service-types). Keystore key material is non-exportable through the app API; hardware-backed protection on the eventual TV remains unverified. TLS uses the platform's prehashed signing operation, with the digest authorization described in [Android's key protection reference](https://developer.android.com/reference/kotlin/android/security/keystore/KeyProtection.Builder).
