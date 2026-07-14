# EDGE-87 Strategy Family Kill/Keep Report Agent Review

mode: REVIEW
candidate_id: edge_87_strategy_family_kill_keep_report
decision: review_ready
reason: strategy_family_report_tests_docs
timestamp: 2026-05-27T09:25:00Z
source: edge87_strategy_family_report_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

EDGE-87 derives read-only strategy-family evidence from EDGE-86 net slippage/cost truth.

This PR reports family-level `KEEP`, `WATCH`, and `KILL` recommendations. It does not mutate lifecycle state and does not promote, suspend, or retire strategies.

## Scope

In scope:

- Consume valid EDGE-86 slippage/cost truth reports.
- Use net-cost buckets only.
- Group strategy versions into families.
- Support explicit family metadata.
- Derive family-level net evidence.
- Classify family evidence as `KEEP`, `WATCH`, or `KILL`.
- Preserve read-only and non-action metadata.

Out of scope:

- Strategy lifecycle state mutation.
- Strategy promotion.
- Strategy suspension.
- Dashboard views.
- Runtime loop wiring.
- Adapter interaction.
- Paper journal mutation.
- Paper event append behavior.

## Scope Guard

- EDGE-86 net cost truth remains the upstream source.
- Invalid cost truth blocks before classification.
- Empty buckets block before classification.
- Recommendations are evidence only.
- No dashboard behavior change.
- No runtime behavior change.
- No lifecycle state change.

## Grill Me Review

Question: Can this PR promote a strategy?

Answer: No. It only emits evidence recommendations.

Question: Can this PR suspend or retire a strategy?

Answer: No. Lifecycle mutation belongs to later governance PRs.

Question: Can this PR use gross PnL as final truth?

Answer: No. It consumes EDGE-86 net-cost buckets.

Question: Can invalid net-cost evidence produce family recommendations?

Answer: No. Invalid cost truth blocks the report.

Question: Can this PR change runtime behavior?

Answer: No.

## Hermes Review

Boundary check:

- No runtime loop wiring added.
- No dashboard controls added.
- No adapter imports added.
- No ranking behavior modified.
- Non-action metadata remains false.

Verdict: scoped and read-only reporting only.

## GSD Review

Files changed are narrow:

- `core/strategy_family_kill_keep_report.py`
- `tests/test_edge_87_strategy_family_kill_keep_report.py`
- `docs/EDGE_87_STRATEGY_FAMILY_KILL_KEEP_REPORT.md`
- `docs/agent_reviews/EDGE_87_STRATEGY_FAMILY_KILL_KEEP_REPORT.md`
- `docs/EDGE_TODO.md`

## QA / safety review

Tests cover:

- KEEP classification
- KILL classification
- WATCH classification for insufficient sample
- WATCH classification for weak win rate
- grouping multiple strategy versions into one family
- explicit family metadata
- invalid cost truth report blocking
- empty bucket blocking
- JSON serialization
- non-action metadata

## Runtime Proof Required After Merge

After merge, EDGE-87 proves only that strategy-family evidence can be derived from net paper cost truth.

Any runtime report, dashboard display, or lifecycle mutation must be added in a separate scoped PR with tests and human review.

## Acceptance Proof

Command:

`PYTHONPATH=. python -m pytest tests/test_edge_87_strategy_family_kill_keep_report.py`

Expected result:

- focused EDGE-87 tests pass
- invalid inputs fail closed
- valid net-cost buckets derive deterministic family recommendations
- non-action metadata remains false

## What This PR Does Not Prove

This PR does not prove:

- strategy lifecycle readiness
- strategy promotion readiness
- strategy suspension readiness
- dashboard correctness
- runtime integration correctness
- pilot readiness

## Human Approval

Human review is required before any later PR wires family recommendations into runtime reports, dashboards, or lifecycle governance decisions.

## Next Action

After EDGE-87 merges green, continue with LIVE-TRUTH-01 — Top Opportunities Executable Truth Alignment.


## QA / Safety Review

N/A

## High-Risk Path Review

N/A
