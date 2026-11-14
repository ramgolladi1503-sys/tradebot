# Edge Factory Truth Layer V1 — Adversarial Review Contract

This review contract accompanies `TRADEBOT_RESEARCH_TRUTH_LAYER_V1`.

It is intentionally hostile to research drift. The reviewer should try to prove that a campaign can bypass the outcome-blind discovery boundary or the downstream truth layer.

## Required attacks

A review is incomplete until it attempts all of the following:

1. Expose forward-return, validation, confirmation, Sharpe, win-rate or P&L results to the discovery phase.
2. Generate a new mechanism after any outcome has been seen.
3. Replace a failed mechanism with a near-neighbor inspired by the failure.
4. Expand the frozen catalog after testing starts.
5. Reorder the frozen catalog to prioritize a promising near-miss.
6. Change the catalog hash without a governed pre-outcome freeze event.
7. Exceed the campaign family/hypothesis/horizon/global-cell budget.
8. Start V2/V3 and reset global trial/search pressure to zero.
9. Hide failed, blocked or superseded experiments from the global ledger.
10. Turn the target of three survivors into a requirement to keep searching until three appear.
11. Weaken an acceptance threshold because too few strategies survived.
12. Add RSI/MACD/VWAP/ADX/other filters after a failed primary hypothesis.
13. Invert a failed signal and treat it as a fresh uncounted strategy.
14. Read protected confirmation before `CANDIDATE_FREEZE`.
15. Reuse a failed confirmation block for repair/retest.
16. Feed a raw-correlation p-value to Holm/BH while claiming an incremental-baseline hypothesis.
17. Define incremental lift from incomparable metrics.
18. Hard-code a negative-control pass.
19. Hard-code +5m/+10m delay retention.
20. Hard-code fold/session concentration.
21. Shift sparse snapshots and call it an actual +5m delay.
22. Allow outcome/future columns into a feature matrix.
23. Report the base SHA as executed code provenance after research files changed.
24. Invent historical bid/ask, depth, slippage, OI, IV or Greeks.
25. Promote historical option-candle research as execution-grade evidence.
26. Repackage a closed family under a new name without declaring overlap.
27. Modify V1 semantics inside an ordinary strategy PR rather than a governed truth-layer version change.

Any successful bypass is a blocking finding.

## Expected invariants

Authority:

`research/governance/edge_factory_truth_layer_v1.json`

Pinned by:

`tests/research/test_edge_factory_truth_layer_v1.py`

Expected raw SHA-256:

```text
c2a4751a34b76b6113003c32c54e6900f34c6c6be9fd20a0b6821290023fc693
```

Key expected properties:

```text
fixed strategy catalog in truth layer = false
mechanism discovery allowed = true
outcome-blind discovery required = true
catalog freeze before outcome access = true
catalog SHA required = true
default max mechanism families = 12
default max primary hypotheses/family = 4
default max horizons/hypothesis = 2
default max primary cells/campaign = 96
post-outcome catalog expansion = false
global search pressure persists across campaigns = true
historical default = OHLCV_ONLY
live authority = false
```

A hash change is not automatically invalid, but must occur only in a dedicated governance/version-change review with explicit rationale. Ordinary strategy/research PRs must not update both contract and pinned hash merely to make tests pass.

## Outcome-blind boundary proof

A campaign must provide evidence that the discovery agent/process could not read:

```text
forward outcomes
validation results
locked confirmation
strategy P&L
Sharpe/win rate
best threshold/horizon searches
near-miss failure diagnostics used to invent replacement families
```

Before evaluation begins, require a materialized and hashed mechanism catalog containing each mechanism rationale, required data authority, falsifiable claim, primary hypotheses/horizons, baseline and prior-family overlap.

The recorded catalog SHA must remain unchanged through evaluation.

If the boundary cannot be proven:

```text
BLOCKED_OUTCOME_BLIND_DISCOVERY_NOT_PROVEN
```

## Review verdicts

Use one:

```text
PASS_NO_TRUTH_LAYER_DRIFT
BLOCKED_CONTRACT_HASH_MISMATCH
BLOCKED_DISCOVERY_OUTCOME_LEAK
BLOCKED_CATALOG_FREEZE_BYPASS
BLOCKED_CAMPAIGN_BUDGET_DRIFT
BLOCKED_GLOBAL_SEARCH_ACCOUNTING_RESET
BLOCKED_GATE_WEAKENING
BLOCKED_HOLDOUT_BYPASS
BLOCKED_STATISTICAL_HARNESS_BYPASS
BLOCKED_PROVENANCE_BYPASS
BLOCKED_EXECUTION_AUTHORITY_DRIFT
BLOCKED_UNGOVERNED_V1_MUTATION
```

## Relationship to strategy performance

Strategy profitability is irrelevant to this review.

A profitable candidate does not justify weakening the truth layer.

A campaign with zero survivors does not justify catalog expansion after outcomes.

The legitimate next step after catalog exhaustion may be a new campaign with a new **blind discovery phase**, but the global experiment ledger and selection pressure continue from prior campaigns.

Therefore the following is forbidden:

```text
V2 = erase V1 search history and try again as if fresh
```

The correct model is:

```text
V2 = new blind catalog + cumulative search accounting
```

## Safety

This PR is governance/research only.

```text
read_only_market_research=true
is_order_action=false
broker_api_called=false
broker_write_authority=false
order_authority=false
allowed_for_live_execution=false
```
