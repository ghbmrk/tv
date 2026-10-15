# Development editing API

Run `python3 -m sovereign_tv.server` from the repository root, then open `http://127.0.0.1:8765`. Read `.local/development-token` locally and paste it into the studio. The token remains in page memory; never commit it or put it in a URL. State and receipts live in `.local/experience.sqlite3`. Python 3.9 or newer is sufficient; no packages are required.

This is a loopback development service, not the production LAN service or a qualified agentOS adapter. It intentionally has no hardware or provider account privileges. It binds only `127.0.0.1`, checks Host/Origin, authenticates every API request and never enables CORS. Do not expose it through a tunnel or reverse proxy. Production requires the paired identity, operation-scoped grants and broker enforcement in `agentos-integration.md`.

Every API call uses `Authorization: Bearer <local-token>`; every POST also uses `Content-Type: application/json`. Maximum POST body size is 65536 bytes.

| Endpoint | Result |
|---|---|
| `GET /api/capabilities` | Version and explicit development-only capability limits. |
| `GET /api/state` | Current `revision` and `experience`. |
| `POST /api/preview` | Validate against current revision and return changed top-level fields without applying. |
| `POST /api/apply` | Atomically save the full experience and durable request receipt. |
| `GET /api/receipts/<request_id>` | Reconcile an uncertain effect. A missing receipt alone is not permission to create a new request ID. |
| `PUT /api/assets/<sha256>` | Upload a bounded PNG with `Content-Type: image/png`; immutable content hash, safe identical retry. |
| `GET /api/assets/<sha256>` | Authenticated integrity-checked PNG. |
| `GET /api/export` | Saved experience and referenced artwork as a portable ZIP. |
| `POST /api/undo` | Restore an earlier revision only if the current revision matches the requested base. |

Apply/preview request:

```json
{"request_id":"household-edit-1","base_revision":1,"experience":{"schema_version":1,"title":"Evening","theme":"warm","sections":[{"id":"art","title":"Artwork","layout":"grid","items":[{"id":"gallery","title":"Local gallery","kind":"collection","target":"artwork","visible":true}]}],"settings":{"text_scale":1.1,"artwork_interval_seconds":600}}}
```

Undo request:

```json
{"request_id":"household-undo-1","base_revision":2,"restore_revision":1}
```

Reuse the exact apply/undo request ID and arguments after a lost response. Deduplication persists across process restarts. A reused ID with different arguments or a stale base returns 409. Invalid documents return 400. Request IDs are not authority: the development token currently authorizes the complete editing surface. Profile grants, media state, subscription events, expiry and production pairing are planned, not implemented.

Schema v1 remains accepted. Schema v2 adds app/artwork collection contents and local slideshow rendering; see [the format and asset limits](COLLECTIONS_AND_ARTWORK.md). Upload all referenced artwork before preview/apply; missing or corrupt assets reject the configuration transaction. Arbitrary widget composition, account controls and actual TV settings remain future work. Visibility is Home curation only; it does not enforce a launch restriction. The Android shell currently imports exports manually; it is not live-connected to this host service.

The Android file-import path now has its own transactional preview/apply/cancel, durable receipts and undo. See [native domain semantics](NATIVE_TRANSACTIONS.md); no live transport between the two implementations is implied.
