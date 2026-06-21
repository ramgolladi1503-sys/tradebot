# PR 600: Telemetry Schema and Paths

## Agent Work Contract
This PR resolves telemetry schema mismatches, adds persistence compression for logger identity, and addresses hardcoded paths for test isolation. 

## Scope Guard
In scope:
- `core/ranking_telemetry.py` setup
- `core/persistence_state_compression.py` inclusion
- `test_no_hardcoded_paths_repo_wide.py` path allowlist updates
- Telemetry logging hooks in `core/decision_logger.py` and `core/reject_shadow.py`

Out of scope:
- Live strategy changes.
- Market data feed logic.
- Broker API integrations.

## Grill Me Review
We assume telemetry state compression logic doesn't hide actual new states. This assumption is handled because the hashing specifically checks for all content fields.

## Hermes Review
Architecture bounds the telemetry components cleanly and limits DB operations to explicitly specified test paths.

## GSD Review
Delivery check:
- Tests pass.
- Schema initialized.
- Paths clean.

## QA / Safety Review
- No live broker changes.
- Safe path adjustments do not leak production data.

## High-Risk Path Review
The paths `core/reject_shadow.py` and `core/decision_logger.py` are part of the core/execution boundary. No execution logic was altered, only logging and persistence.

## Acceptance Proof
All pytest suites are verified green (`pytest tests -q` ran with 4664 passed).

## Runtime Proof Required After Merge
No runtime evidence required. CI checks pass.

## What This PR Does Not Prove
This PR does not prove strategy profitability. It only hardens telemetry persistence and test isolation.

## Human Approval
Requires PR review and manual merge.
