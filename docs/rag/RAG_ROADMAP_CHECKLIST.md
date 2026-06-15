# RAG Roadmap Checklist

This checklist must be followed to ensure the safety and progression of the RAG roadmap.

## 1. One-Branch Roadmap Model
- [ ] All RAG work is contained on the single `rag/roadmap-prod-rag-v2` branch.
- [ ] No direct commits to `main` for RAG features until the final PR.

## 2. Checkpoint Commit Model
- [ ] Work is divided into specific checkpoints.
- [ ] Each checkpoint only modifies the files relevant to its scope.
- [ ] Commits are clearly labeled with the checkpoint ID (e.g., `chore(rag-00): ...`).

## 3. Forbidden Files Validation
- [ ] Ensure the following critical paths are completely untouched to avoid live system impact:
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

## 4. Allowed Files Validation
- [ ] Ensure modifications are strictly within allowed paths (for checkpoint 00, this is `scripts/rag_*` and `docs/rag/`).

## 5. Post-Checkpoint Validation
After each checkpoint, verify success by running:
- [ ] `git diff --check`
- [ ] `bash scripts/rag_guard_diff.sh origin/main`
- [ ] `bash scripts/rag_roadmap_runner.sh --check`

## 6. Pre-PR Validation
Before creating a PR to merge into `main`:
- [ ] Run `bash scripts/rag_roadmap_runner.sh --full`
- [ ] Confirm all tests and evals pass.
- [ ] Verify no forbidden paths have been altered during the entire branch lifecycle.