# Read-only target identification

`tools/identify_tv.py` makes one fixed `GET /api/v2/` request on port 8001 at an owner-supplied private LAN IPv4 address. It performs no discovery, authentication attempt, shell command, remote-key action, setting change, sideload or firmware write. Public addresses, hostnames, subnets and implicit loopback are refused. Redirects are not followed; JSON/body bounds and socket timeouts apply.

Replace `TV_PRIVATE_IPV4` with the actual address shown in the TV's ordinary network settings:

```sh
python3 tools/identify_tv.py TV_PRIVATE_IPV4
```

The default output is ignored `.local/tv-identification.json`. Only allowlisted fields survive: recognized full SKU or LS03F family model, matching software-family build syntax, optional developer/Frame flags and bounded reported UI resolution. Unknown model/build strings become null. Raw responses, serials, device IDs, MAC addresses, network details, household names, tokens and arbitrary fields are discarded. Errors never echo raw server status lines or bodies. Review sanitized evidence before publishing it.

The endpoint appears in [primary research on a 2019 Q60R](https://labs.reversec.com/posts/2019/12/opening-up-the-samsung-q60-series-smart-tv); later read-only requests on the owner's LS03F reported the matching full SKU, Frame support and a 3840×2160 UI surface. The software-build field was unrecognized and remains null; the photographed build remains the installed-build evidence. A reported resolution is not decoded stream resolution or quality evidence. HTTP is unauthenticated, so matching reported fields do not establish physical board identity or permission for writes.

A bounded standard SSDP attempt was also made from the development host on 2026-10-15. Both the default route and an explicitly selected active physical interface rejected multicast send with OS error 65 (No route to host). No response or matching TV was obtained. This does not establish that the TV is offline or that a direct request to its actual IP will fail. No routes, privacy settings, VPN configuration or TV settings were changed. Private interface addresses remain outside Git.

A reachable path subsequently became available; this is historical discovery context, not the current blocker. If the endpoint is unavailable, preserve that outcome and review documented developer-access prerequisites; do not turn the failure into automatic rooting or a request to change firmware. Exact SoC/board/ABI, storage, boot trust, controller provenance and recovery still require their own evidence beyond this endpoint.

A subsequent Bonjour-discovered Samsung candidate also failed the same fixed GET with OS error 65, including one retry with host-network permission on 2026-10-15. No model response establishes that candidate as the owner's LS03F. The ordinary command sandbox alone does not explain the permitted retry's failure; the underlying network/host/TV cause remains undetermined. The [safe hardware-session procedure](../research/FEASIBILITY.md#safe-collection-for-the-next-hardware-session) starts with the address shown by the TV, without automatic network or Developer Mode changes.


## Current access boundary

[Sanitized retained observations](../research/target-access-observations.json) record the later successful HTTP reports, developer-mode transition and eventual reachability of ports 8001 and 26101. Official SDB 4.2.36 failed to establish a device session. A passive connection to 26101 received no unsolicited bytes and was closed by the peer after approximately 63 ms, before client application data. That proves connection/closure behavior only, not a firewall, allowlist, firmware or protocol diagnosis.

The API-reported developer-host field was valid IPv4 and matched neither the current Mac address nor the TV address in the private comparison. The owner reports entering one of the supplied addresses; the discrepancy remains unresolved because the API field may be stale or represent something different. No incorrect user entry is inferred. The earlier `0.0.0.0` value was a placeholder, not evidence of a working developer-host configuration.

No additional reboot or setting change is prescribed while off-TV implementation continues. A later access session should first reconcile the displayed Developer Mode host field with the retained comparison, then attempt one bounded official SDB connection if authorized. Preserve the outcome; do not escalate automatically to root, sideloading or firmware changes. Public records exclude all private addresses and unique device identifiers. No new TV connection was made to reconcile these documents.

A subsequent read-only check at 2026-10-15 16:27 UTC again reported the full target SKU and Developer Mode enabled. Official SDB 4.2.36 connection still failed (exit 1). No TV shell command, setting change or installation was attempted. HTTP reachability does not resolve the developer-access blocker.
