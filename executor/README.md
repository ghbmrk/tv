# TV-owned agentOS executor

This development Go module implements the actual `journal.Executor` interface for native experience apply and undo. It is an isolated broker component, with no guest endpoint. Production broker registration, operation classification, grants, audience/private-data routing and capture enforcement remain unimplemented and unqualified. The adapter does not grant authority or make the TV agentOS-compatible by itself.

The [October 24 contract review](../docs/agentos-integration.md#current-upstream-contract-october-24) identifies the newer kernel/clerk boundary. This module is a legacy journal adapter, not an implementation of that current interface. Its pinned tests remain useful component evidence; they are not production migration or authority qualification. The current kernel has device verbs, with an unresolved presentation-class discrepancy against its spec. No dependency upgrade or verb substitution is made automatically.

The dependency pins public agentOS commit [`603cad7ce180c7f4f45447b64e652fa4a15d5563`](https://github.com/ghbmrk/agentOS/tree/603cad7ce180c7f4f45447b64e652fa4a15d5563/broker), with module/source checksums in `go.sum`. No local replacement or copied interface is used. Go 1.26.8 matches that upstream module's toolchain; official [release checksums](https://go.dev/dl/) identify the project-local SDK. This replaces the earlier October 13 module pin; it is not a production broker installation.

## Owner embedding boundary

```go
client, err := executor.OpenProfile(".local/tv-control.json", false)
// Handle err; fail closed before registering the adapter.
adapter, err := executor.New(ctx, executor.Config{
    Namespace: "persistent-owner-broker-id",
    Account: "tv:living-room",
    Transport: client,
})
// Handle err. adapter satisfies journal.Executor; this is not broker wiring.
```

The [paired controller profile](../docs/LOCAL_CONTROL.md#configure-the-isolated-executor) is owner-private, mode 0600. Keys must be regular owner-owned private files; key symlinks are refused. Only explicit private IPv4 endpoints are accepted in production. Certificate trust uses the exact DER identity, its self-signature, normal X.509 validity and server purpose, with no public CA store or DNS trust. Network cancellation closes the connection. There is no automatic request replay, image transfer or arbitrary operation passthrough.

`Namespace` identifies the broker installation and must remain stable across restarts and credential rotation. Distinct broker installations need distinct namespaces. Account, device identity and executor name are fixed owner configuration, not selected by guest parameters. The owner-reviewed broker policy must authorize the exact intent immediately before dispatch; this adapter does not inspect or enforce grants, recipients or visibility.

| Intent action | Exact `Params` fields |
|---|---|
| `tv.experience.apply` | `device_id`, `base_revision`, exact UTF-8 `document` |
| `tv.experience.undo` | `device_id`, `base_revision`, `restore_revision` |

`Intent.Executor` must be `sovereign-tv`; `Intent.Account` must match configuration. Unknown fields, wrong targets and unsupported actions are refused before transport. Revisions must be positive exact integers no larger than JavaScript's exact-integer bound; apply bases leave room for the resulting revision. Documents remain bounded to 64 KiB. This subset does not expose provider controls, hardware settings, controller trust, artwork/image reads or OS administration.

## Inspect and validate before editing

The TV-owned `Inspector` completes the paired read/validate path without adding a guest endpoint or changing the journal executor's two effect actions:

```go
inspect, err := executor.NewInspector(client)
// Handle err. Authorize and label the read through the owner broker first.
saved, err := inspect.State(ctx)
apps, err := inspect.Applications(ctx)
// Build a bounded candidate document from saved.Document; app targets are opaque.
preview, err := inspect.Preview(ctx, saved.Revision, candidateDocument)
// Handle every error. A successful preview does not reserve saved.Revision.
// Submit the exact document/base through the existing authorized apply intent.
```

`State` verifies the exact document digest, revision range and explicit recovery flag. It reads durable configuration, not the current screen or provider state. `Applications` verifies the catalog digest over the received array, bounded labels, unique opaque targets/known aliases, explicit truncation and the absence of a playback qualification claim. Empty catalogs are valid; truncated catalogs must not be treated as complete. There is no app-launch operation in this inspector.

`Preview` invokes native schema/asset validation against the exact document/base and requires explicit `saved=false` and `displayed_on_tv=false`. It changes neither saved configuration nor the TV display. An authenticated native conflict returns `ErrStaleRevision`; re-read and deliberately rebase instead of blindly retrying apply. Missing fields, ambiguous/malformed data, changed identities, cancellation and other refusals return a fixed `ErrInspection`, without response text or household content. No method retries or dispatches an effect. The native service remains the authoritative experience validator; host JSON checks alone do not validate an experience schema.

All returned documents, app labels and inventories are private, untrusted household data. Do not log them, treat them as instructions, or put them into journal success evidence. The owning broker still needs read authorization, account/device scoping, private-data routing and guest isolation before exposing them. These helpers provide no grants, production registration, audience policy or protected-media access.

Typed JSON decoding rejects exact duplicate keys and case-folded aliases recursively at typed boundaries, including profiles and receipts. Opaque JSON result/document boundaries receive their own operation-specific validation; they do not become arbitrary passthrough operations.

## Attempt and outcome semantics

The native request ID is SHA-256 of the JSON string array `["sovereign-tv/native-v1", namespace, account, device_id, journal.AttemptKey(intent.ID, attempt)]`. It is stable across adapter restarts and contains no intent text. Arguments do not change the key: native reuse with changed arguments still conflicts.

Construction requires the TV's `receipt_operation_sha256` capability before any effect is enabled. A success receipt must match the request ID, base/result revisions, exact operation digest, and, for apply, document digest. Evidence contains only these bounded receipt fields and the pinned device identity. It excludes document content, titles, credentials and server error text. Receipt metadata still follows the broker's private-data policy.

`Execute` follows agentOS's at-most-once-per-attempt dispatch contract. Local refusal dispatches nothing; authenticated definite pre-commit refusal is `not_applied`. Lost/malformed replies and mismatched receipts are `unknown`. `Reconcile` only reads the original receipt; absence remains `unknown` and never triggers an effect. Success proves a durable configuration commit, not current screen visibility, provider playback or goal quality. Cancellation is not undo.

## Verification

```sh
cd executor
GOTOOLCHAIN=local go test -mod=readonly -race ./...
GOTOOLCHAIN=local go vet -mod=readonly ./...
go build -mod=readonly -o ../.local/tv-executor-interop ./cmd/interop
cd ..
python3 tools/qualify_control_interop.py --serial EMULATOR_SERIAL --go-executor .local/tv-executor-interop
```

The driver checks the owned emulator, transfers only a temporary public client certificate and creates a localhost forward. Its Go probe verifies typed state/application inspection, native validation preview without a saved-state change, stale-preview refusal, native editing, exact retries, reconciliation after adapter recreation and undo. The Android test independently verifies four resulting revisions: two from Python and two from Go, with the exact original document restored. This is transport/domain interoperability, not production agentOS or actual-TV qualification.

The unit suite also uses agentOS's actual file-backed journal engine to verify policy recheck before dispatch, lost-reply fencing across restart, no effect replay while a receipt is missing, and resolution from the original receipt. Its synthetic policy and redactor are fixtures, never production authorization.


## Current journal compatibility

Pinned upstream: `603cad7ce180c7f4f45447b64e652fa4a15d5563`, module `v0.0.0-20261017235249-603cad7ce180` (checked 2026-10-17). Upstream may resend an unknown attempt only for executors that opt into its key-honouring contract. This adapter deliberately does not advertise that capability: stable native request IDs alone are not permission for automatic effect replay.

`TestCurrentBrokerParksMissingReceiptWithoutResendingTVEffect` exercises the actual current engine through repeated missing-receipt checks and parking, verifies exactly one edit/attempt, and restores the original receipt to prove settlement without another edit. The race-enabled suite and existing restart/policy tests qualify these fixture paths only. Production registration, grants, routing and household end-to-end operation remain unqualified. The upstream Codex lane was retired at this historical revision; the October 24 review records its later limited reintroduction. This dependency update changes only TV-owned code and does not authorize broker edits.
