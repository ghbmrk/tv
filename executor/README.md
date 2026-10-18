# TV-owned agentOS executor

This development Go module implements the actual `journal.Executor` interface for native experience apply and undo. It is an isolated broker component, with no guest endpoint. Production broker registration, operation classification, grants, audience/private-data routing and capture enforcement remain unimplemented and unqualified. The adapter does not grant authority or make the TV agentOS-compatible by itself.

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

The driver checks the owned emulator, transfers only a temporary public client certificate and creates a localhost forward. Its Go probe verifies native editing, exact retries, reconciliation after adapter recreation and undo. The Android test independently verifies four resulting revisions: two from Python and two from Go, with the exact original document restored. This is transport/domain interoperability, not production agentOS or actual-TV qualification.

The unit suite also uses agentOS's actual file-backed journal engine to verify policy recheck before dispatch, lost-reply fencing across restart, no effect replay while a receipt is missing, and resolution from the original receipt. Its synthetic policy and redactor are fixtures, never production authorization.


## Current journal compatibility

Pinned upstream: `603cad7ce180c7f4f45447b64e652fa4a15d5563`, module `v0.0.0-20261017235249-603cad7ce180` (checked 2026-10-17). Upstream may resend an unknown attempt only for executors that opt into its key-honouring contract. This adapter deliberately does not advertise that capability: stable native request IDs alone are not permission for automatic effect replay.

`TestCurrentBrokerParksMissingReceiptWithoutResendingTVEffect` exercises the actual current engine through repeated missing-receipt checks and parking, verifies exactly one edit/attempt, and restores the original receipt to prove settlement without another edit. The race-enabled suite and existing restart/policy tests qualify these fixture paths only. Production registration, grants, routing and household end-to-end operation remain unqualified. The upstream Codex lane is retired; this dependency update changes only TV-owned code and does not authorize broker edits.
