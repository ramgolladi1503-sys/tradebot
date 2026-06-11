# Eight-Year Backtesting Phase 1 and 1.5 - Agent Review Evidence

mode: PAPER
decision: historical-data-readiness-foundation
timestamp: 2026-06-11T13:25:00Z
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: docs/agent_reviews/qa-eight-year-backtest-strategy-edge.md

## Agent Work Contract

This PR adds Phase 1 and Phase 1.5 of the eight-year backtesting program.

Requested paths:

- `core/backtesting/*`
- `scripts/backtest_data_diagnostics.py`
- `scripts/import_historical_data.py`
- `configs/backtest_8y.example.json`
- `configs/backtest_data_schema_examples/*`
- `docs/backtesting/*`
- `tests/backtesting/*`

Allowed paths:

- historical data cataloging
- schema validation
- readiness scoring
- feasibility classification
- import/diagnostics CLI
- sample schemas
- docs and tests

Forbidden paths:

- broker adapters
- live execution gates
- risk gates
- strategy generators
- Phase 2 replay/backtest execution
- Phase 3 ranking/confidence/sizing remediation

## Scope Guard

In scope:

- read-only historical data inspection
- local file schema validation
- offline readiness classification
- diagnostics and import dry-run reporting
- regression tests that block false readiness unlocks

Out of scope:

- order placement, modification, cancellation, or exits
- broker API calls
- LIVE mode changes
- feed truth changes
- quote truth changes
- risk truth changes
- runtime trading behavior changes

## Grill Me Review

Question: Could this PR fake eight-year intraday readiness without real option history?

Answer: The final implementation blocks that path. `TRUE_OPTIONS_INTRADAY` requires valid intraday options plus long-span underlying or futures support.

Question: Could runtime replay be mislabeled as real options support?

Answer: The review fix removes runtime replay from `HYBRID`. Replay can support only `LIVE_CAPTURE_REPLAY`.

Question: Could this PR silently widen live or broker behavior?

Answer: No. The changed files are isolated to backtesting cataloging, docs, config, and tests. No broker or live execution modules were modified.

## Hermes Review

Architecture choice:

- separate discovery/cataloging from any future replay engine
- keep Phase 1 fail-closed and evidence-first
- classify feasible modes without inventing unavailable data
- use explicit config roots and explicit schema contracts

Trade-off:

- this PR prefers conservative under-classification over accidental readiness claims

## GSD Review

Execution discipline:

- implemented only Phase 1 and 1.5
- review findings were fixed in a follow-up commit before merge
- no unrelated feed-soak changes were mixed into this branch
- generated `.runtime` artifacts were not committed

## QA / Safety Review

Safety checks:

- no broker APIs imported in Phase 1 files
- no live execution gate files changed
- no risk gate files changed
- no strategy generator files changed
- no fake historical data added
- no runtime fallback mislabeled as real options coverage

Key regression coverage:

- option EOD cannot unlock true intraday mode
- underlying-only cannot unlock real options mode
- short underlying span cannot unlock full true intraday readiness
- runtime replay cannot unlock hybrid mode
- duplicate runtime replay roots do not double count evidence

## Acceptance Proof

Local verification completed:

```bash
python -m pytest tests/backtesting -q
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
python scripts/import_historical_data.py --config configs/backtest_8y.example.json --dry-run
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Observed result:

- backtesting tests passed
- diagnostics returned `NEED_USER_HISTORICAL_DATA`
- import dry-run completed without broker calls
- agent review evidence gate passed locally after adding this file

## Runtime Proof Required After Merge

Runtime proof is not required after merge for this PR because it does not change live execution or broker paths.

Required post-merge evidence remains:

- operator-supplied local historical datasets
- rerun of diagnostics against real imported data
- honest readiness verdict before any Phase 2 work starts

## What This PR Does Not Prove

This PR does not prove:

- true eight-year intraday options history exists locally
- Phase 2 replay correctness
- Phase 2 simulator correctness
- Phase 3 ranking or sizing quality
- strategy profitability
- live execution safety beyond the unchanged existing gates

## Human Approval

Human approval required before merge.

Recommended approval conditions:

- Agent Review Evidence Gate passes
- Code Excellence Gates pass on current HEAD
- no `.runtime` artifacts are committed
- final verdict remains honest about missing real historical data
