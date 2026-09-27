# Hermes contract — PR #936 research-pipeline Monte Carlo resampling

```yaml
source_agent: hermes
action: DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
title: Correct repeated deterministic pseudo-resamples in research pipeline
scope: Offline statistics helper only; deterministic bootstrap with replacement over caller-supplied synthetic PnL
requested_paths:
  - core/research_pipeline.py
  - tests/test_research_pipeline_monte_carlo.py
  - docs/research/PR936_MONTE_CARLO_RESAMPLING_CONTRACT.md
allowed_paths:
  - core/research_pipeline.py
  - tests/test_research_pipeline_monte_carlo.py
  - docs/research/PR936_MONTE_CARLO_RESAMPLING_CONTRACT.md
forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - strategies/**
  - requirements.txt
  - pyproject.toml
  - protected outcome files, ledgers, market data, runtime artifacts
expected_tests:
  - pytest -q tests/test_research_pipeline_monte_carlo.py
acceptance_proof:
  - Bootstrap samples are drawn with replacement and have input sample length
  - A fixed seed is reproducible and changing the seed can change distribution summaries
  - Nonconstant synthetic input produces nondegenerate bootstrap sum quantiles
  - Inputs with fewer than 10 rows preserve existing omission behavior
  - Empty/malformed strategy input is handled explicitly without outcome access
  - The method does not reorder or mutate the supplied trade records
  - No research data is loaded; tests invoke only the private statistic with inline synthetic records
  - The exact input and full-pipeline output format stay unchanged
```

## GSD execution boundary

Change only `_monte_carlo`; do not alter `_load_trades`, orchestration, walk-forward, risk state, or report schema. Use a local `random.Random(seed)` so global random state is untouched. Draw `len(pnl)` observations with replacement for each replication, sort aggregate sums, and retain the current percentile/rounding fields. The default seed is fixed for reproducibility; make `n` and `seed` explicit keyword-compatible parameters. This is IID bootstrap of individual trade outcomes only; it does not handle serial dependence, overlapping labels, regime structure, or multiple testing and must not be presented as inferential certification.

```text
read_only=true for tests
append=false
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```
