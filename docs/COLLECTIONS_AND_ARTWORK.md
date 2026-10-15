# Local collections and artwork

The host studio and Android shell render owner-defined app/artwork collections, local PNG images and timed slideshows. Configuration uses the existing revision journal: preview is unsaved, Save changes (Android: Apply preview) commits atomically, and Undo restores a retained revision. Android remains offline with no network permission. This is ordinary gallery presentation; low-power panel Art Mode, brightness, sensors and standby still require board integration.

## Use the feature

1. Run the host studio and connect with its local development token. Choose Add artwork and a plain RGB/RGBA PNG. The upload is cached locally and a schema v2 configuration is staged as an unsaved preview.
2. Open Local artwork, then an image. Previous/Next and Start/Pause slideshow operate on visible artwork entries. Use the visual editor to change titles, appearance, visibility, entry order and slideshow interval, then Preview changes and Save changes. Advanced document retains direct JSON editing for other changes.
3. Export for Android downloads `experience.stv.zip` containing the **saved** document and its referenced PNGs. Transfer it to an authorized Android development target; Import experience stages it. Apply preview saves it; Cancel leaves the saved configuration intact. Android also accepts a local PNG through Import artwork.
4. On Android, D-pad activation opens collections and images; Back returns to the collection and restores its selected entry. Undo last change restores the prior saved configuration after restart as well.

Artwork controls hide after six seconds without interaction once the image has loaded; Android honors a longer accessibility timeout. A D-pad/Enter press reveals the controls without activating them. Back still returns to the collection. Browser pointer movement also reveals controls.

Slideshow starts paused. The configured interval is 30–86400 seconds and begins after the image loads. Android suspends advancement outside RESUMED; the browser suspends it while the document is hidden. Resuming begins a new interval, without catching up missed frames. Images fit within the display without cropping. Android hashes, validates and decodes on its single background worker, with bitmap sampling based on the viewport.

## Document format

The [schema v2 example](../examples/collections.json) starts with an empty local gallery. Version 1 remains valid. Version 2 retains its fields and adds a required `collections` array. A collection has `id`, `title` and `items`. Collection items have `id`, `title`, `kind`, `target` and `visible`; kind is `app` or `artwork`. Artwork target is the lowercase SHA-256 of the exact PNG bytes. App targets use the existing identifiers and discovered-activity resolution. Collections cannot contain other collections.

Every section tile of kind `collection` must reference an existing collection in version 2. Collection IDs are unique; entry IDs are unique within each collection. Limits: 12 collections, 48 entries per collection, 256 total entries, and 64 KiB of document metadata. Hidden images remain references and must exist, so unhiding and historical undo do not depend on another upload. Visibility curates the custom Home surface; it does not enforce app access restrictions.

## Image profile and storage

Both implementations accept only noninterlaced 8-bit RGB/RGBA PNG: at most 8 MiB per image, dimensions up to 8192 on either axis and total area at most 8,847,360 pixels. They verify chunk CRCs, compressed image completion, exact decompressed scanline size and valid scanline filter bytes before accepting an image. Optional metadata is limited to fixed-size sRGB, gAMA, cHRM and pHYs chunks before image data. Animation, EXIF, text, compressed metadata, palettes, other bit depths and executable formats are rejected. Export unsupported inputs as plain RGB/RGBA PNG first. This initial profile does not qualify wide-gamut/HDR artwork rendering.

Private immutable files are named by hash. Each experience may reference at most 32 MiB of unique image bytes; each asset store holds at most 128 MiB. Matching upload retries reuse an existing verified file, including at capacity. Files are flushed and atomically renamed before a document can reference them; preview, apply and undo reject missing or corrupt assets. Local owners must protect the host data directory from other processes; the host upload quota lock covers threads within one server instance.

Assets are deliberately not deleted on undo/cancel, preserving history and retries. Failed or cancelled previews and bundle imports can leave unreferenced cached images. Storage-full refuses new images without deleting saved artwork. There is no automatic garbage collection or per-image deletion UI yet; reaching the limit requires an owner-managed backup/migration, not ad hoc removal of files needed by history.

## Portable bundles

Android accepts JSON or ZIP through the same picker. ZIP imports are bounded to 40 MiB, 257 unique entries and 32 MiB of image payloads. Allowed names are exactly `experience.json` and `artwork/<sha256>.png`. Unknown names, duplicate entries, unsafe paths, mismatched hashes, unsupported PNGs and missing/extra assets fail before configuration changes. Entries are read with individual bounds, never extracted by their archive paths. The bundle is fully validated before caching its images; an I/O or quota failure while caching leaves the saved configuration intact.

The host exposes authenticated image upload/read and export operations in [API.md](API.md). These implement local domain editing, not production agentOS pairing or on-TV service access. Portable transfer remains manual.

Implementation references: [PNG specification](https://www.w3.org/TR/png-3/), [Android bitmap sampling](https://developer.android.com/topic/performance/graphics/load-bitmap), [Compose effect lifecycle](https://developer.android.com/develop/ui/compose/side-effects).
