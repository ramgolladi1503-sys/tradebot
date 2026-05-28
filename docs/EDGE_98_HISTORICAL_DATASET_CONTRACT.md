# EDGE-98 — Historical Dataset Contract

## Purpose

EDGE-98 adds a strict historical market dataset contract for future backtest and replay snapshots.

This is a validation boundary only. It does not run replay, execute strategies, rank candidates, write paper journal events, call external systems, or wire dashboard behavior.

## Scope

This PR adds:

- `core/backtest_dataset_contract.py`
- `tests/test_edge_98_backtest_dataset_contract.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Snapshot contract

A valid snapshot must include:

- `snapshot_timestamp`
- `market_session`
- `source_metadata`
- one or more instruments

The snapshot output is deterministic and JSON-serializable. Instruments are sorted by identity so repeated validation of the same payload emits the same ordered payload.

## Option instrument contract

Option instruments require:

- `expiry`
- `strike`
- `option_type`
- `bid`
- `ask`
- `ltp`
- `volume`
- `oi`
- `quote_timestamp`

Missing required option fields fail closed with `HistoricalDatasetContractError`.

## Price and market-data validation

The contract rejects:

- invalid snapshot timestamps
- invalid quote timestamps
- missing required option fields
- negative `bid`
- negative `ask`
- negative `ltp`
- negative `volume`
- negative `oi`
- `ask < bid`
- unsupported instrument types
- unsupported option types

## Executability classification

Missing or stale quote timestamps are not silently allowed as executable data.

The instrument remains in the snapshot for auditability, but is classified as non-executable with a reason:

- `MISSING_QUOTE_TIMESTAMP`
- `STALE_QUOTE_TIMESTAMP`
- `QUOTE_TIMESTAMP_AFTER_SNAPSHOT`

This is deliberate. Future replay/backtest layers can inspect bad data without accidentally treating it as tradable.

## Output payload

The snapshot payload includes:

- schema version
- source marker
- snapshot timestamp
- instrument counts
- executable/non-executable counts
- normalized instruments
- read-only safety fields

Payloads preserve explicit non-action boundaries:

- `read_only=True`
- `append=False`
- action marker false
- external-call marker false
- live-action marker false

## Boundaries

EDGE-98 does not:

- create a replay runner
- execute strategies
- rank candidates
- write paper journal events
- call external systems
- create live actions
- wire runtime loops
- wire dashboard/UI
- modify existing strategy contracts

## Acceptance proof

Run:

```bash
pytest tests/test_edge_98_backtest_dataset_contract.py -q
```

Recommended regression:

```bash
pytest tests/test_edge_98_backtest_dataset_contract.py tests/test_final_edge_readiness_report.py -q
```

Focused coverage includes:

- valid snapshots
- deterministic JSON serialization
- missing/invalid snapshot timestamp
- missing required option fields
- negative bid/ask/ltp/volume/OI
- invalid bid/ask spread
- missing quote timestamp classified non-executable
- stale quote timestamp classified non-executable
- multiple instruments per snapshot
