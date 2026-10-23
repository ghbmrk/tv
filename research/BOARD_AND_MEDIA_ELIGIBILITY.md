# Board topology and protected-media eligibility

Research date: 2026-10-17. Updated 2026-10-18 to remove an unsupported outreach prerequisite. This advances feasibility gates 1 and 5 in [FEASIBILITY.md](FEASIBILITY.md), without a device connection, installation, source execution or supplier message. Independent boot remains unqualified. No exact-unit identity field changes.

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

## October 23: public board and radio evidence

The [bounded public evidence follow-up](board-radio-evidence.json) adds a seller's first-hand [BN94-18661C board photograph](https://tvpartstoday.com/products/bn94-18661c-samsung-main-board-bn62-01037a-qn50ls03fafxza). The label is visible, but a heat spreader covers the main chips. It does not establish the installed revision, application processor or boot policy. No owner hardware was opened and no photo or unique label data is redistributed.

Samsung's filed [WCF734M internal photos](https://fccid.io/A3LWCF734M/Internal-Photos/Internal-Photos-7805708.pdf), visually reviewed on both pages, show a MediaTek MT7668AUN chip. The mirrored PDF matches the published exhibit digest; the FCC primary download did not succeed. The module is a model-catalog candidate, not an observed installed part. Do not confuse this radio processor with the application CPU.

