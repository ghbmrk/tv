# TV-owned agentOS control components

This development Go module implements native experience apply/undo through the current Linux `kernel.Clerk` interface in `kernelclerk/`, and preserves the older `journal.Executor` interface at the module root. It is an isolated broker component, with no guest endpoint. Production broker registration, operation classification, grants, audience/private-data routing and capture enforcement remain unimplemented and unqualified. The adapter does not grant authority or make the TV agentOS-compatible by itself.

The dependency now pins agentOS [`9806a98dd2b8b85f8f3db1e7e9d7432a1f0bd137`](https://github.com/ghbmrk/agentOS/tree/9806a98dd2b8b85f8f3db1e7e9d7432a1f0bd137/broker), module `v0.0.0-20261024140559-9806a98dd2b8`, with source checksums in `go.sum`. Go 1.26.8 matches upstream. The [contract review](../docs/agentos-integration.md#current-upstream-contract-october-24) still applies: the kernel's presentation class disagrees with its spec. Configuration uses the specified administrative `change-account` verb at the high class; this is not a general presentation or device-actuation clerk.

## Current kernel clerk

`native/` contains the paired client, inspection and exact edit/receipt protocol, with no agentOS dependency. `kernelclerk/` imports that package and the current kernel/clerk APIs; it imports no legacy journal/durable code. The module root is a compatibility adapter over the same native editor. Both protocols preserve their own stable request-ID domain; kernel IDs additionally bind the signed plan's signature, preventing a different signed plan from borrowing its receipt.

The current clerk accepts exactly one pinned TV, two configuration operations and the fixed `target`/`value` shape. It independently verifies the signed plan, grant/dispatch/hold state on its own clock, and private content facts before dispatch. It snapshots caller input before clock/view callbacks. Request IDs, endpoints, credentials and executable operations cannot be supplied in the command. Native validation remains authoritative for experience schema and local assets.

Trusted construction requires owner anchors and a qualified declaration: `local-only` visibility, and `owner` or `household` audience. Unknown/cloud-visible declarations and public audiences are refused. These construction inputs are not hardware/privacy proofs. An owner-audience device can use a properly granted delegated configuration key. Because private curation on a household screen is a disclosure, household edits currently require an owner-signed exact plan with a bare passkey root; delegated household templates are not implemented. No approval prompt or widening is created inside this library. The actual owner broker must prepare and authorize the exact plan through its own trusted path.

`Do` sends one native operation after the current authority recheck. Duplicate native request IDs remain governed by the atomic, non-evicting native receipt journal. `Probe` verifies the original signed plan and only requests its exact receipt, even after STOP, expiry or revocation. Absence stays unknown and never returns `notdone`, which could trigger a replay. Kernel results contain fixed wording only: no document, private metadata or raw error. A verified commit does not prove current screen visibility or provider playback.

The current upstream clerk package depends on Linux network code, so `kernelclerk` and its current-kernel emulator probe are Linux-only. Native transport and the preserved legacy adapter remain testable on macOS. Linux CI runs the real-kernel authority/restart tests, checks that the clerk has no legacy-core imports, and drives the paired Android TV emulator with `cmd/kernelinterop`. Its owner keys, grants, clock and in-memory kernel store are synthetic test fixtures; the native Keystore/mutual-TLS service and SQLite transactions are real. This is component interoperability, not production registration, grants/disclosure routing or household-TV qualification.

```sh
cd executor
GOTOOLCHAIN=local go test -mod=readonly -race ./...
GOTOOLCHAIN=local go vet -mod=readonly ./...
# Linux: compile the current-kernel owned-emulator probe.
go build -mod=readonly -o ../.local/tv-kernel-clerk-interop ./cmd/kernelinterop
cd ..
python3 tools/qualify_control_interop.py --serial EMULATOR_SERIAL \
  --go-executor .local/tv-kernel-clerk-interop --kernel-clerk
```

The static Linux ARM64 authority and file-store tests pass inside the local Android emulator, including lost-reply reconciliation after reopening the upstream fsynced file store (with a synthetic retained anchor), real-kernel restart reconciliation, revocation, STOP, expiry, signed-plan tampering and household exact-plan checks. The current-kernel probe also passes against the real paired Android service: apply, exact retry, clerk/kernel recreation, receipt reconciliation and undo. This local run used an emulator-only wrapper and temporary synthetic credentials; it does not verify production process isolation. The additional Unix-socket protocol test requires hosted Linux: the Android emulator shell denies filesystem socket binding, and its security policy was left unchanged. The [implementation PR](https://github.com/ghbmrk/tv/pull/40) records the separate hosted Linux race/vet, Unix-socket and x86_64 paired-service checks. Local runtime success is not a substitute for those checks. Historical journal verification below remains scoped to that adapter.

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


## Historical journal compatibility

Historical qualification pin: `603cad7ce180c7f4f45447b64e652fa4a15d5563`, module `v0.0.0-20261017235249-603cad7ce180` (checked 2026-10-17). The preserved adapter is now also compiled/tested against the current pinned dependency; that does not turn it into a current clerk. Upstream may resend an unknown attempt only for executors that opt into its key-honouring contract. This adapter deliberately does not advertise that capability: stable native request IDs alone are not permission for automatic effect replay.

`TestCurrentBrokerParksMissingReceiptWithoutResendingTVEffect` exercises the actual current engine through repeated missing-receipt checks and parking, verifies exactly one edit/attempt, and restores the original receipt to prove settlement without another edit. The race-enabled suite and existing restart/policy tests qualify these fixture paths only. Production registration, grants, routing and household end-to-end operation remain unqualified. The upstream Codex lane was retired at this historical revision; the October 24 review records its later limited reintroduction. This dependency update changes only TV-owned code and does not authorize broker edits.
