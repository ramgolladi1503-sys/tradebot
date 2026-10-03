# PR 959 — Objective Weekly Bearish Structure V1

mode: RESEARCH
candidate_id: OBJECTIVE_WEEKLY_BEARISH_STRUCTURE_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Add a read-only, deterministic market-structure detector that translates a discretionary Elliott-style bearish-top thesis into falsifiable weekly rules without changing strategy or execution authority.
timestamp: 2026-10-03T22:55:00+05:30
is_order_action: false
broker_api_called: false
source: research/objective-weekly-structure-v1

## Agent Work Contract

Implement only an additive, research-only detector and its tests/documentation. Do not modify live feeds, strategy selection, ranking, risk, order construction, broker integration, paper/live modes, or existing truth-engine semantics.

Owned paths:
- `core/objective_weekly_structure.py`
- `tests/test_objective_weekly_structure.py`
- `docs/research/objective_weekly_bearish_structure_v1.md`
- `docs/agent_reviews/pr959_objective_weekly_bearish_structure_v1.md`

## Scope Guard

The diff is additive. The detector accepts completed weekly OHLC mappings and returns a read-only descriptive assessment. It has no imports from broker, execution, ranking, strategy, or risk paths and exposes no order action.

## Grill Me Review

1. Does this prove Elliott Wave theory?
   - No. Elliott labels are deliberately excluded.
2. Can the detector signal on the final high before confirmation?
   - No. Pivots require right-side confirmation and the bearish state requires a later completed weekly close below the last reaction low.
3. Can oscillator divergence manufacture a signal?
   - No. Divergence is optional recorded evidence; the structural contraction and downside break are mandatory.
4. Does a visually similar 2026 chart certify an edge?
   - No. Historical repeated-event and out-of-sample testing remain required.
5. Can this code place a trade or alter live behavior?
   - No.

## QA / Safety Review

Focused tests cover:
- fail-closed insufficient history;
- no signal before the breakdown week;
- deterministic confirmation on the first valid breakdown week;
- rejection when the downside break is absent;
- rejection of expanding rather than contracting swings;
- explicit read-only/no-broker metadata.

## Acceptance Boundary

This PR may become an implementation-valid research feature only. It must not be described as:
- evidence of a multi-year NIFTY bear market;
- a certified predictive edge;
- a live regime authority;
- a trading strategy.

The next admissible step is offline historical evaluation against fixed 1/4/12/26/52-week NIFTY outcomes, matched controls, placebo shifts, simpler bear-regime baselines, and existing bearish option-buying outcomes without retuning strategy rules.

## What This PR Does Not Prove

- predictive value;
- incremental value over a moving-average/downtrend regime;
- option profitability;
- execution viability;
- current-market direction.

## Human Approval

Keep the PR draft and unmerged. Human review is required before integration.
