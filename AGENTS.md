# Project instructions

Reason from first principles and use exact-device evidence. Read README.md, docs/deployment/PLAN.md and docs/agentos-integration.md before changing architecture. Preserve original hardware, Samsung software removal, equivalent playback quality, local ownership and full household-agent editing requirements unless the owner explicitly changes scope.

Never claim a host preview, Android APK, temporary root, stock launcher or external streamer demonstrates an independent port. Do not invent board IDs, drivers, flash offsets, DRM support or recovery procedures. No persistent hardware write before exact identification, independent boot analysis, proven recovery and applicable safety gates.

Keep provider credentials, device identifiers, tokens, signing/DRM keys, raw owner photos, private inputs and vendor firmware/source archives out of Git and logs. Public research may include model/build and bounded metadata with provenance. Unknown provenance remains unverified.

Run `python3 -m unittest discover -s tests -v` and `python3 tools/check_public.py`. Build Android with the pinned toolchain and run lint when that environment is available; otherwise state the missing validation. Production agentOS integration follows its broker/executor/grants model, not direct guest LAN access. No arbitrary executable content in experience documents. Test persistence, conflicting edits, uncertain effects and authority boundaries when changing the editing core.
