# Original remote and responsive navigation

Reuse the owner's existing Samsung remote as the normal controller. No replacement remote, phone, agentOS connection, or internet connection is required for everyday TV operation. Preserve the stock-supported interaction and playback quality while making interface changes as fast as the hardware permits. These are release requirements; the current Android application has not been tested with this remote or on this TV.

## Remote integration

Identify the actual remote model, receiver hardware, pairing mechanism and per-button transport from target evidence. Do not assume every button uses the same transport or that a standard Bluetooth HID implementation covers pairing, microphone audio, wake or long presses. Samsung's [2025 remote guide](https://www.samsung.com/my/support/tv-audio-video/samsung-solarcell-remote-guide-2025-model/) and [pairing guide](https://www.samsung.com/uk/support/tv-audio-video/how-to-charge-and-use-the-samsung-solarcell-remote/) are starting references; neither proves custom-OS compatibility for the owner's unit.

Map independently implemented receiver drivers and Android input configuration to stable domain actions. Handle key-down/up, repeat, simultaneous keys and short/long presses without double delivery. Keep input processing and local UI response independent of agentOS. Physical input interrupts agent navigation immediately; an agent must not replay queued navigation against a screen the owner has changed.

| Control where present | Required behavior |
|---|---|
| D-pad and Select | Predictable focus, repeat, activation and scrolling in Home, settings and provider applications. Restore focus and scroll position on return. |
| Home and Back | Home always returns to the owner interface; Back follows a consistent navigation stack. Final system routing belongs in the OS, not a provider-specific workaround. |
| Volume rocker and mute | Preserve gestures, repeat, mute and the actual speaker/receiver routing, including the owner's CEC/eARC arrangement where used. |
| Power and artwork gestures | Preserve the established short/long-press distinction, artwork entry/exit, standby and wake behavior after measuring the actual remote. Do not invent a hard-coded duration from a different model. |
| Playback and shortcut buttons | Route playback to the appropriate media session; map present service buttons to installed provider activities. Do not send ordinary navigation through a cloud assistant. |
| Voice, channel and multifunction controls | Inventory actual stock-supported functions and implement the relevant independent path. Microphone transport and voice processing require their own qualification; Samsung cloud speech is not a hidden dependency. Expose owner-editable mappings without losing basic navigation. |
| Pairing and recovery | Pair/re-pair using supported hardware mechanisms, preserve pairing across reboot and updates, and test lost pairing and recovery independently of Home. Never publish pairing secrets or stable radio identifiers. |

The existing physical remote is reused as an accessory. Record its own firmware provenance separately; reuse does not authorize retaining Samsung receiver, standby or platform software on the TV. If a required remote function depends on such a retained component, record that specific integration blocker rather than silently replacing the remote or claiming software removal.

Wake needs a functioning receiver/standby path while the main OS sleeps. Qualify that path and its power consumption before promising rapid wake. An Android service cannot receive network or key events while its processor is unpowered.

## Architecture for low latency

Keep Home, settings, artwork selection and overlays in one native application with lightweight navigation between screens. Retain recent local UI state and bounded caches so returning Home does not reconstruct the experience or refetch assets. Keep provider applications as native activities; preserve their normal lifecycle and media-session behavior.

On an app switch, show the destination or immediate local feedback without waiting for catalog metadata or network results. Reserve enough memory for Home to recover quickly, but measure the budget on the actual board. Do not pin every provider in RAM, keep hidden video sessions decoding, disable thermal control, or reduce video/HDR quality to win a navigation benchmark. Warm-resume supported clients when memory and their lifecycle allow; report cold starts separately.

Keep filesystem access, image decoding, model calls, configuration validation, logging, network traffic and synchronous persistence off the frame/input path in the production implementation. Precompute bounded layouts and thumbnails, apply prepared experience revisions atomically, and retain focus using stable IDs. Coalesce obsolete events and cancel obsolete asset work. A slow provider or unavailable agent must not stall local navigation. The prototype now runs configuration I/O, validation, atomic saves and app discovery on a background worker, with activity-retained state and stable tile focus restoration. Profile it before treating it as the production implementation; actual frame timing, memory behavior and target-TV latency remain unmeasured.

Use short, interruptible transitions; target at most 150 ms for decorative animation and provide a reduced-motion setting. Input takes effect during transitions rather than waiting behind them. Preserve safe regions for the current artwork/video composition and avoid protected-surface churn. Display-mode and HDMI handshakes must be measured separately; no artificial fixed delay should be added around them.

## Measurement and provisional budgets

The release gate is no regression against the stock TV under comparable conditions. The numbers below are initial engineering goals for local interactions, not measured results or guarantees about provider/network startup. Revisit them with exact-board evidence; do not relax the stock-parity requirement implicitly.

| Interaction | Initial goal | Definition |
|---|---|---|
| Remote navigation feedback | p95 at most 100 ms | Physical button actuation to visible focus/feedback, including receiver and display latency. |
| Switch between owned screens | p95 at most 150 ms | Key actuation to interactive destination with correct focus; decorative completion is recorded separately. |
| Return to warm Home | p95 at most 250 ms | Home button actuation to an interactive, correctly restored Home, including a return from active playback. |
| Frame pacing | Fit the active refresh deadline | At 60 Hz the frame interval is about 16.7 ms; measure actual refresh and missed frames rather than assuming 60 Hz for this panel. |
| Provider switch, cold launch and wake | At least stock parity; minimize measured latency | Report first feedback, first interactive UI, first video frame and stable output separately. A splash screen is not an interactive result. |

Measure p50/p95 and worst observed latency with sample count and conditions, not averages alone. Use external high-frame-rate video for button-to-display timing and Android traces/frame timing to locate scheduling, input, disk, GPU and process-start delays. Record release build, remote transport, title/plan, client version, display mode, network state, thermal state and time since boot. Start with at least 30 repetitions per transition and expand samples where tails are unstable.

Exercise Home ↔ each of Netflix, Prime Video, Disney+ and YouTube; app ↔ app through Home; settings/overlays during playback; artwork ↔ viewing; standby/wake; and navigation during household-agent edits. Repeat offline local operation, cold boot, warm use, memory pressure, background updates and sustained UHD/HDR playback. Check responsiveness, dropped/repeated keys, focus continuity, audio, HDR transitions, frame cadence, memory pressure, temperatures and standby consumption together.

A faster benchmark does not pass if it loses settings, breaks the existing remote, leaves a stale secure surface, restarts playback unnecessarily, or compromises current picture/audio quality. Publish measured results only after target testing; no such results exist yet.
