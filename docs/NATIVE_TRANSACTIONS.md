# Native experience transactions

The Android domain layer implements preview, revision-checked apply, durable receipts and conflict-safe undo. Remote-operated import stages an unsaved preview; Apply commits it, Cancel restores the saved view, and Undo last change appends the preceding document as a new revision. A preview survives activity recreation through the retained view model; process death discards only the unsaved preview. Undo remains available after process restart from saved history.

`ExperienceRepository` is the domain facade. Home calls run on its background worker; bridge calls run in the dedicated domain process:

| Operation | Inputs/result |
|---|---|
| Load | Parsed experience, original document, revision and recovery flags. |
| Preview | Expected revision and document; staged result without a saved revision. |
| Apply | Stable request ID, expected revision and document; durable receipt. |
| Receipt | Request ID; original committed receipt or absence. |
| Undo | Stable request ID, expected revision and retained earlier revision; durable receipt. |
| Apply default | Stable request ID and expected revision; same transaction rules as any edit. |

`ExperienceJournal` stores revisions and receipts in app-private SQLite. Initial import from the former AtomicFile or preferences store occurs inside the first journal transaction. Subsequent legacy-file changes cannot override it. Old files remain private evidence rather than being deleted implicitly. Invalid legacy content seeds a default document with a recovery flag; an explicit default/apply clears that flag in a new revision.

Each effect validates before saving, serializes writers in a database transaction, checks a prior receipt before checking the current revision, and commits the new document and receipt together. Reusing an ID with different arguments fails. Undo never overwrites an intervening edit. Digests distinguish apply from undo. Native apply fingerprints include the SHA-256 of the exact UTF-8 document; clients retry the same document bytes. This Kotlin domain interface does not claim wire compatibility with the Python server's canonical-JSON request digest.

The latest 128 documents are retained. Receipts are retained up to an explicit 10,000-effect capacity; reaching it refuses new effects while preserving receipts and state. Receipts are never silently evicted to permit replay. Production maintenance/epoch rotation must be designed before enabling a continuously reachable service; the current shell and native bridge have no network endpoint. Request IDs are bounded to 64 characters and documents to 64 KiB. Quotas are not authorization.

The UI retains a pending effect's ID and arguments until receipt/state reconciliation succeeds. An unconfirmed result offers Retry change using the same request; it never claims the previous experience survived an uncertain commit. A confirmed stale-revision refusal reloads saved state. Read-back checks the document hash when the receipt identifies the current revision; a newer saved revision is reported explicitly.

Android's default corrupt-database handler can delete evidence. This journal instead preserves it. An unreadable journal or stored document exposes a default Home for manual navigation with editing disabled and revision zero; history is not rebuilt and receipts are not discarded. Repair/export is an explicit owner maintenance operation, outside this renderer. This is not qualified boot/storage recovery for the Samsung TV.

## Owner-signed native bridge

`IExperienceControl.aidl` exposes the same journal through `ExperienceControlService` in the app's private `:domain` process. It is exported only behind the signature permission `local.sovereigntv.permission.CONTROL_EXPERIENCE`. Clients must request that permission and be signed by the owner's trusted signing identity. Keep that identity private; development debug signing is not production authority. The service checks permission on every Binder transaction before unmarshalling, so forwarding a Binder handle does not delegate authority. Synchronous methods reject one-way transactions before effects. This is a local Android permission boundary, not agentOS grants, paired transport or a network endpoint.

| AIDL operation | Contract |
|---|---|
| `capabilities(expiry)` | API version, declared operations, resource bounds and explicit unavailable capabilities. |
| `state(expiry)` | Current revision, exact saved document string, its SHA-256 and recovery flag. |
| `preview(base, document, expiry)` | Validated candidate; neither saved nor displayed on TV. Manual on-TV preview remains a separate UI workflow. |
| `apply(id, base, document, expiry)` | Revision-checked journal transaction; receipt and fresh saved-state read-back. |
| `undo(id, base, restoreRevision, expiry)` | Conflict-safe restore of a retained revision; receipt and current state. |
| `restoreDefault(id, base, expiry)` | Default document through the same idempotent apply transaction. |
| `receipt(id, expiry)` | Durable receipt or `not_found`. |
| `putArtwork(digest, descriptor, expiry)` | Verified SHA-256 and bounded PNG upload from a regular-file descriptor; pipes/devices refused. |
| `openArtwork(digest, expiry)` | Integrity-checked asset through a read-only descriptor. This returns image content: an eventual agentOS route must apply capture and private-data policy. |

Every response is a Bundle with `api_version=1` and `status`. Success metadata is a JSON string under `json`; asset read success also includes `file`, a caller-owned `ParcelFileDescriptor` that must be closed. JSON state contains the exact saved document string, not a normalized replacement. Effect success contains `receipt` and `state`; another writer may already have advanced that state beyond the receipt. Compare revisions and hashes. Request IDs are `[A-Za-z0-9._-]{1,64}` and exact retries preserve the original document bytes. Uploads can safely retry the same content hash. Neither descriptor paths nor arbitrary intents, URLs or shell commands are accepted.

Expiry is UTC milliseconds, strictly in the future and at most 30 seconds away. The service converts it once to an elapsed-time deadline. Effect guards recheck original caller authority and deadline after acquiring the journal writer lock and after document/asset validation, before SQL mutation. Artwork writes check again under the cross-process quota lock. A new effect that expires while waiting cannot commit. A caller that loses a reply still reconciles by ID; an elapsed request must not be reissued with a different ID. Receipt lookup uses its own fresh read deadline.

Statuses are `ok`, `not_found`, `conflict`, `capacity`, `invalid`, `expired`, `unauthorized`, `unavailable`, and `unknown`. Android denies unauthorized binding/transactions with `SecurityException` before a Bundle exists. `unknown` means an effect could have committed before a later failure: inspect its durable receipt and fresh state. Receipt-capacity refusal is explicit; malformed documents/assets, digest mismatch and artwork quota refusal return `invalid`. No error returns exception text, paths or private document contents. Binder death or transport failure also requires reconciliation, never an assumed rollback.

The service and Home have distinct processes but share the same app UID and private stores. SQLite serializes journal writers; artwork storage now combines an in-process monitor and an interprocess file lock to enforce its quota. The domain service holds no platform privileges or network permission. The future paired network controller must use a separate application/OS identity and its own authenticated boundary; this service does not yet implement that controller.

After a commit, an explicit-package signature-protected broadcast asks Home to reload the authoritative journal. Activity resume also reloads, covering missed notifications. Events carry no trusted state payload or document. Refresh work coalesces without dropping a notification received during a pending read. An unsaved manual preview remains visible during an external edit; applying its stale revision is refused, and cancelling it loads the current saved revision. Unconfirmed local effects are reconciled before external updates replace the view. Physical-remote editing continues without agentOS or a network.

Native runtime tests bind across processes rather than using a local Stub. They cover permission denial from a different UID, forwarded handles, one-way refusal, expiry during a writer wait, concurrent edits, exact retries, receipt survival after killing/restarting the dedicated domain process, bounded file descriptors, artwork read-back, live UI refresh and stale manual preview refusal. These emulator results do not qualify a production controller, agentOS broker integration, real-TV deployment or protected media.
