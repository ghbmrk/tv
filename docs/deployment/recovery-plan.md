# Recovery qualification

Status: unverified for QN50LS03FAFXZA. Persistent device modification is not authorized by this record.

For each proposed write, document the affected storage/controller and exact failure modes. Identify the independent restore mechanism, hardware/tool dependencies, required off-device artifacts and their digests, unique private data excluded from public records, and a measured restoration test. Explicitly state uncovered failures.

RAM/alternate boot also requires a side-effect review before execution. The released family controller driver starts a watchdog thread during message-device probing; its ordinary branch attempts a rollback-control message and periodic liveness messages. Initialization can therefore affect an external controller even without an explicit flash operation. This is source evidence, not installed-unit behavior. Establish the actual controller, active branch, watchdog deadlines, boot-health semantics and recovery coverage before any candidate kernel runs. Do not use the vendor driver to discover those effects on the household TV. See the [controller and recovery investigation](../../research/CONTROLLER_AND_RECOVERY_FINDINGS.md).

The [secure-world source review](../../research/SECURE_WORLD_FINDINGS.md) also shows that loading the family `tzdev` driver invokes monitor initialization, storage/RPC startup and file deletion/creation. A version-reporting path is not thereby a passive probe. Review full initialization effects before any module load; no monitor, storage or sysfs operation is authorized by this finding.

Required cases: invalid OS image, failed kernel start, unavailable Home/network, interrupted update, incompatible configuration migration, corrupted boot stage, and any changed secure-world or peripheral firmware. Mark unsupported cases as blockers for experiments that could cause them. Record whether restoration depends on software the experiment would overwrite.

No USB update ZIP, factory reset, temporary root method, or backup has yet been demonstrated to restore an unbootable target. Board-specific restore commands will be written only after the relevant mechanism and storage map are verified.

## Failure coverage required for the exact experiment

All current entries are **unverified**, not accepted risks. Fill each with the exact affected domain, independent restore dependency, digest-bound private artifacts, matching-lab demonstration and measured outcome. A failure that the experiment cannot cause may be excluded only with reviewed side-effect evidence.

| Failure | Required independent recovery proof | Current evidence |
| --- | --- | --- |
| Invalid image or failed kernel startup | Restore works without the candidate kernel, Home or network | None |
| Home/controller unavailable | Physical recovery route preserves valid configuration and cannot depend on either process | Emulator default/undo tests only; hardware recovery unverified |
| Power loss during an update | Actual storage/boot design preserves or restores a known-good chain | None; A/B support unknown |
| Bad configuration or migration | Last-known-good recovery without accepting a corrupt/newer incompatible store | Native domain tests exist; release-image migration/rollback qualification pending |
| Early boot stage corrupted | A restore mechanism outside the changed stage and all its dependencies | None; do not alter early boot |
| Secure-world/RPMB/rollback/OTP change | Proven recoverability of each effect, including monotonic state | None; no fuse/counter/key/RPMB writes |
| Panel/One Connect/controller firmware or calibration affected | Restore works with main OS unavailable and retains exact private calibration | None; no controller update/calibration operation |
| Lost remote/network or deep standby | An independently demonstrated physical/wake route | None on the replacement system |

Do not deliberately inject destructive faults on the household unit. Rehearse covered failure cases on a verified matching lab assembly; software simulations can test orchestration but cannot certify electrical/storage recovery. A backup hash proves byte integrity, not coverage, consistency, readability after failure or successful restoration.

Before a household proposal, the reviewer must name all uncovered failure modes and reject any experiment that could cause one. The [off-TV plan](OFF_TV_READINESS.md) and read-only packet auditor organize evidence; neither grants authorization or certifies recovery.

## Early-memory initialization

The [DDR package investigation](../../research/DDR_PACKAGE_FINDINGS.md) identifies three bounded but unclassified payloads in the shared update. Its FIP-shaped table does not establish a standard TF-A loader or recovery route. Any experiment that can prevent DRAM bring-up requires recovery that does not depend on that successful bring-up. Do not replace memory-initialization data/code, repack the table or assume a working Linux network service covers that failure. The exact hardware, loader, payload roles and independent recovery remain unverified.
