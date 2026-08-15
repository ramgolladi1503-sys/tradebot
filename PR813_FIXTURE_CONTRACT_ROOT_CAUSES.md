# PR813 fixture contract root causes

## Runtime-health fixtures

The three old fixtures omitted the canonical session, writer, schema, feed epoch, produced-at, and lineage contract. They were accepted by pre-M1-M9 behavior but correctly rejected by the canonical loader. The tests now use the shared factory and retain fail-closed assertions for malformed artifacts.

## Phase 2 fixtures

The 32 Phase 2 tests supplied candidates without a current canonical feed-runtime artifact. The shared autouse fixture creates a valid truth/runtime pair in the test runtime root, and Phase 2 still calls the production `load_current_feed_runtime()` path. No raw `feed_ok` or loader bypass was added.

## Negative controls

The factory test rejects wrong run ID, boot epoch, feed epoch, writer, schema, snapshot hash, missing lineage, missing/malformed truth, and same-identity mutated truth.

FIXTURE_ROOT_CAUSES_UNKNOWN=0
