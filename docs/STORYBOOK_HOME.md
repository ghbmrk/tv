# Storybook Home and deliberate viewing

The initial Home is a quiet, text-free storybook surface: warm paper, ink and muted watercolor; six chosen movie illustrations above Netflix, Disney+, YouTube, Prime Video, Hulu and Apple TV. No headings, captions or availability labels are painted on Home. Accessibility keeps movie/app names, focus, button roles and availability. Settings retains readable editing and diagnostic text. The illustrations are original interpretations, not provider-supplied posters or evidence of availability.

The movie order comes only from the local document. There are no recommendation feeds, automatic additions, hover previews, trailers, carousel timers or automatic advances. An empty movie section stays empty. Manual add, remove, reorder, visibility and poster edits use the existing preview/apply/undo journal. Authorized household edits use that same document, not a separate recommendation service. Existing saved experiences are preserved; the new default applies to a fresh store or explicit Restore default.

Remote selection follows the card's stable ID during live curation. If an edit moves that card beyond a composed viewport, Home brings its section and carousel position into view before restoring focus. Existing visible scroll positions are retained. Hiding or removing the selected card uses the existing visible-card fallback; the next D-pad action works without reopening Home. This is local navigation behavior, not a measurement of the Samsung remote or TV latency.

## Curating movies

Run the local studio and connect using its private local token. Expand Chosen movies. Add chosen movie creates an unsaved blank card, never an algorithmic selection. Set the title and choose a local PNG poster, or choose a bundled illustration key. Arrange, hide or remove entries, then Preview changes and Save changes. Uploaded posters are immutable content-addressed private PNGs; export includes referenced posters. Nothing fetches movie art or metadata from a third party. The same validated JSON can be edited by an authorized household agent through native preview/apply/undo; production agentOS broker qualification remains pending.

`examples/storybook.json` is the portable v3 initial document, byte-identical to Android's `storybook.json`. Versions 1 and 2 remain supported. Version 3 retains v2's root fields and permits `movie` entries in sections; movies do not become artwork slideshows or recursively nested collections. Section item count is 0–24 in v3, with at least one visible item somewhere on Home. Existing section, ID, label, document-size, collection and asset bounds remain in force. Row/grid layouts remain editable.

A movie has the normal `id`, `title`, `kind`, `target`, `visible` fields plus required `poster` and `playback`. Its target is an owner-defined local identifier, not an executable, URI, intent or inferred catalog entry. Poster is `blank`, one of the six keys below, or a lowercase SHA-256 of an existing local PNG. Hidden movie posters remain integrity-checked references so unhide and undo do not depend on another upload.

| Bundled key | Initial chosen title |
|---|---|
| `princess_frog` | The Princess and the Frog |
| `kung_fu_panda` | Kung Fu Panda |
| `balto` | Balto |
| `little_mermaid` | The Little Mermaid |
| `hunchback` | The Hunchback of Notre Dame |
| `land_before_time` | The Land Before Time |

`playback` is null or an explicit `{provider, content_id}` descriptor. Only bounded Netflix numeric IDs, Prime Video ten-character IDs, Disney+ entity UUIDs and YouTube eleven-character IDs are accepted. These are candidate binding namespaces, not assertions that a provider supports any generated URL, that a title is in the household's subscription/region, or that playback is qualified. Arbitrary URLs, shell/intent data, feed and autoplay fields are rejected. Initial movie bindings are deliberately null; no content ID or provider availability has been invented.

## Stop at the selected movie

A movie descriptor alone cannot prevent a provider's post-play recommendations. Consequently, no movie playback adapter is enabled yet, even if an explicit descriptor is supplied. Selecting a movie never falls back to a provider's Home, search or recommendation screen. The native UI gives an accessible unavailable notice, without adding visible text to Home. This is a fail-closed prototype boundary, not completed movie playback.

Before enabling an adapter, qualify the exact title route, account/region/client version, completion detection, immediate stop/return behavior, interruption, missing completion events and recovery. The selected movie must end without starting another title. If reliable stop-at-end cannot be enforced, that adapter remains disabled; do not substitute a guessed media duration, periodic key press or configuration flag for observed behavior. The [provider and hardware release gates](deployment/PLAN.md) still apply.

The six app tiles are deliberate app launches, independently discovered and rechecked. Their internal recommendations and autoplay remain provider behavior; the owner-built Home does not claim to control them. Hulu and Apple TV package aliases are corroborated by their [Hulu Android TV](https://play.google.com/store/apps/details?id=com.hulu.livingroomplus) and [Apple TV](https://play.google.com/store/apps/details?id=com.apple.atve.androidtv.appletv) listings; actual installed entry points still govern availability. A logo is not proof of installation, entitlement or 4K/HDR.

## Rendering and verification

The background and six-cell illustration atlas are separate from controls. Bitmap decoding runs off the UI thread; two shared bundled bitmaps are retained through Settings. Custom posters decode to bounded display size. Lazy rows retain native D-pad behavior; focus uses a paper edge and modest shadow without video, blur shaders or animated scaling. Settings return freezes the owner selection while Android rehomes focus, then restores that selection; a removed selection falls back only to another explicit visible item.

The read-only `/preview` page displays only the bundled initial example and generated product art. It never exposes saved household state or private assets and needs no local editing token. The authenticated studio continues to use the revision API. Android still has no INTERNET permission; the separate paired controller handles authorized transport. This does not qualify original-TV boot, remote hardware, provider playback or stock-parity latency.

Generated asset hashes and exact prompts are in [the asset manifest](STORYBOOK_ASSETS.json). Only those two bounded, digest-pinned product images are permitted by publication checks; raw owner references and vendor artifacts remain private. Built-in imagegen was used; no external runtime asset service is required.
