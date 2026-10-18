# Off-TV execution plan and experiment boundary

Owner direction, 2026-10-15: finish the software and reduce irreversible-device risk as far as practical before putting it on the household TV. No current image, recovery procedure or hardware experiment is qualified. No persistent TV change is authorized by this plan. The family-source and emulator work continues without touching the TV.

Risk cannot be made zero by software tests. The effective strategy is to keep development failures off the household unit, prove the relevant restore path on a matching lab assembly, and decline a household experiment if an uncovered irreversible failure remains. A complete review packet is necessary but cannot certify that its claims are true.

## Ordered work, deliverables and stop conditions

| Order | Work now / deliverable | Completion evidence and dependency |
| --- | --- | --- |
| 1 | Offline boot/media dependency analysis. Reproduce source hashes, review actual call paths, identify executable firmware, secure-world calls and diagnostic side effects. | Hashed findings with applicability limits. Media callback hazard is recorded in `research/MEDIA_SOURCE_FINDINGS.md`. Exact installed-board applicability remains unresolved. Do not run vendor diagnostics to resolve it. |
| 2 | Establish exact board, revision, SoC, storage, panel and One Connect identities and match source to installed build. Obtain documented trust-chain and recovery information. | Independent corroboration of actual-unit identity, not a same-model parts listing. Current normal SDB cannot supply this. Seek authoritative documentation and externally accessible non-unique labels first; no service menu, disassembly or electrical connection is included. |
| 3 | Resolve independent boot and legitimate media eligibility before a board port. Inventory all execution/storage domains in the provenance ledger. | Exact-chip boot/signing policy and a supported independent provisioning/client path. If immutable or indispensable Samsung code contradicts the requirement, report the incompatibility and seek a scope decision. Do not conceal it beneath a launcher. No full AOSP checkout/board selection on a marketing-family guess. |
| 4 | Build the selected platform offline and reproduce its inputs, artifacts and configuration. Continue Home/controller tests and complete agentOS integration under its authorized repository lane. | Clean-build artifact hashes and dependency/license records; static image inspection; CI and emulator lifecycle, authority, network-loss and persistence tests. Emulator success does not qualify board drivers, standby or protected playback. AgentOS broker work remains dependent on its owning lane. |
| 5 | Qualify a matching lab assembly and independent recovery before experimenting on the household unit. | Match board/revision, relevant peripheral revisions and actual write domains. Use a qualified technician and exact electrical documentation where needed. A loose, different board is not an equivalent test. Acquisition, opening enclosures, tool connections and power procedures require their own concrete proposal; none is performed or purchased here. |
| 6 | Rehearse the exact candidate on that lab assembly, beginning with a documented nonpersistent boot route if one exists. | Instrumented boot, hardware safety, original remote and wake. Audit *all* side effects, including controller firmware loads, secure-storage counters and calibration; RAM boot alone does not guarantee no persistent effects. Test only failure modes covered by a restore route independent of the failing stage. Never deliberately corrupt the household TV to prove recovery. |
| 7 | Qualify media/product parity on the lab assembly. | Stock baseline and same-condition provider sessions, actual negotiated resolution/HDR/cadence/audio, exact-title selection and stop-at-end, agentOS observation/control, manual interruption, offline use and measured performance. Confirm six app targets separately; Hulu and Apple TV are UI selections, not already qualified services. |
| 8 | Produce and independently review one exact household experiment packet. | Target/revision, candidate digest, complete ordered read/write/side-effect inventory, restore artifacts and coverage, preconditions and measured abort limits. Recheck identity, image and power/recovery conditions at the session. Present the concrete proposal for separate owner authorization only after review; no generic flashing command is acceptable. |
| 9 | Perform only that authorized experiment, verify actual state, then consider persistent installation. | Measured boot/hardware/media results and repeatable recovery. A persistent install needs its own reviewed packet, stable release signing/update policy and rollback/migration tests. Stop if any evidence differs; never improvise a repair write. |

Steps 1 and the packet tooling are implemented in this change. Steps 2–3 are the critical external evidence dependencies. Steps 4–9 are not marked complete by writing this plan. UI refinements do not outrank boot, recovery or protected-media feasibility.

## Read-only packet auditor

Run from the repository root:

```sh
python3 tools/audit_experiment.py docs/deployment/experiment-packet.json
```

The checked-in packet deliberately exits **2**: exact board/revision, candidate image and all eight experiment proofs are missing. It is not an install manifest and contains no executable commands. The auditor has no device/network/subprocess operation and no override, approval or write mode.

