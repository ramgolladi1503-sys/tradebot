# Block Unknown FeedTruth Top Executable Emission

## Agent Work Contract
Scope: evidence-only runtime normalization so `TB_TOP_EXECUTABLE_CANDIDATE` cannot be emitted as reportable executable when FeedTruth is `UNKNOWN`, `entries_allowed=false`, or `quotes_trusted=false`. No broker/order, strategy, ranking, Phase2, UI, websocket reconnect, or threshold changes.

## Scope Guard
This PR only tightens executable-truth normalization and audit coverage. It does not change trade selection logic, score math, or live execution behavior.

## Grill Me Review
The dangerous failure mode is a candidate that still looks executable in inner fields while the canonical feed truth is blocked or unknown. That must remain blocked and non-reportable.

## Hermes Review
The execution-truth path now consumes feed freshness evidence conservatively so stale or unknown feed truth cannot masquerade as executable opportunity evidence.

## GSD Review
Implementation is localized to `core/runtime_execution_truth.py`, `core/feed_truth_audit.py`, and the corresponding regression tests.

## QA / Safety Review
Validated with focused runtime truth and audit tests plus repo gates. No broker calls, no live orders, no strategy/ranking/Phase2 changes, no UI changes.

## High-Risk Path Review
- `core/runtime_execution_truth.py`: tightened feed-truth gating so stale/unknown feed truth cannot normalize to executable.
- `core/feed_truth_audit.py`: audit context now recognizes `feed_fresh` as a fail-closed signal.
- `tests/test_kite_depth_restart.py`: test-only isolation reset expanded to keep websocket lifecycle tests deterministic.
- `tests/test_runtime_execution_truth_evidence.py` and `tests/test_feed_truth_audit.py`: regressions cover stale feed snapshot, unknown feed truth, and blocked executable leakage.

## Evidence
- mode: CHECK
- candidate_id: unknown_feedtruth_top_executable_block
- decision: block_top_executable_emission
- reason: feed_truth_unknown_or_not_fresh_must_fail_closed
- timestamp: 2026-06-05T01:44:41+05:30
- is_order_action: false
- broker_api_called: false
- source: core.runtime_execution_truth

## Acceptance Proof
- `reportable_executable` is false when feed truth is stale, unknown, or entries are not allowed.
- `TB_TOP_EXECUTABLE_CANDIDATE` is suppressed when feed truth is not safe to report.
- runtime feed freshness (`feed_fresh=false`) is treated as blocked in execution-truth evidence.
- the audit harness rejects reportable executable output when runtime feed snapshot is not fresh.
- `is_order_action: false`
- `broker_api_called: false`

## Runtime Proof Required After Merge
Re-run the focused feed/runtime/audit suites and confirm they stay green across repeated runs. Verify blocked feed truth never produces executable-looking top candidate evidence.

## What This PR Does Not Prove
It does not change live feed recovery, option subscription logic, strategy generation, ranking math, Phase2 selection, or broker execution.

## Human Approval
Reviewed for merge only after CI and agent-review evidence gates pass.
