# EDGE-NEXT-04 Strategy Baseline Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative, offline strategy-vs-baseline comparison layer that classifies each strategy/setup as outperforming, matching, underperforming, or insufficient sample, and feeds that signal into readiness and ranking without weakening safety gates.

**Architecture:** Build one pure baseline-comparison helper that consumes existing candidate outcome / expectancy summaries and produces deterministic verdicts plus a small penalty/boost. Wire the verdict into strategy-regime expectancy outputs first, then into expectancy gate / edge ranking as a narrow additive signal. Keep fallback, stale-feed, Phase 2, and executable safety as higher-priority gates that always dominate.

**Tech Stack:** Python, pytest, existing outcome truth / expectancy / ranking modules, JSON/Markdown report outputs used by the repo.

---

### Task 1: Define baseline comparison contract

**Files:**
- Create: `core/expectancy/strategy_baseline_comparison.py`
- Modify: `core/expectancy/__init__.py`
- Test: `tests/test_strategy_baseline_comparison.py`

- [ ] **Step 1: Write the failing test**

```python
def test_outperforms_same_regime_baseline():
    report = compare_strategy_to_baselines(strategy_rows, baseline_rows)
    assert report.baseline_verdict == "OUTPERFORMS"
    assert report.expectancy_delta_vs_baseline > 0
    assert report.penalty_or_boost > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_strategy_baseline_comparison.py -vv`
Expected: FAIL with module/function not found.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class StrategyBaselineComparison:
    strategy_id: str
    setup_fingerprint: str
    regime: str
    sample_count: int
    strategy_after_cost_expectancy: float | None
    baseline_after_cost_expectancy: float | None
    expectancy_delta_vs_baseline: float | None
    baseline_verdict: str
    confidence_tier: str
    penalty_or_boost: float
    reason: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_strategy_baseline_comparison.py -vv`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/expectancy/strategy_baseline_comparison.py core/expectancy/__init__.py tests/test_strategy_baseline_comparison.py
git commit -m "edge: add strategy baseline comparison contract"
```

### Task 2: Aggregate baselines from existing expectancy rows

**Files:**
- Modify: `core/expectancy/strategy_regime_expectancy.py`
- Test: `tests/test_strategy_regime_expectancy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_same_regime_baseline_is_used_when_available():
    report = build_strategy_regime_expectancy_report(rows)
    comparison = report.strategy_baseline_comparisons[0]
    assert comparison.baseline_verdict == "OUTPERFORMS"
    assert comparison.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_strategy_regime_expectancy.py -vv`
Expected: FAIL because `strategy_baseline_comparisons` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def compare_strategy_to_baselines(strategy_rows, *, same_regime_rows, same_direction_rows, eligible_rows):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_strategy_regime_expectancy.py -vv`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/expectancy/strategy_regime_expectancy.py tests/test_strategy_regime_expectancy.py
git commit -m "edge: compare strategy expectancy against baselines"
```

### Task 3: Feed baseline verdict into readiness and ranking conservatively

**Files:**
- Modify: `core/expectancy/expectancy_gate.py`
- Modify: `core/expectancy/edge_ranking.py`
- Modify: `core/no_trade_engine.py`
- Test: `tests/test_expectancy_gate.py`
- Test: `tests/test_edge_ranking.py`
- Test: `tests/test_no_trade_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_underperforming_strategy_gets_penalized_but_not_hard_blocked_if_other_candidates_are_healthy():
    ...
    assert below_baseline.penalty_or_boost < 0
    assert healthy_candidate.can_still_be_executable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_expectancy_gate.py tests/test_edge_ranking.py tests/test_no_trade_engine.py -vv`
Expected: FAIL because baseline signals are not wired yet.

- [ ] **Step 3: Write minimal implementation**

```python
if comparison.baseline_verdict == "OUTPERFORMS":
    boost = min(comparison.penalty_or_boost, 0.08)
elif comparison.baseline_verdict == "UNDERPERFORMS":
    penalty = min(abs(comparison.penalty_or_boost), 0.12)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_expectancy_gate.py tests/test_edge_ranking.py tests/test_no_trade_engine.py -vv`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/expectancy/expectancy_gate.py core/expectancy/edge_ranking.py core/no_trade_engine.py tests/test_expectancy_gate.py tests/test_edge_ranking.py tests/test_no_trade_engine.py
git commit -m "edge: wire baseline comparison into readiness and ranking"
```

### Task 4: Add traceable evidence and run repo gates

**Files:**
- Add: `docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md`
- Modify: `tests/test_strategy_baseline_comparison.py` if any deterministic edge case is missing

- [ ] **Step 1: Write the evidence doc**

Include the required traceability fields and sections: `Agent Work Contract`, `Scope Guard`, `Grill Me Review`, `Hermes Review`, `GSD Review`, `QA / Safety Review`, `Acceptance Proof`, `Runtime Proof Required After Merge`, `What This PR Does Not Prove`, `Human Approval`.

- [ ] **Step 2: Run the repository gates**

Run:
`python scripts/validate_agent_review_evidence.py --base-ref origin/main`
`git diff --check`
`PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_04_changed_paths.txt`

Expected: all pass with no blocks.

- [ ] **Step 3: Final regression run**

Run:
`PYTHONPATH=. pytest -q tests/test_strategy_baseline_comparison.py tests/test_strategy_regime_expectancy.py tests/test_expectancy_gate.py tests/test_edge_ranking.py tests/test_candidate_scoring.py tests/test_candidate_pool_quality.py tests/test_top_opportunity_selector.py tests/test_no_trade_engine.py tests/test_review_queue_fallback_execution.py tests/test_engine_phase2_adapter.py -vv`

Expected: all green.

- [ ] **Step 4: Commit and publish**

```bash
git add docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md
git commit -m "edge: add strategy baseline comparison evidence"
git push -u origin ram/edge-next-04-strategy-baseline-comparison
```

---

## Design coverage check
- Strategy/setup identity: covered via `setup_fingerprint`, `strategy_id`, `regime`, and `direction` keys in the comparison contract.
- Historical outcome / expectancy storage: covered by reusing `strategy_regime_expectancy` outputs.
- Baseline comparison existence: this PR adds it.
- Feasible baselines: same-regime, same-direction, and naive eligible-candidate baseline are all represented in the helper contract.
- Insufficient samples: handled conservatively with `INSUFFICIENT_SAMPLE` and no boost.
- Files to change: listed above per task.
- Tests to add: listed above per task.
