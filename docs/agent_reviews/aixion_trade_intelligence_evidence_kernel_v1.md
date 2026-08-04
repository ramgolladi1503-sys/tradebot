# Agent Review — Aixion Trade Intelligence Evidence Kernel V1

mode: PAPER_AND_OFFLINE_EVIDENCE
candidate_id: aixion_trade_intelligence_evidence_kernel_v1
decision: OFFLINE_CERTIFIED_LIVE_CANARY_REQUIRED
reason: Adds a read-only canonical evidence, deterministic replay, candidate-lineage, causal outcome, and reporting lane without changing trading authority.
timestamp: 2026-08-04T18:30:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
strategy_logic_changed: false
execution_logic_changed: false
risk_logic_changed: false

## Objective

Create the smallest complete evidence kernel needed to observe TradeBot candidates, attach exact market evidence, calculate causal outcomes, and fail closed when data or contracts are incomplete.

## Changed scope

Allowed:

- `aixion_trade_intelligence/`
- `scripts/generate_offline_fixture.py`
- `scripts/run_tradebot_intelligence_observer.py`
- `scripts/import_upstox_parquet.py`
- `scripts/finalize_trade_intelligence_session.py`
- focused `tests/test_aixion_*`
- docs, research summary, and focused workflow.

Forbidden:

- strategies;
- TradeBuilder;
- ranking;
- risk engine;
- broker and order routers;
- orchestrator;
- production execution configuration;
- dashboard opportunity selection.

## Correctness boundaries

- No missing bid or ask is inferred.
- No generic strategy horizon is created by production code.
- Every outcome horizon comes from an immutable candidate outcome contract.
- No future quote is treated as available before its actual availability timestamp.
- Incomplete declared outcomes reject certification.
- Invalid outcome contracts reject with a failed gate rather than crashing finalization.
- Finalization is idempotent.
- The quote importer derives exact candidate instruments and refuses accidental all-instrument ingestion.

## Offline proof

```text
45 focused tests passed
fixture pipeline: PIPELINE_OFFLINE_CERTIFIED
real August 3 corpus: PIPELINE_OFFLINE_CERTIFIED
real event count: 18,014
real look-ahead violations: 0
real outcome classifications: UNDERLYING_WRONG x2
strategy edge certified: false
```

## What this does not prove

- no live callback or filesystem proof;
- no strategy profitability;
- no calibrated queue position or fill probability;
- no capacity;
- no holdout edge;
- no model promotion;
- no CAS directional edge;
- no autonomous agent or LLM trading authority.

## Merge boundary

Keep the PR draft until focused CI and repository checks complete. Even after CI, a human must review the diff and the separate live canary result before any merge decision.
