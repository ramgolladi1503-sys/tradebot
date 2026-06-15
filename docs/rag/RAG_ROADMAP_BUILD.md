# RAG Roadmap Build Model

This document outlines the build and validation model for the production-grade RAG roadmap.

## One-Branch Roadmap Model
The entire RAG roadmap will be developed on a single dedicated branch (`rag/roadmap-prod-rag-v2`). This ensures that all intermediate steps and automated safety mechanisms are preserved and tested in sequence before being merged into the main codebase.

## Checkpoint Commit Model
Development is divided into discrete checkpoints. Each checkpoint focuses on a specific set of features or automation guardrails.
1. Implement the specific scope for the checkpoint.
2. Ensure no out-of-scope paths are modified.
3. Commit with a specific message format (e.g., `chore(rag-00): add roadmap automation guardrails`).
4. Validate the checkpoint using automated scripts.

## Forbidden Files
The following paths must not be modified under any circumstances during this roadmap to prevent interference with live trading and core systems:
- `.env`
- `.env.*`
- `runtime/secrets/`
- `secrets/`
- `config/broker*`
- `configs/live*`
- `core/execution*`
- `core/order*`
- `core/risk*`
- `core/orchestrator*`
- `core/engine_phase2_adapter.py`
- `core/feed_execution_truth.py`
- `strategies/`
- `core/strategies/`
- `core/backtest_elite.py`
- `core/backtesting/`
- `core/vectorized_signals.py`
- `scripts/run_wfa_intraday.py`

## Allowed Files
For this initial checkpoint, modifications are strictly limited to:
- `scripts/rag_*`
- `docs/rag/`

## Required Validation After Each Checkpoint
After every checkpoint, you must run the following sequence to validate the changes:
```bash
git diff --check
bash scripts/rag_guard_diff.sh origin/main
bash scripts/rag_roadmap_runner.sh --check
```

## Final Validation Before Opening PR to Main
Before opening the final pull request to merge the branch into `main`, a full validation must be performed to ensure tests and evaluations pass:
```bash
bash scripts/rag_roadmap_runner.sh --full
```