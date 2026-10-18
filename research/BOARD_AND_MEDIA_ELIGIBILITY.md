# Board topology and protected-media eligibility

Research date: 2026-10-17. This advances feasibility gates 1 and 5 in [FEASIBILITY.md](FEASIBILITY.md), without a device connection, installation, source execution or supplier message. Independent boot remains unqualified. No exact-unit identity field changes.

## What the new raw records establish

The [bounded provenance record](public-component-evidence.json) records independently retrieved public catalog metadata, hashes and query parameters. It contains no owner-photo observations, serials, QR values or private device observations. Raw vendor documents and catalog responses remain private. A reproducible digest identifies acquired bytes; it does not authenticate the publisher or validate the catalog's correctness.

### Samsung repair guide

[Samsung's Canadian model support listing](https://www.samsung.com/ca/support/model/QN50LS03FAFXZC/) supplies repair guide file 11120328, version 1.0, dated 2025-11-19, titled `79.Repair_Guide_QFLS03M_QNxxLS03FAFXxx_Ver1.0.pdf`. The listing has the Canadian suffix, while the applicable-model patterns on the guide cover the LS03FA/LS03FD families. This is family documentation, not an exact US revision BOM.

The 23-page guide was downloaded from Samsung and inspected as rendered pages as well as text. PDF pages 12–15 (printed 2-3 through 2-6) depict TV-side boards, remote/radio-related modules, power, speakers and USIT cables. Page 12 explicitly uses a 65-inch example; location can vary by size. Page 15 calls a TV-side board MainBoard/TV Board. That name does not establish the location of the application processor or eliminate computing inside One Connect. No legible exact silicon identity or installed revision was established.

The later factory-mode screenshots are marked SAMPLE and include other models/platforms. Their board labels, TCON names and software strings are not LS03F evidence. No service-menu procedure was performed or proposed. Post-repair setup through a running stock system does not establish recovery from a broken boot stage.

### Exact-model catalog, not exact-unit BOM

The [SamsungParts model page](https://samsungparts.com/products/samsung-qn50ls03fafxza-50-inch-class-the-frame-ls03fa-qled-4k-tv) retrieves a flat parts relation through its public JavaScript's `fetch_related_products` query. The relation names both PCB assemblies, decoder entries and storage parts below. This is stronger than a search snippet but supplies no board-to-chip placement or revision matching. SamsungParts is a parts seller/catalog source, not a silicon specification or boot-policy authority.

| Catalog part | Public record | What remains unknown |
| --- | --- | --- |
| BN94-18661C | [Product record](https://samsungparts.com/products/samsung-bn94-18661c): generic part name only. | Actual revision, components, CPU role and location. |
| BN94-18663B | [Product record](https://samsungparts.com/products/samsung-bn94-18663b-assy-pcb): PCB assembly, no placement detail. | Same; do not substitute a different suffix with a richer description. |
| BN96-61147A | [Product record](https://samsungparts.com/products/samsung-bn96-61147a-assembly-pcb-p-fr-1-oc-cover): OC plus cover assembly. | Included PCB(s), location of executing processors and matching lab scope. |
| 1204-003778 | [Product record](https://samsungparts.com/products/1204-003778): SDP1805S decoder, FCBGA, 490 pins. | Application CPU versus auxiliary media role; board placement and applicable variant. |
| 1204-003839 | [Product record](https://samsungparts.com/products/1204-003839): Quantum Processor decoder. | Exact chip marking, architecture, board placement and relationship to SDP1805S. |
| 1107-002758 | [Product record](https://samsungparts.com/products/1107-002758): eMMC. | Manufacturer part, capacity, placement, partition map and boot/provisioning dependencies. |
| 1107-002587 | [Product record](https://samsungparts.com/products/1107-002587): EN25QH16B NOR, 16 Mbit. | What executes from it, placement and write/restore policy. |
| 1107-002226 | [Product record](https://samsungparts.com/products/1107-002226): NOR flash, unspecified. | Same, plus exact chip identity and capacity. |

These entries do not prove both decoders or all flash devices are fitted simultaneously. A model catalog can aggregate variants and service parts. The EN25QH16B catalog capacity is 16 **Mbit**, not 16 MB; no storage addresses are inferred. No retrieved product record contains component photos or a revision-specific schematic. Public chip-name searches yielded no authoritative exact-chip boot/BSP documentation; that bounded search result is not proof none exists.

**Decision:** do not choose an SoC BSP or buy a spare One Connect box from this relation. The cheapest decisive next evidence is a revision-specific exploded BOM/placement map, with non-unique chip-marking images, identifying which PCB runs the application OS and which required panel/controller boards execute separate firmware. A spare enclosure alone cannot yet be claimed to reproduce the relevant hardware boundary. Keep the household unit closed.

## Four distinct playback decisions

1. **Android compatibility:** [AOSP's compatibility FAQ](https://source.android.com/docs/compatibility/compatibility-faq) distinguishes CDD/CTS compatibility from separately licensed Google Play access. It permits a customized interface within compatibility constraints. This supports keeping the owner Home separate from provider integrations; it does not grant Play or TV-client distribution.
2. **Legitimate secure-media integration:** [Widevine's access process](https://developers.google.com/widevine/access) requires an agreement and separately approved repository access; personal-email accounts are excluded from that repository process. For L1 integration it directs the integrator to the chipset vendor for OEMCrypto. [The overview](https://developers.google.com/widevine/drm/overview) separately identifies device provisioning and Keybox. Generic AOSP support or existing Samsung credentials therefore cannot establish a new independent integration. No existing key is requested, copied or reused.
3. **Provider/configuration acceptance:** [Netflix](https://help.netflix.com/en/node/14361) supports specific device routes; [Prime Video](https://www.primevideo.com/help?nodeId=GK4GR2DKAKDK92H9) makes smart-TV capabilities model-dependent. Neither page offers an onboarding entitlement for this replacement. Disney+'s [official Android TV article](https://help.disneyplus.com/en-GB/article/disneyplus-en-bs-android-tv) again returned no readable article body; no unsupported-device rules are inferred from its search snippet or another platform's documentation.
4. **Measured parity:** client availability, provisioning and approval precede actual stock-matched stream/output measurements. A protected demo, L1 status, Play access or a 3840×2160 surface cannot individually establish Netflix/Prime/Disney UHD/HDR, decoded cadence or panel output quality.

[YouTube's Living Room documentation](https://developers.google.com/youtube/devices/living-room/) also specifies device application requirements and certification. Its [access page](https://developers.google.com/youtube/devices/living-room/access/accessing-lr-partnership-resources) describes onboarded partner-domain access and supplies `youtube-devices@google.com` for assistance. That is a real published contact, not evidence this project is eligible. Free HDR samples can test the media path later; they do not prove official-client approval or protected-content parity. Old public YouTube requirement PDFs are not treated as current release criteria.

The owner-controlled Home can remain independently modifiable while a protected subsystem follows its accepted integrity policy **if** the integrators permit that boundary. Establish which Home, agent, OS and kernel updates require requalification. Do not weaken owner update control silently to obtain provisioning, and do not claim approval requires locking the whole experience without an actual integration answer.

## Requests that can resolve the current unknowns

No inquiry has been sent. These are concrete information requests, not authorizations to purchase, open hardware, execute diagnostics, accept licensing or disclose device/account identifiers.

| Recipient / verified route | Request | Sufficient next evidence |
| --- | --- | --- |
| Parts supplier; existing private draft | Revision-specific BOM for the exact model; clarify both PCB assemblies, OC enclosure contents and application-CPU placement; supply non-unique component photos and minimum matching lab configuration. | Dated revision-specific document or photos with provenance; independently check part/revision correspondence. A generic compatibility assurance is insufficient. |
| Widevine [published inquiry route](https://developers.google.com/widevine/contact/support), using General Questions | Is a single-household, independently maintained AOSP TV project eligible for a new licensed device integration? Which legal/entity/account conditions apply? After exact silicon is established, can independently sourced OEMCrypto/secure execution and new provisioning be obtained without Samsung software? | A scoped written eligibility answer and named chipset/integration route. No claimed OEM/partner status, invented company or license acceptance. |
| YouTube `youtube-devices@google.com`, from the access page above | Does that owner-maintained original-hardware configuration have an official TV-app onboarding/distribution path, and what application/platform changes affect qualification? | Scoped onboarding route, required entity/volume and current requirements access; an app-store APK is insufficient. |
| Netflix, Prime Video and Disney+ | Ask each official support route to identify its device-integration contact and whether this exact kind of owner-maintained build can qualify. No verified public self-service OEM onboarding route was established in this pass. | Named responsible integration party and written configuration/client eligibility; consumer stock-device support does not qualify the replacement. |

The first Widevine request can ask eligibility before the chip is identified; chip-specific support must remain conditional. Supplier and integration replies are external dependencies, not work that can be replaced by further shell implementation. Drafts can be prepared now; sending messages requires explicit owner authorization.

Until those replies and exact identity arrive, do not allocate a speculative full AOSP port, produce a flash script or claim recovery. Continue independent source analysis only when it answers a specific boot/provenance question; preserve the functioning off-TV product slice.
