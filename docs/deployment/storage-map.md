# Storage map — not established

Target model/build: QN50LS03FAFXZA / T-PTMFAKUC-0090-1301.0. Exact board/revision and storage devices remain unknown. This document contains no addresses, offsets, sizes, partition names or proposed writes because none are verified for the actual unit.

Required evidence before filling the map:

- Exact storage part, controller, access method, geometry, address units, erase/write granularity and firmware revision.
- Boot ROM, OTP/fuses, boot stages, secure world, RPMB, main OS, recovery/inactive copies, controller/One Connect/panel stores and calibration domains. Distinguish volatile microcode loads from nonvolatile storage; do not assume firmware is only in a file partition.
- For each domain: authenticated source of the mapping, read/restore coverage, protection/signing/rollback behavior, unique data handling and proposed experiment exposure.
- Independent cross-check of every range and boundary. Update-container offsets are file offsets, not flash addresses. A same-model listing or kernel-family source is not a target partition map.

No raw storage read, RPMB operation, register probe, service menu or flash command is authorized to fill this table. Review a documented collection method's real side effects first; even a readable diagnostic can modify hardware (see `research/MEDIA_SOURCE_FINDINGS.md`).
