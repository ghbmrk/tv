# Controller initialization and embedded recovery investigation

Observed October 23, 2026, entirely offline against the previously acquired official family source and shared update. No vendor code, controller command, TV connection or storage write on the TV was executed. This extends the [native verifier trace](BOOT_VERIFIER_FINDINGS.md), not hardware readiness.

## Consequence for bring-up

A candidate RAM boot cannot yet be classified as harmless. The released family controller-message driver starts a watchdog thread during probing. Its ordinary branch attempts a rollback-control message and periodic liveness messages; its EPAPER branch differs. A running kernel can therefore affect controller state without a flashing script. The installed branch, controller semantics and effect persistence are unknown. Review these dependencies before a minimal kernel trial; do not discover them by running the vendor driver on the household TV.

The [inventory](controller-recovery-inventory.json) binds the observations to exact files, line ranges, hashes and independently checked native calls. The [source inventory](platform-dependency-inventory.json) now includes `msg-wt61p807.c`. Lexical markers locate evidence; the manual source observations establish the narrower control-flow claims below. Neither proves the installed build matches the release.

## Controller transport

The checked MICOM library's device initialization references `/dev/micom-msg`. The message transport contains a direct call to the `ioctl` import thunk. Original ELF file mapping, instruction hash and Thumb BLX destination pass the separate call checker. This establishes a call instruction, not a successful ioctl or its physical effect.

Released `msg-wt61p807.c` registers that device name and its message ioctl handler. The acknowledged-message branch copies a request from userspace, transmits it, waits for an acknowledgement, may retry and returns data. Its completion is transport-level evidence; it does not establish durable state, safe replay or a qualified recovery transaction. The callback checks acknowledgement command identity, not the replacement project's independently verified postcondition. The exact userspace/kernel request ABI and actual runtime binding remain unverified; a matching pathname does not settle them.

Probe starts the watchdog thread before marking the message device ready. The ordinary thread's initial rollback-control attempt and periodic liveness messages make startup behavior part of the boot/recovery contract. Unknown active build conditions, failure behavior, controller watchdog deadlines and rollback semantics remain installation blockers. No timeout value from this family source is a qualified deadline for this TV.

## Controller firmware candidates

The source archive contains eight bounded PontusM release `.bin` files, including one whose name contains `FRTV`. Their ZIP reads passed CRC, and their sizes and SHA-256 digests are recorded without redistributing bytes. The filename does not select this TV's firmware. None has been identified as the installed controller image or an independent implementation. Source availability for a Linux transport driver is not source availability for the controller program.

Do not flash these candidates, use their apparent product suffixes to select hardware, or retain a Samsung controller binary as the final replacement. Determine exact execution/storage domains, firmware authorship, independent implementation and recovery before selecting a controller route.

## Embedded stream in `seret.bin`

The 3,661,824-byte decoded update section matches its previously recorded CRC and SHA-256. A bounded scan finds two XZ magic candidates. One fails header CRC. The other is a complete 2,002,476-byte stream whose XZ CRC32 integrity check passes; it decodes to 4,952,320 bytes, SHA-256 `a60e1b13bd45c952647427d15799d01d72bde6fdc531a9205a574f1d3ad76e51`. The decoded payload contains a Linux version token `5.4.261`.

This is a Linux-bearing payload in a named update section, **not an independently bootable recovery image**. An ELF magic candidate has an invalid class, and both FDT magic candidates fail structural validation. No executable architecture, selected DTB, entry point, image-signature policy, early boot dependency or installed recovery mechanism follows. The update publisher's signature has not been authenticated; an XZ integrity check is not authenticity or permission to boot modified code.

Reproduce the stream metadata from the private decoded section:

```sh
python3 tools/inspect_embedded_xz.py --file PRIVATE_SERET_BIN --output .local/seret-xz.json
python3 -m unittest tests.test_embedded_xz -v
```

The tool bounds input, candidates, decoder memory and total decoded output; rejects incomplete/corrupt streams and absent payload integrity checks; and exports only metadata and bounded numeric version tokens. Tests cover embedded/trailing bytes, false headers, corrupt/truncated streams, aggregate expansion limits and omission of private text. It never exports decoded payloads or executes them. Native call reproduction uses `tools.check_native_calls.inspect` with the inventory's `micom_transport` record and the exact private MICOM ELF. Native analysis closed without pending cleanup.

## Remaining decision boundary

These results narrow what a replacement must implement and what a trial could affect. They do not establish independent boot acceptance, Samsung-free controller firmware, complete recovery or provider-quality media. Exact installed board/controller correspondence and an independently demonstrated restore mechanism remain required. The [recovery plan](../docs/deployment/recovery-plan.md) now explicitly includes implicit initialization effects, even for a proposed RAM boot.
