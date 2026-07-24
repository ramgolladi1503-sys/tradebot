# All Strategy Source Census v1

candidate_id: all_strategy_source_census_v1
decision: PROVISIONAL_CENSUS_WITH_DECLARED_GAPS
mode: OFFLINE_CENSUS_AND_READINESS_MATRIX
reason: Build a provisional all-strategy source census from the already materialized VWAP source bundle, deduplicate by content and semantic identity, and emit a strategy-specific execution-readiness matrix without running replay, WFA, holdout, broker, or fixed-economics tournament paths.
timestamp: 2026-07-24T12:57:42+05:30
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
source: local bundle /Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/vwap_source_search/20260724-123741-41381
source_head: `b4ccd69857ce0d594ef6e9c98646fa9f968b3c8c`
research_only: true

## Scope

This work adds a local census layer, compact repo summaries, and tests. It does not touch broker, live orders, live feeds, credentials, risk gates, dashboard code, production thresholds, or production registration.

## Verified Input Bundle

- `run_status.json`: `status=COMPLETE`
- `source_search_summary.json`: `conclusion=SIGNAL_SOURCE_RESOLVED`
- `source_search_manifest.json`: present
- `candidate_inventory.jsonl`: present
- `root_inventory.json`: present
- `git_search_manifest.json`: present
- `source_search_manifest.json.sha256`: present

Observed bundle counts:

- Raw candidates: 6119
- Raw accepted: 1055
- Raw unresolved: 24
- Physical candidate files: 6119
- Exact content blobs: 2910
- Dataset partitions: 1054
- Logical dataset families: 8
- Dataset versions: 986
- Canonical dataset versions: 0
- Usable-with-limitations versions: 25
- Unresolved dataset versions: 961
- Canonical signal ledgers: 1
- Truncation: `true`
- Timed out roots: 0

The census module rechecked the bundle and the compact evidence was deterministic across two independent output directories.

## What Changed

- Added `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census.py`
- Added `research/option_e2e_recertification_v4/all_strategy_source_census_v1/__init__.py`
- Added compact repo summaries and sidecars under `research/option_e2e_recertification_v4/all_strategy_source_census_v1/`
- Added `tests/research/option_e2e/test_all_strategy_source_census_v1.py`

## What Was Proven

- Input bundle integrity checks pass for the verified bundle.
- Exact duplicate groups are collapsed by `sha256 + classification + size`.
- Minimal five-column signal ledgers do not become canonical by shape alone.
- NIFTY-named OHLCV files are not treated as canonical unless they satisfy the census rules.
- Strategy inventory and readiness are emitted separately from dataset and ledger registries.
- Deterministic rerun hashes matched for the full external outputs and the compact outputs.
- The earlier illustrative tournament contract was removed.

## What Remains True

- The source bundle is resolved, but truncated.
- The census is not an exhaustive closure proof for every possible root tail.
- The census remains provisional because truncation and unresolved candidate tails still exist.
- This does not execute options replay, WFA, holdout, or P&L.
- This does not certify live readiness.

## Tests

- `PYTHONPATH=. pytest -q tests/research/option_e2e/test_all_strategy_source_census_v1.py`
- `PYTHONPATH=. pytest -q tests/research/option_e2e/test_all_strategy_source_census_v1.py tests/research/option_e2e/test_signal_ledgers_v4_10.py tests/research/option_e2e/test_signal_ledgers_v4_10_2.py`
- `AGENT_REVIEW_BASE_REF=origin/main PYTHONPATH=. python scripts/validate_agent_review_evidence.py`

## Output Paths

External evidence:

- `/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133422_family_model`
- `/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/all_strategy_source_census_v1/20260724-133424_family_model_rerun`

Compact committed evidence:

- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/schema.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_family_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_version_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/signal_ledger_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/execution_readiness_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/external_evidence_manifest.json`