A private candidate packet can use `--evidence-root PRIVATE_DIRECTORY`. Each `artifact`/`evidence` descriptor has a canonical relative `path`, exact `bytes` and lowercase `sha256`. Keep images, backups, raw captures, identifiers and provisioning private. Each documented gate binds to the complete target and candidate image digest. A changed image or target requires renewed evidence/review. Unknown fields, missing/duplicate gates, symlink/escaping paths, absent/changed files and out-of-budget inputs are rejected. JSON duplicate keys are rejected by the CLI.

Packet schema **2** additionally binds `one_connect_model`, `one_connect_assembly`, `power_label_code` and `panel_id` in the target. Schema 1 is rejected because it cannot bind changed peripheral identities. Every documented gate must match the full expanded target as well as the candidate image digest; changing any one field invalidates the recorded scope. These labels do not establish firmware equality or physical compatibility, and cannot substitute for compute-board/revision or panel identity. Renew the technical evidence/review rather than simply changing an old packet's version number.

The public packet leaves these fields null. Owner-unit label observations, photo provenance and filled packets stay in ignored `.local/` storage unless their publication is separately authorized. Run a private filled packet by passing its local path; do not copy raw labels, tracking strings, serials, photographs or private source hashes into public metadata. Supplier listings describe catalogue items, not the installed unit or an authoritative bill of materials; do not promote their part numbers to observed board facts or a purchase/boot recommendation.

Exit 0 means only a structurally complete, hash-consistent review packet. Exit 2 means missing evidence; exit 3 means invalid/unavailable/mismatched evidence. **Every result keeps `hardware_safety_verified` and `authorization_granted` false.** A synthetic packet can pass; fabricated documentation can too. Hashes identify bytes, not authorship or truth. This is a local snapshot checker, not a privileged security boundary or protection against concurrent hostile filesystem changes. Any future execution mechanism must reopen/reverify the artifacts at use and enforce separate authority; it does not exist here.

## Evidence required in each gate

| Gate | What an independent reviewer must establish |
| --- | --- |
| identity | Actual board/revision, SoC/ABI, all relevant peripherals, installed build/source correspondence and the candidate's applicability. No serial/key material in public evidence. |
| boot_trust | Executing boot and secure-world chain, accepted authorities, rollback/OTP effects, complete proposed side effects and the documented trial route. Root/USB update availability is insufficient. |
| software_provenance | Every required mutable/immutable executing component and recovery copy; independent replacement provenance and license. Explicitly resolve embedded firmware, not only Linux source. |
| build_reproduction | Pinned source/toolchain/binaries/configuration, independent clean rebuild comparison, artifact/partition bounds, image format/signature and analysis of startup side effects. Record nondeterminism rather than calling an unreproducible build reproducible. |
| bench_rehearsal | Matching lab configuration, exact candidate, observed boot/remote/power/display/audio/thermal behavior, external measurements and declared uncertainty. Any divergence blocks transfer to household hardware. |
| recovery | Per-write-domain restore path independent of every affected stage, private verified backups and calibration handling, available tools, timed rehearsal and uncovered failure modes. Factory reset cannot stand in for early-boot recovery. |
| stock_baseline | Actual baseline picture/audio/media eligibility, remote behavior, timing and network observations, collected without protected-frame/credential capture. Unknown baseline means no parity claim. |
| provider_route | Legitimate independent protected-path/provisioning/client availability for the exact build and ownership policy; then provider session evidence before release. A generic DRM label is insufficient. |

Independent review must inspect these claims, not just tick fields. External timing, negotiated stream data, calibrated output measurements and network observations cross-check software assertions. Review also checks that the proposed experiment does not depend on the untested thing as its only recovery mechanism.

## Present disposition

**Continue offline; no TV experiment.** Normal connection setup is resolved and must not be repeated as busywork. Needed next: authoritative actual-board identity/boot/recovery evidence and a legitimate exact-chip media integration route. If they cannot be obtained through documented noninvasive paths, the next proposal is a separately scoped matching lab/technician investigation—not a speculative command on the owner's TV.

Primary architectural references checked 2026-10-15: [AOSP bootloader responsibilities](https://source.android.com/docs/core/architecture/bootloader), [DRM hardware/software integration](https://source.android.com/docs/core/media/drm), [conditional A/B update design](https://source.android.com/docs/core/ota/ab). These describe Android architecture, not support or recovery for this Samsung board.