An independent implementation candidate now has explicit provenance: [Google Coral's MT7668 Wi-Fi source](https://coral.googlesource.com/mt7668-wifi-mod/+/50e077977859e95b8f8250d1b59b17ebd7ec08a3/) carries MediaTek's GPLv2 notice. Its inspected build metadata has USB, SDIO and PCIe branches, plus a USB MT7668 configuration. This has not been compiled or qualified for this TV. Upstream [Linux v6.18 Bluetooth source](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/7d0a66e4bb9081d75c82ec4957c50034cb0ea449/drivers/bluetooth/btmtk.c) includes MT7668 firmware selection. The separately pinned [linux-firmware provenance](https://kernel.googlesource.com/pub/scm/linux/kernel/git/firmware/linux-firmware/+/8a46c32a26b3f22835543b158877aa0b0e01e8d6/WHENCE) lists a MediaTek Bluetooth image under its own redistribution terms. These historical pins are research inputs, not selected current release artifacts or an audit of every file's authorship.

The remaining binding facts are installed module identity, actual host bus/device IDs, power/reset/coexistence wiring, applicable firmware and working pairing/wake behavior with the original remote. Generic chip-family support proves none of those. No driver or firmware was loaded, and no firmware binary was downloaded in this follow-up. The component ledger retains `unverified` status and now links these candidate facts rather than leaving the evidence fields empty.

## Four distinct playback decisions

1. **Android compatibility:** [AOSP's compatibility FAQ](https://source.android.com/docs/compatibility/compatibility-faq) distinguishes CDD/CTS compatibility from separately licensed Google Play access. It permits a customized interface within compatibility constraints. This supports keeping the owner Home separate from provider integrations; it does not grant Play or TV-client distribution.
2. **Legitimate secure-media integration:** [Widevine's access process](https://developers.google.com/widevine/access) requires an agreement and separately approved repository access; personal-email accounts are excluded from that repository process. For L1 integration it directs the integrator to the chipset vendor for OEMCrypto. [The overview](https://developers.google.com/widevine/drm/overview) separately identifies device provisioning and Keybox. Generic AOSP support or existing Samsung credentials therefore cannot establish a new independent integration. No existing key is requested, copied or reused.
3. **Provider/configuration acceptance:** [Netflix](https://help.netflix.com/en/node/14361) supports specific device routes; [Prime Video](https://www.primevideo.com/help?nodeId=GK4GR2DKAKDK92H9) makes smart-TV capabilities model-dependent. Neither page offers an onboarding entitlement for this replacement. Disney+'s [official Android TV article](https://help.disneyplus.com/en-GB/article/disneyplus-en-bs-android-tv) again returned no readable article body; no unsupported-device rules are inferred from its search snippet or another platform's documentation.
4. **Measured parity:** use an available, legitimately provisioned client/configuration and compare actual stock-matched stream/output measurements. A new vendor conversation is not a universal prerequisite; establish the applicable distribution/integration rules for the chosen route. A protected demo, L1 status, Play access or a 3840×2160 surface cannot individually establish Netflix/Prime/Disney UHD/HDR, decoded cadence or panel output quality.

[YouTube's Living Room documentation](https://developers.google.com/youtube/devices/living-room/) defines its scope as enabling/distributing the HTML5 living-room applications through device partners. Its onboarding requirements cannot by themselves establish that a private Android build using an existing client must contact YouTube. The earlier broader inference is withdrawn. Free HDR samples can test a media path later; they do not qualify protected services. Old public requirement PDFs are not current release criteria.

The owner-controlled Home can remain independently modifiable while a protected subsystem follows its accepted integrity policy **if** the integrators permit that boundary. Establish which Home, agent, OS and kernel updates require requalification. Do not weaken owner update control silently to obtain provisioning, and do not claim approval requires locking the whole experience without an actual integration answer.

## Resolve evidence without outreach

Owner direction, 2026-10-18: **do not message third parties**. No inquiry has been sent. The private drafts are retained as inactive research notes, not pending authorization requests. Supplier replies and vendor correspondence are not mandatory deliverables. The requirement is sufficient technical and service evidence, which can come from public primary documentation, attributable existing integrations and properly gated measurements.

A useful correction comes from Google's [developer device-distribution documentation](https://support.google.com/googleplay/android-developer/answer/7353455?hl=en-US-u-mu-fahrenhe): uncertified devices may receive an app unless its distribution rules exclude them. Certification, app availability and integrity-sensitive features must therefore be examined separately. This does not guarantee availability of any named provider client, grant Play/GMS distribution rights or qualify UHD/HDR. Model-list membership, a benchmark claiming Android or an APK installation alone remains insufficient.

| Question | Evidence to seek without contacting anyone | What that evidence cannot settle alone |
| --- | --- | --- |
| Which board/chip executes the OS? | Revision-specific public service BOM/placement documentation, attributable component photos, source identifiers and already authorized exact-unit observations. | A flat same-model parts list cannot establish installed revision or whether two decoder entries are fitted together. |
| Can an independent system boot and recover? | Exact-chip boot policy and publicly available independent boot/BSP implementations; match their revisions and provenance to the target. Later validate only on matching lab hardware under the existing safety gates. | Temporary root, a stock updater and a post-stock kernel entry point do not establish independent cold boot or recovery. |
| Is an independent protected-media implementation available? | Public release/source/licensing records for the actual chipset's DRM plugin, secure execution, OEMCrypto, secure decoder/output and provisioning route. | AOSP interface definitions are not the scheme implementation. A codec list cannot supply device credentials or service acceptance. |
| Can existing official clients be used here? | Provider/platform distribution documentation and an attributable matching implementation/build, then bounded client tests on the safely qualified lab platform. | App installation does not establish UHD/HDR. Commercial device-manufacturer onboarding rules are not automatically rules for every private end-user build. |
| Does the final system meet stock quality? | Same-title/plan/settings negotiated stream and measured output, original-remote, thermal/standby and privacy observations on the qualified candidate. | General documentation cannot report the output of this unbuilt image or replace physical measurements. |

[Widevine's published access process](https://developers.google.com/widevine/access) establishes that its partner repository access involves agreements and that an L1 integrator needs the appropriate chipset OEMCrypto implementation. It does not establish that this particular project must become a new direct licensee, that an existing lawful integration is available, or that one can be fabricated from public interface headers. Seek an attributable matching integration first. Do not transplant stock keys or unrelated-device blobs to make the evidence appear complete.

[AOSP's DRM description](https://source.android.com/docs/core/media/drm) explicitly separates framework/plugin interfaces from a DRM scheme's robustness/compliance rules and describes vendor/SoC-specific plugins. A working independent implementation and applicable provisioning are real dependencies; contacting a vendor is only one possible information source, now excluded by owner direction.

The literal Samsung-software-removal boundary is explicitly in the supplied specification, including immutable/peripheral software. It is not removed by this correction. No exact immutable incompatibility or feasible independent replacement has yet been established.

**Decision boundary:** continue public/offline research and useful owner-software implementation. Do not require unanswered emails before proceeding, and do not select a speculative BSP, claim eligibility/recovery or create a writer without the underlying evidence. If a necessary fact is unavailable publicly and cannot be safely observed, record that exact fact as unknown and its consequence. Availability, approval and cryptographic provisioning cannot be asserted merely because they would be convenient. No household hardware gate changes in this update.
