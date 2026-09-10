# V28 full regression report

Targeted V28 tests: **18 passed**. Python compilation and `git diff --check`
passed.

The explicitly identified acceptance-relevant subset (acceptance gate,
production-equivalent CAS suite, feed-soak contract, runtime guard, lifecycle
shutdown, shutdown clean, and V28 disk tests) passes: **38 passed**.

The expanded CAS/future-leakage/ingestion/shutdown group passes: **71 passed**,
including CAS primitive producer, CAS runtime, coordinator lifecycle,
consumer contract, no-future-leak replay, dataset leakage, and shutdown
manager coverage.

The full repository run was not green: **2,147 passed, 75 failed, 28
deselected**, and was interrupted after 152.75 seconds. The first collection
run also failed on missing optional dependency `zstandard` in
`tests/upstox_capture/test_capture_validation_sequence.py`. The broader
failures include repository-backed tests resolving relative fixture paths and
subprocess working directories that are unavailable from this mounted
successor; they are not attributable to the V28 disk-gate files, but they
prevent acceptance.

Decision: no successor commit and no verification ref. The validated f44e637
runtime and canonical checkout were not modified.
