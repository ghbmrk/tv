# Read-only target identification

`tools/identify_tv.py` makes one fixed `GET /api/v2/` request on port 8001 at an owner-supplied private LAN IPv4 address. It performs no discovery, authentication attempt, shell command, remote-key action, setting change, sideload or firmware write. Public addresses, hostnames, subnets and implicit loopback are refused. Redirects are not followed; JSON/body bounds and socket timeouts apply.

Replace `TV_PRIVATE_IPV4` with the actual address shown in the TV's ordinary network settings:

```sh
python3 tools/identify_tv.py TV_PRIVATE_IPV4
```

The default output is ignored `.local/tv-identification.json`. Only allowlisted fields survive: recognized full SKU or LS03F family model, matching software-family build syntax, optional developer/Frame flags and bounded reported UI resolution. Unknown model/build strings become null. Raw responses, serials, device IDs, MAC addresses, network details, household names, tokens and arbitrary fields are discarded. Errors never echo raw server status lines or bodies. Review sanitized evidence before publishing it.

The endpoint appears in [primary research on a 2019 Q60R](https://labs.reversec.com/posts/2019/12/opening-up-the-samsung-q60-series-smart-tv); operation and field availability on the owner's 2025 LS03F are not yet observed. The tool has passed synthetic local HTTP tests only. A reported resolution is not decoded stream resolution or quality evidence. HTTP is unauthenticated, so matching reported fields do not establish physical board identity or permission for writes.

A bounded standard SSDP attempt was also made from the development host on 2026-10-15. Both the default route and an explicitly selected active physical interface rejected multicast send with OS error 65 (No route to host). No response or matching TV was obtained. This does not establish that the TV is offline or that a direct request to its actual IP will fail. No routes, privacy settings, VPN configuration or TV settings were changed. Private interface addresses remain outside Git.

An actual TV address/reachable network path is now required to execute this check on target. If the endpoint is unavailable, preserve that outcome and review documented developer-access prerequisites; do not turn the failure into automatic rooting or a request to change firmware. Exact SoC/board/ABI, storage, boot trust, controller provenance and recovery still require their own evidence beyond this endpoint.
