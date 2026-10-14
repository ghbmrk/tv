# Recovery qualification

Status: unverified for QN50LS03FAFXZA. Persistent device modification is not authorized by this record.

For each proposed write, document the affected storage/controller and exact failure modes. Identify the independent restore mechanism, hardware/tool dependencies, required off-device artifacts and their digests, unique private data excluded from public records, and a measured restoration test. Explicitly state uncovered failures.

Required cases: invalid OS image, failed kernel start, unavailable Home/network, interrupted update, incompatible configuration migration, corrupted boot stage, and any changed secure-world or peripheral firmware. Mark unsupported cases as blockers for experiments that could cause them. Record whether restoration depends on software the experiment would overwrite.

No USB update ZIP, factory reset, temporary root method, or backup has yet been demonstrated to restore an unbootable target. Board-specific restore commands will be written only after the relevant mechanism and storage map are verified.
