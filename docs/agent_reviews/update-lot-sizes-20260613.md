# Update Instrument Lot Sizes — Agent Review Evidence

mode: PAPER
candidate_id: pr-update-lot-sizes
decision: update-lot-sizes-for-index-options
reason: Update the hardcoded lot sizes for NIFTY, BANKNIFTY, and SENSEX to match recent exchange requirements.
timestamp: 2026-06-13T12:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/update-lot-sizes-20260613.md

## Agent Work Contract

This PR updates the `LOT_SIZE` dictionary in `config/config.py` to correctly reflect the updated market lot sizes for index options.

## Scope Guard

In scope:
- `config/config.py` (LOT_SIZE dictionary only)

Out of scope:
- Broker execution adapters
- Execution logic
- Risk allocation algorithms

## Grill Me Review

Question: Does this change execution logic?
Answer: No. It simply changes the configuration values that existing logic uses to calculate size and exposure.

Question: Have we accounted for changes in portfolio risk?
Answer: Yes. The new lot sizes will automatically be passed into the existing risk management and portfolio allocation methods (e.g., `_exposure_for_trade`), ensuring total capital at risk is respected even with the different unit counts.

## Hermes Review

Coordination notes:
- This PR strictly modifies `config/config.py`. 
- Ensures no hidden logic changes are introduced to `core/risk_engine.py` or `core/orchestrator.py`.

## GSD Review

Governance / Scope / Discipline result:
- Single theme: Update config lot sizes.
- No unrelated files touched.
- No complex re-architecture.

## QA / Safety Review

Safety findings:
- `is_order_action: false`
- `broker_api_called: false`

## High-Risk Path Review

This PR touches `config/config.py`, which is a high-risk path.
- The changes are strictly confined to the `LOT_SIZE` dictionary keys corresponding to NIFTY, BANKNIFTY, and SENSEX. No other configuration keys or behaviors are modified.

## Acceptance Proof

Local focused tests passed:
- `pytest tests/ -k config` (Config parsing tests remain intact).

## Runtime Proof Required After Merge

Recommended post-merge verification:
- Ensure the next paper/live soak logs show the updated quantity values when reporting lot sizing logic, and that `qty_total_units` scales correctly based on the new dictionary values.

## What This PR Does Not Prove

This PR does not prove:
- Correct broker order fulfillment of the new lot size in the LIVE market.

## Human Approval

Human approval required before merge.
Recommended approval condition:
- Agent Review Evidence Gate passes.
- PR diff confirms only the three lines in `config/config.py` were modified.
