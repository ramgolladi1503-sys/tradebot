# V33A mount-loss and device-change semantics

If the expected volume disappears, becomes non-directory, becomes unwritable, resolves elsewhere, or changes device ID, the observer must:

- stop accepting new market-data writes;
- preserve the last confirmed state and explicit failure reason in already-authorized storage if available;
- avoid fallback to internal disk or system temporary storage;
- enter a fail-closed terminal state requiring governed operator review;
- report `storage_authority=LOST`, never `PASS` or `RECOVERED` without a fresh probe.

A reconnect is not storage recovery. Recovery requires a new presence, realpath, device, writable, and same-directory-temp probe, followed by an explicit session transition. No order or broker-write path is reachable in any state.

Current host probe: volume present, writable, device stable at `16777240`. Mount-loss runtime behavior remains a required negative-control test, not live proof.
