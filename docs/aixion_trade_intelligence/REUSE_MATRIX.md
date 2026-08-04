# Aixion Trade Intelligence — Phase -1 Reuse Matrix

This matrix prevents the sidecar from replacing existing TradeBot authority.

| Capability | Existing TradeBot owner | Authority | Sidecar action | New implementation required? |
|---|---|---|---|---|
| Feed truth | `core/feed_truth_contract.py` and execution-truth integration | Production feed eligibility | Adapt emitted snapshot into canonical event | No |
| Execution truth | `core/execution_truth.py` | Production execution eligibility | Record decisions and blockers | No |
| Candidate lineage | `core/candidate_lineage_ledger.py` | Candidate-stage evidence | Translate existing rows to canonical lineage events | No |
| TradeBuilder mapping | `strategies/trade_builder.py` | Contract selection and candidate construction | Observe inputs/outputs only | No |
| Option quote evidence | Existing market-data and option-chain payloads | Source-specific | Persist exact identity, time, bid/ask and quality | Adapter only |
| Slippage | `core/slippage_model.py`, `core/slippage_guard.py` | Existing model and guard | Preserve model output; calibrate later against fills | No replacement |
| Fill realism | `core/fill_model.py`, `core/fill_realism.py`, `core/fill_quality.py` | Existing simulation/evaluation | Join to actual fill evidence | No replacement |
| Confidence calibration | `core/analytics/confidence_calibration.py` | Existing calibration analytics | Consume reports after causal outcomes exist | No replacement |
| Strategy decay | `core/strategy_decay.py`, `core/strategy_tracker.py` | Existing degradation logic | Record state and audit evidence | No replacement |
| Walk-forward analysis | `scripts/run_wfa.py` and option replay WFA | Research validation | Reuse in cold-plane certification | No replacement |
| Runtime health | Existing orchestrator/feed/runtime telemetry | Operational truth | Adapt state changes and incidents | Adapter only |
| CAS | Research PR evidence | Research-only | Port observer only after accumulated evidence | Deferred |
| Market Event Graph | Existing research/live-shadow stack | Research and shadow evidence | Consume events and outcomes; no duplicate implementation in V1 | Deferred |

## Current V1 authority boundary

The new package owns only:

```text
canonical intelligence event validation
append-only local evidence publishing
deterministic event-log replay
offline session manifest
candidate-to-outcome completeness analytics
read-only report artifacts
```

It does not own strategy logic, ranking, broker execution, risk permission, feed permission, or strategy promotion.
