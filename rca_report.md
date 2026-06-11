# RCA: Strategy Edge and Candidate Pipeline

## 1. Branch/base inspected
```bash
git branch --show-current
git diff --stat
```
Inspected the main branch, verifying no active diffs prior to the audit.

## 2. Full module map
1. **Feed & Market Context**: `market_context.py` provides the snapshot. `core/feed_execution_truth.py` establishes boolean permission (`feed_truth_allows_live_selection`) to allow execution.
2. **Strategy/Decision Layer**: `trade_builder.py` takes market data and evaluates against logic to build `Trade` objects representing candidates.
3. **Filtering/Scoring**: Candidates generated go through internal filtering, including probability gating, spread/slippage calculation, and target/stop creation via ATR multiples.
4. **Phase 2 Pipeline**: `core/engine_phase2_adapter.py` receives candidates, inspects `feed_runtime_latest.json` for `feed_ok` validity, enforces hard drops (`_phase2_contract_hard_drop`), and calculates spread thresholds.
5. **Orchestrator Decision Flow**: `core/orchestrator.py` receives the final candidate list, compares them with risk limits, and creates the final signal execution object.

## 3. File coverage table
| Module | Responsibility | Weakness/Finding | Test Coverage |
|---|---|---|---|
| `strategies/trade_builder.py` | Generate execution candidates and apply strategy gates | Weak signal edge, generic scoring, fake candidates possible | Unknown / Fragmented |
| `core/orchestrator.py` | Central nervous system for trading | Confusing wiring between risk limits and signal creation | Extensive |
| `core/engine_phase2_adapter.py` | Adapts candidates to new pipeline | Misreading `feed_ok` exceptions block trades | Lacking specific edge tests |
| `core/feed_execution_truth.py` | Converts health truth to execution boolean | Clean boolean check | Covered |

## 4. Strategy/orchestration/ranking/candidate weakness table
| Finding Type | File Path | Function/Class Name | Current Behavior | Why it is weak | Proposed Modification |
|---|---|---|---|---|---|
| **A. Strategy logic weakness** | `strategies/trade_builder.py` | `TradeBuilder.build` | Uses basic static probability thresholds (`SCALP_MIN_PROBA`, 0.58) and static ATR multipliers to define candidates. | Represents an arbitrary rule engine with no discernible edge. Generates trades based on thresholds, not statistical backtest proof. | Define a specific entry setup with statistical backing. Remove generic threshold generation. |
| **B. Orchestration wiring weakness** | `core/engine_phase2_adapter.py` | `build_candidates_phase2` | Reads `feed_runtime_latest.json` but falls back to `feed_ok = False` if any exception occurs. | If `feed_ok` logic inside json fails or json is temporarily unreadable, it fails closed silently blocking the pipeline. | Ensure JSON parse explicitly checks for empty payloads or log parsing errors accurately. |
| **C. Candidate pool generation weakness** | `strategies/trade_builder.py` | `_reject_record` | Logs rejected candidates into `rejected_candidates.jsonl` using a subset of fields. | Does not capture the full reason the strategy failed it (just `reason: missing_contract_fields`, etc), making it impossible to audit *why* the edge didn't trigger. | Enrich rejection logging with full market context and specific gate failure. |
| **H. Liquidity/spread/slippage weakness** | `core/engine_phase2_adapter.py` | `_phase2_contract_hard_drop` | Blocks based on strict configuration but does not evaluate post-score liquidity. | Liquidity is a static boolean rather than a sliding scale impacting the `confidence` score. | Incorporate spread and slippage cost directly into candidate ranking score. |
| **M. Backtest/replay validation gap** | `strategies/trade_builder.py` | `Trade` generation | Emits candidates purely on live snapshot data. | Cannot prove that `confidence > 0.58` leads to positive expectancy because it lacks a historical simulation harness. | Build a replay mechanism that runs identical `build` code on tick datasets. |

## 5. Dominant root cause preventing trading edge
The strategy module (`trade_builder.py`) is an arbitrary rule engine rather than an edge-based system. It uses generic `confidence` scores (often set statically or derived from unknown ML components) and applies static ATR multiples (`SCALP_STOP_ATR = 0.3`, `SCALP_TARGET_ATR = 0.6`) without market regime context. It generates candidates to hit thresholds, not because a statistically proven market inefficiency exists.

## 6. Secondary contributors
- `engine_phase2_adapter.py` acts as a blunt filter that throws away candidates due to silent feed-read errors, breaking the pipeline unexpectedly and masking true strategy performance.
- Rejection logging (`_reject_record`) truncates data, preventing offline analysis of missed opportunities.

## 7. Evidence gaps
- **No-trade Evidence**: `rejected_candidates.jsonl` is written but lacks full feed health context and orchestrator state, making it hard to tell if the candidate was bad or if the system was just broken.
- **Phase-2 Rejection**: `engine_phase2_adapter.py` drops candidates but does not record detailed metrics of the drop into a centralized dashboard file.

## 8. Test coverage gaps
- Lack of end-to-end replay validation ensuring that `confidence` scoring correctly predicts positive expectation.
- Tests mock the strategy builder but do not validate its internal mathematical correctness or slippage estimation.

## 9. Proposed elite architecture improvements
1. **Edge-First Strategy**: Replace static `TradeBuilder` logic with a setup-driven model (e.g., specific breakout pattern, momentum fade) with historical expectancy.
2. **Contextual Scoring**: Incorporate regime, spread, and slippage into the candidate ranking score rather than using them as blunt boolean filters.
3. **Unified Evidence Log**: Emit every generated, rejected, and executed candidate to a single SQLite/JSONL ledger containing full market context and exact rejection reasons.

## 10. Patch plan split into small commits
- **Commit 1**: Add robust rejection evidence logging to `TradeBuilder` and `engine_phase2_adapter.py`.
- **Commit 2**: Fix `engine_phase2_adapter.py` to properly log and parse `feed_ok` instead of silently failing.
- **Commit 3**: Remove static `confidence` thresholds from `TradeBuilder` and replace with setup-specific logic.
- **Commit 4**: Wire regime and spread data directly into candidate ranking equations.
- **Commit 5**: Implement a replay validation harness to prove the edge.

## 11. Backtest/replay validation plan
1. Dump 30 days of raw ticks into SQLite.
2. Run `trade_builder.py` over the ticks simulating `now()`.
3. Capture all generated `Trade` objects.
4. Calculate MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion) for every candidate.
5. Prove that top-ranked candidates have positive R-multiple expectancy.

## 12. Metrics to prove edge improvement
- Candidate pool size by market regime.
- Rejection reason distribution.
- MAE/MFE after candidate creation.
- Average R multiple (Target hit vs Stop Hit).
- Expectancy (Win Rate * Avg Win - Loss Rate * Avg Loss).
- No-trade correctness rate.

## 13. Risks and anti-overfitting safeguards
- Avoid adding more indicators or static thresholds to `trade_builder.py`.
- Ensure the backtest validation relies on out-of-sample data, not the exact days used to tune the ATR multipliers.

## 14. Final recommendation
**Collect more data and test first.** The repository currently lacks a proven, measurable edge. It is a robust orchestration pipeline executing arbitrary rules. Implement Commit 1 (Evidence Logging) and Commit 5 (Replay Harness) immediately to establish baseline expectancy before modifying strategy code.
