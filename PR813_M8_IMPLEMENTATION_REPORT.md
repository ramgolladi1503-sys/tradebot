# PR813 M8 implementation report

Base: `3510a4984e5d5defd4157b3101558889213d477c` (M7 independently passed).

M8 makes `feed_epoch` the currentness field in feed runtime provenance and removes legacy recovery/subscription-generation mismatches from health blocker derivation. Legacy values remain in runtime, health, debug, and decision telemetry payloads for diagnostics and compatibility. Artifact acceptance continues to require the current `feed_epoch`, canonical integrity, runtime session, and M7 truth lineage.

The websocket/MEG reconnect-generation fields were classified as local lifecycle and request/tick causality identities, not feed artifact currentness authority; they were not removed in this slice.

## Safety

No live runtime was launched. No broker API or order action was performed. Broker write, order, paper, and live authorization remain false.

## Validation

Focused M8 and M7 tests cover current/stale epoch conflicts, legacy mismatch non-authority, supervisor/recovery health behavior, artifact acceptance, and lineage preservation. Compile and `git diff --check` are required before freeze. Independent review is required after the exact M8 commit and is not claimed by this implementation report.
