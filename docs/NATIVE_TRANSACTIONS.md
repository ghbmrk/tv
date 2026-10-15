# Native experience transactions

The Android domain layer implements preview, revision-checked apply, durable receipts and conflict-safe undo. Remote-operated import stages an unsaved preview; Apply commits it, Cancel restores the saved view, and Undo last change appends the preceding document as a new revision. A preview survives activity recreation through the retained view model; process death discards only the unsaved preview. Undo remains available after process restart from saved history.

`ExperienceRepository` is the domain facade. All calls run on the shell's background worker:

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

The latest 128 documents are retained. Receipts are retained up to an explicit 10,000-effect capacity; reaching it refuses new effects while preserving receipts and state. Receipts are never silently evicted to permit replay. Production maintenance/epoch rotation must be designed before enabling a continuously reachable service; the current file-import prototype has no network endpoint. Request IDs are bounded to 64 characters and documents to 64 KiB. Quotas are not authorization.

The UI retains a pending effect's ID and arguments until receipt/state reconciliation succeeds. An unconfirmed result offers Retry change using the same request; it never claims the previous experience survived an uncertain commit. A confirmed stale-revision refusal reloads saved state. Read-back checks the document hash when the receipt identifies the current revision; a newer saved revision is reported explicitly.

Android's default corrupt-database handler can delete evidence. This journal instead preserves it. An unreadable journal or stored document exposes a default Home for manual navigation with editing disabled and revision zero; history is not rebuilt and receipts are not discarded. Repair/export is an explicit owner maintenance operation, outside this renderer. This is not qualified boot/storage recovery for the Samsung TV.

This layer has no exported Binder endpoint, LAN transport, pairing or agent authorization. The future control service must expose these typed operations through its authenticated boundary, never arbitrary database access. Physical-remote preview, apply, cancel and undo operate independently of agentOS and the network.
