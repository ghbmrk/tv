# Implementation roadmap

The first vertical slice is the local experience format, revision store, editing API/studio, and native TV shell import path. The final system also requires the board port, qualified native playback, production agentOS control, and recovery. Completion of one workstream is not evidence for another.

| Next package | Deliverable | Acceptance |
|---|---|---|
| Native shell qualification | Local APK/JVM/lint and four API 36 TV emulator tests pass; Linux x86_64 TV CI also passed; PR #1 merged. | D-pad/focus, import callback, persisted read-back, invalid files and reset/recovery covered. Actual system picker, physical remote and provider launch remain separate qualification work. |
| Experience composition | Component catalog, local artwork collections, timers, content sources and scene transactions. | New screens/layouts/content through the API, offline rendering, bounded resources, preview/apply/undo and regression tests. |
| Paired control service | Android service with pinned identity and typed domain operations separate from renderer. | No unpaired calls, narrow privilege bridge, durable receipts, state reconciliation and physical-remote priority. |
| agentOS device integration | Qualified device declaration, executor, broker operation classification, grants, events, audience/capture enforcement. | End-to-end household editing and provider control through agentOS without direct guest LAN access. Backend changes follow the agentOS owning team's lane/review process. |
| Target source inventory | Official family source acquired, hashed and bounded kernel inspection complete; establish exact board and installed-build correspondence. | Evidence-backed board/BSP/HAL map, provenance ledger, storage and recovery records. |
| Independent boot experiment | Independently sourced boot/kernel/platform integrations and bounded hardware session. | Original-board boot and hardware safety through a verified recovery-covered path. |
| Provider qualification | Independently provisioned protected path and all four official TV clients. | Stock-supported resolution/HDR/cadence/audio under comparable conditions, with agent controls active. |
| Owner installation | Signed reproducible build inputs, exact-board manifest, qualified installer/restore procedure. | Interrupted-update recovery, offline operation, final provenance/removal and media/agentOS acceptance. |

Current limits and the full target sequence are in [deployment/PLAN.md](deployment/PLAN.md); implemented API coverage is in [API.md](API.md). No real-device milestone is marked complete without target evidence.
