# Agent Review — EDGE-98 Historical Dataset Contract

## Agent Work Contract

- issue: #319 / EDGE-98 Historical Dataset Contract
- parent: #318
- mode: CONTRACT_ONLY
- scope: strict historical market dataset validation for future backtest/replay snapshots
- base: `8dd26e43e3a947ae991ea9a62ca3d1f91c631d87`
- branch: `feature/edge-98-historical-dataset-contract`
- candidate_id: EDGE-98-HISTORICAL-DATASET-CONTRACT
- decision: HISTORICAL_DATASET_CONTRACT_ONLY
- reason: STRICT_REPLAY_SAFE_DATASET_BOUNDARY
- timestamp: 2026-05-28T08:20:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: core/backtest_dataset_contract.py

## Scope Guard

EDGE-98 adds a deterministic validation boundary for historical market snapshots.

Included files:

- core/backtest_dataset_contract.py
- tests/test_edge_98_backtest_dataset_contract.py
- docs/EDGE_98_HISTORICAL_DATASET_CONTRACT.md
- docs/agent_reviews/EDGE_98_HISTORICAL_DATASET_CONTRACT.md
- docs/EDGE_TODO.md

Excluded areas:

- replay runner
- strategy execution
- ranking
- paper journal writes
- external adapters
- execution engine
- runtime loop
- dashboard/UI
- unrelated cleanup

## Grill Me Review

Question: Does this PR run replay?

Answer: No. It only validates and normalizes historical snapshot data.

Question: Can missing option fields slip through?

Answer: No. Required option fields raise `HistoricalDatasetContractError`.

Question: Can stale quote data remain executable?

Answer: No. Stale or missing quote timestamps are classified as non-executable with explicit reasons.

Question: Can bad price data pass?

Answer: No. Negative bid, ask, ltp, volume, and oi are rejected. `ask < bid` is rejected.

## Hermes Review

The module exports a small stable contract:

- `build_historical_market_snapshot`
- `HistoricalMarketSnapshot`
- `HistoricalInstrumentQuote`
- `HistoricalDatasetContractError`
- schema/source constants
- non-executable reason constants

The payload is JSON-friendly, deterministic, read-only, and explicit about external/action boundaries.

## GSD Review

Purpose: add the first strict dataset contract for the backtest/walk-forward roadmap.

Scope: pure validation and normalization of historical snapshots.

Files changed:

- core/backtest_dataset_contract.py
- tests/test_edge_98_backtest_dataset_contract.py
- docs/EDGE_98_HISTORICAL_DATASET_CONTRACT.md
- docs/agent_reviews/EDGE_98_HISTORICAL_DATASET_CONTRACT.md
- docs/EDGE_TODO.md

Test evidence: focused pytest coverage is included and targets the exact contract edge cases introduced by EDGE-98.

Validation evidence: tests cover valid snapshots, invalid timestamps, missing fields, negative values, invalid bid/ask, missing expiry, stale quote timestamps, and multiple instruments.

Risk control: future replay layers must consume the `executable` flag and non-executable reasons instead of bypassing this contract.

Next sequencing control: do not start the next roadmap issue until #319 is merged green and the next issue is explicitly confirmed.

## QA / Safety Review

Focused tests cover:

- deterministic JSON-serializable valid snapshot
- required snapshot timestamp
- invalid snapshot timestamp
- missing option expiry
- negative bid/ask/ltp/volume/OI
- ask below bid
- missing quote timestamp classified non-executable
- stale quote timestamp classified non-executable
- deterministic ordering across multiple instruments

Verification command executed locally:

```bash
pytest tests/test_edge_98_backtest_dataset_contract.py -q
```

Verification result:

```text
8 passed
```

CI evidence observed before this evidence-file correction:

- Repo Forensics PR Gate: success
- Agent Review Evidence Gate: success
- Portfolio CI: success
- CodeQL Advanced: success
- tests: success
- Code Excellence Gates: blocked only on this evidence file with `weak_evidence_pattern_found`

## Acceptance Proof

The contract allows executable historical option data only when:

- snapshot timestamp is valid and timezone-aware
- instrument identity is valid
- required option fields exist
- bid, ask, ltp, volume, and oi are non-negative
- ask is greater than or equal to bid
- quote timestamp exists and is not stale

Missing or stale quote timestamps are retained for auditability but made non-executable.

## Runtime Boundary Review

EDGE-98 is contract validation only. Runtime paths remain unchanged.

Unchanged paths:

- replay runner
- strategy execution
- ranking
- paper journal writes
- external adapters
- execution engine
- runtime loop
- Streamlit dashboard

## High-Risk Path Review

High-risk paths intentionally unchanged:

- external adapters
- execution engine
- runtime loop
- Streamlit dashboard
- strategy generation logic
- ranking logic
- paper journal logic
