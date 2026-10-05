# TradeBot Adversarial QA Playbook

## Mission

QA is not a confirmation step. QA attempts to prove the change unsafe, incorrect, incomplete, nondeterministic, or misleading.

QA must never silently patch defects. Defects return to Development.

## Mandatory test classes

Every applicable change should be attacked with:

1. functional tests
2. negative tests
3. boundary tests
4. regression tests
5. contract/schema tests
6. stale/missing/corrupt-data tests
7. deterministic/repeatability tests
8. state-transition tests
9. restart/recovery tests
10. concurrency/order tests where applicable

## Trading-system attack catalogue

For feed/replay/Sentinel/data work, explicitly consider:

- future-data leakage
- final-candle leakage
- out-of-order ticks
- duplicate events
- stale quote/OI/depth
- delayed availability
- missing strikes
- missing constituents
- clock skew
- incorrect DTE
- expiry/session mismatch
- market holiday/session boundaries
- NaN/Inf
- empty arrays
- schema mismatch
- artifact/hash mismatch
- corrupt Parquet/JSON/NPZ
- partial WebSocket disconnect
- restart mid-session
- partial replay
- invalid probability vector
- contradictory state
- stale model
- spread explosion
- zero-volume contract
- race condition
- fail-open fallback
- forbidden order/action path

## Defect lifecycle

Each defect must record:

- defect ID
- severity
- originating story
- reproduction steps
- expected behavior
- actual behavior
- evidence
- developer fix reference
- QA retest evidence
- regression/adversarial follow-up result

## Exit rule

QA passes only when:

- acceptance criteria are met;
- reported defects are fixed and retested;
- changed areas survive a new adversarial pass;
- no unresolved blocking/severe defects remain;
- no risk or feed gate was weakened to make tests pass.
