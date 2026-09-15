# Edge Factory Truth Layer V1 — Adversarial Review Contract

This review contract accompanies `TRADEBOT_RESEARCH_TRUTH_LAYER_V1`.

It is intentionally hostile to research drift. A reviewer should try to prove that a proposed campaign can bypass the truth layer.

## Required attacks

A review is incomplete until it attempts all of the following:

1. Add a ninth strategy family after failures.
2. Increase the per-family or global primary-test budget after seeing outcomes.
3. Turn the target of three survivors into a requirement to keep searching until three appear.
4. Weaken an acceptance threshold because too few strategies survived.
5. Add RSI/MACD/VWAP/ADX/other filters after a failed primary hypothesis.
6. Invert a failed signal and treat the inversion as a fresh uncounted strategy.
7. Read protected confirmation before `CANDIDATE_FREEZE`.
8. Reuse a failed confirmation block for repair/retest.
9. Feed a raw-correlation p-value to Holm/BH while claiming an incremental-baseline hypothesis.
10. Define incremental lift from incomparable metrics.
11. Hard-code a negative-control pass.
12. Hard-code +5m/+10m delay retention.
13. Hard-code fold/session concentration.
14. Shift sparse snapshots and call it an actual +5m delay.
15. Allow outcome/future columns into a feature matrix.
16. Report the base SHA as executed code provenance after research files changed.
17. Invent historical bid/ask, depth, slippage, OI, IV, or Greeks.
18. Promote historical option-candle research as execution-grade evidence.
19. Reopen a closed family without a new governed research version.
20. Modify V1 semantics inside an ordinary strategy PR rather than creating a new governance version.

Any successful bypass is a blocking finding.

## Expected invariants

The authoritative machine contract is:

`research/governance/edge_factory_truth_layer_v1.json`

The V1 raw-file SHA-256 is pinned by:

`tests/research/test_edge_factory_truth_layer_v1.py`

Expected digest:

```text
96688b8d2c0d9235bc8dfde1bd7d4fbdb434dd83d446436961d8b84c1dba5771
```

A hash change is not automatically invalid, but it must occur only in a dedicated governance/version-change review with explicit rationale. Ordinary research/strategy PRs should not update both the contract and its pinned hash simply to make tests green.

## Review verdicts

Use one:

```text
PASS_NO_TRUTH_LAYER_DRIFT
BLOCKED_CONTRACT_HASH_MISMATCH
BLOCKED_FAMILY_BUDGET_DRIFT
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

A campaign with zero survivors does not justify expanding the search universe.

The correct outcome of a fully exhausted bounded campaign may be:

```text
0 independent survivors
```

That remains a successful research process if the truth layer was preserved.

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
