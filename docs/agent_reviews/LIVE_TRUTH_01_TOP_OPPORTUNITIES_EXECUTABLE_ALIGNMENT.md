# LIVE-TRUTH-01 Top Opportunities Executable Truth Alignment Agent Review

mode: REVIEW
candidate_id: live_truth_01_top_opportunities_executable_alignment
decision: review_ready
reason: executable_alignment_and_trace_completeness_tests_docs
timestamp: 2026-05-27T09:50:00Z
source: live_truth_01_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

LIVE-TRUTH-01 adds read-only executable truth alignment evidence between ranked opportunities and top-opportunities artifacts.

It also validates that top executable runtime evidence contains full trade-quality trace fields.

## Scope

In scope:

- Detect ranked/top-opportunities executable-count mismatch.
- Detect top-reportable executable mismatch.
- Detect missing top executable in top-opportunities evidence.
- Validate `TB_TOP_EXECUTABLE_CANDIDATE` trace fields.
- Validate `runtime_candidate_handoff_latest.json` fields.
- Preserve read-only and non-action metadata.

Out of scope:

- Order placement.
- Forced execution.
- Runtime state mutation.
- Broker/adaptor integration.
- Dashboard changes.
- Artifact writer changes.
- Latest non-empty preservation; that belongs to LIVE-TRUTH-02.

## Required Evidence Fields

Every top executable trace and runtime candidate handoff must include:

- `trade_id`
- `appeared_at`
- `symbol`
- `strike`
- `option_type`
- `strategy_family`
- `entry`
- `execution_entry`
- `stop_loss`
- `target`
- `risk_reward`
- `rank_score`
- `source_quote_age`
- `bid`
- `ask`
- `ltp`

## Grill Me Review

Question: Can this PR place an order?

Answer: No.

Question: Can this PR force an executable candidate into top opportunities?

Answer: No. It only reports whether the evidence is aligned.

Question: Can this PR mutate runtime state?

Answer: No.

Question: Can this PR hide missing trace fields?

Answer: No. Missing trace fields become explicit mismatch reasons.

Question: Does this PR fix latest artifact overwrite behavior?

Answer: No. That belongs to LIVE-TRUTH-02.

## Hermes Review

Boundary check:

- No adapter import.
- No broker call.
- No runtime writer mutation.
- No dashboard change.
- No execution behavior.
- Non-action metadata remains explicit.

Verdict: scoped as evidence-only alignment and trace completeness.

## GSD Review

Files changed are narrow:

- `core/live_truth_top_opportunities_alignment.py`
- `tests/test_live_truth_01_top_opportunities_alignment.py`
- `docs/LIVE_TRUTH_01_TOP_OPPORTUNITIES_EXECUTABLE_ALIGNMENT.md`
- `docs/agent_reviews/LIVE_TRUTH_01_TOP_OPPORTUNITIES_EXECUTABLE_ALIGNMENT.md`
- `docs/EDGE_TODO.md`

## QA / safety review

Tests cover:

- executable-count mismatch
- top-reportable mismatch
- top executable missing from top-opportunities evidence
- aligned state
- count derivation from lists
- incomplete top executable trace
- incomplete runtime candidate handoff
- no trace requirement when executable truth is absent
- invalid input blocking
- JSON serialization
- non-action metadata

## Acceptance Proof

Command:

`PYTHONPATH=. python -m pytest tests/test_live_truth_01_top_opportunities_alignment.py`

Expected result:

- focused LIVE-TRUTH-01 tests pass
- mismatches are explicit
- trace gaps are explicit
- no order behavior is introduced

## Human Approval

Human review is required before any later PR wires this evidence into runtime artifact writers or dashboards.

## Next Action

After this PR merges green, continue with LIVE-TRUTH-02 — Latest Artifact Non-Empty Preservation.
