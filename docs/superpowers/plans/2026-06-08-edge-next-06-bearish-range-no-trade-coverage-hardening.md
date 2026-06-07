# EDGE-NEXT-06 — Bearish / Range / No-Trade Coverage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the system preserves valid bearish, range, and chop/no-trade candidates correctly, then degrade readiness when the pool is structurally one-sided or regime-incompatible.

**Architecture:** Keep strategy generation unchanged unless inspection proves a hard representation bug where valid bearish/range candidates cannot be represented at all. Harden the preservation, exposure normalization, pool-quality, no-trade, and ranking plumbing so existing bearish/PE and range/mean-reversion candidates survive, compete fairly, and still fail closed when the pool is one-sided or regime-mismatched. Safety gates remain dominant over all readiness and ranking signals.

**Tech Stack:** Python, pytest, existing tradebot candidate classification / pool-quality / no-trade / ranking helpers.

---

## Current Weakness Found

- Bearish and range semantics already exist in the system, but they are mostly represented indirectly through candidate direction, strategy family, and regime tags rather than a single explicit generation layer.
- The risky part is not obvious absence of bearish/range candidates; it is that BUY-centric assumptions, pool concentration, and readiness plumbing can still make a one-sided pool look better than it is.
- Pool-quality and no-trade logic already know about direction family coverage, concentration, fallback contamination, and baseline weakness, but the bearish/range/chop failure modes are not yet pinned down by targeted regression tests.
- Candidate-level versus pool-level weakness needs to be split explicitly so a single mismatched candidate can be penalized without hard-failing a healthy mixed pool.

## Files to Modify or Create

### Files to modify
- `core/candidate_pool_quality.py` — strengthen directional/regime coverage signals and pool-quality penalties for one-sided bearish/range/chop pools.
- `core/candidate_exposure.py` or the smallest existing helper location that already normalizes direction/regime fields — add exposure normalization across direction, option type, signal direction, strategy family, movement type, and regime.
- `core/no_trade_engine.py` — degrade readiness or trigger no-trade when the whole pool is structurally one-sided, especially in bearish/range/chop contexts.
- `core/expectancy/edge_ranking.py` — apply a secondary penalty so regime-mismatched or direction-mismatched candidates do not outrank aligned candidates unfairly.
- `tests/test_candidate_pool_quality.py` — add direct pool coverage regressions for bearish, range, and directional-heavy chop pools.
- `tests/test_no_trade_engine.py` — add readiness/no-trade regressions for one-sided bearish/range/chop pools.
- `tests/test_edge_ranking.py` — add ranking regressions showing regime-compatible bearish/range candidates can outrank mismatched candidates.
- `tests/test_candidate_classifier.py` — add preservation regressions proving bearish/range candidates are not lost to BUY-only assumptions.
- `tests/test_candidate_normalizer.py` — add preservation regressions proving bearish/range candidates survive dedupe/normalization with their direction intact.

### Files to leave unchanged unless inspection proves a hard representation bug
- `strategies/trade_builder.py`
- `strategies/pro_layer/pro_strategy_engine.py`

## Task 1: Prove the current direction and pool-coverage behavior

**Files:**
- Create or modify: `core/candidate_exposure.py` if the repo does not already have a suitable helper for normalizing directional exposure.
- Modify: `tests/test_candidate_classifier.py`
- Modify: `tests/test_candidate_normalizer.py`
- Modify: `tests/test_candidate_pool_quality.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_bearish_candidate_is_preserved_through_classification():
    candidate = _candidate(direction="BUY_PUT", movement_type="FAILED_BREAKOUT_TRAP")
    classified = classify_candidate(candidate)
    assert classified.bucket in {"EXECUTABLE_CANDIDATE", "NEAR_EXECUTABLE_CANDIDATE", "ADVISORY_CANDIDATE"}
    assert classified.direction == "BUY_PUT"


def test_range_candidate_is_preserved_through_normalization():
    candidate = _candidate(direction="BUY_CALL", movement_type="VWAP_MEAN_REVERSION")
    normalized = normalize_candidates([candidate])
    assert normalized.candidates[0].direction == "BUY_CALL"
    assert normalized.candidates[0].movement_type == "VWAP_MEAN_REVERSION"


def test_pool_quality_counts_bullish_bearish_and_range_coverage():
    pool = analyze_candidate_pool([
        _row(direction="BUY_CALL", strategy_family="breakout"),
        _row(direction="BUY_PUT", strategy_family="mean_reversion"),
        _row(direction="BUY_CALL", strategy_family="mean_reversion", movement_type="VWAP_MEAN_REVERSION"),
    ])
    assert pool.bullish_count == 1
    assert pool.bearish_count == 1
    assert pool.range_count == 1
```

The new exposure helper should normalize:
- `direction`
- `option_type`
- `signal_direction`
- `strategy_family`
- `movement_type`
- `regime`

Unknown exposure defaults conservative and counts as `UNKNOWN` rather than forcing bullish or bearish.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=. pytest -q tests/test_candidate_classifier.py tests/test_candidate_normalizer.py tests/test_candidate_pool_quality.py -vv`

Expected: fail until the preservation and coverage assertions exist.

- [ ] **Step 3: Implement the minimal preservation / coverage fixes**

```python
def is_bearish_direction(direction: str | None) -> bool:
    return normalize_direction(direction) in BEARISH_DIRECTIONS


def is_range_candidate(candidate: object) -> bool:
    regime = normalize_regime(getattr(candidate, "regime", None))
    family = normalize_family(getattr(candidate, "strategy_family", None))
    return regime in {"RANGE", "SIDEWAYS", "LOW_VOL"} or family in {"mean_reversion", "vwap_mean_reversion"}
```

Use the existing direction/regime/family fields rather than inventing new candidate types.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `PYTHONPATH=. pytest -q tests/test_candidate_classifier.py tests/test_candidate_normalizer.py tests/test_candidate_pool_quality.py -vv`

Expected: PASS.

## Task 2: Make readiness fail closed for one-sided bearish/range/chop pools

**Files:**
- Modify: `core/candidate_pool_quality.py`
- Modify: `core/no_trade_engine.py`
- Modify: `tests/test_candidate_pool_quality.py`
- Modify: `tests/test_no_trade_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_bearish_regime_with_bullish_only_pool_degrades_readiness():
    pool = analyze_candidate_pool([
        _row(direction="BUY_CALL", strategy_family="breakout", regime="BEARISH"),
        _row(direction="BUY_CALL", strategy_family="breakout", regime="BEARISH"),
    ])
    assessment = assess_no_trade(_context(), _regime(primary="BEARISH"), candidates=[_candidate("BUY_CALL"), _candidate("BUY_CALL")])
    assert assessment.no_trade_reason in {"NO_TRADE_POOL_CONCENTRATION", "NO_TRADE_BASELINE_WEAKNESS", "NO_TRADE_INCONCLUSIVE_REGIME"}
    assert assessment.readiness_state in {"WEAK", "NO_TRADE"}


def test_range_regime_without_range_candidate_degrades_readiness():
    pool = analyze_candidate_pool([
        _row(direction="BUY_CALL", strategy_family="breakout", regime="RANGE"),
    ])
    assessment = assess_no_trade(_context(), _regime(primary="RANGE", RANGE=0.7), candidates=[_candidate("BUY_CALL")])
    assert assessment.readiness_state in {"WEAK", "NO_TRADE"}
```

CHOP/noise logic must not treat a thin directional pool as healthy coverage. It should consider directional concentration, range/advisory coverage, total candidate count, and weak setup quality. If the pool is directional-heavy or weak in chop, the gate should favor no-trade rather than readiness.

Mixed-pool tests must prove:
- bearish pool with both `BUY_PUT` and `BUY_CALL` candidates should not fail closed
- `BUY_CALL` should still be penalized when compared to a regime-aligned `BUY_PUT` candidate
- range pool with mean-reversion + breakout candidates should not fail closed
- breakout should rank lower when comparable

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=. pytest -q tests/test_candidate_pool_quality.py tests/test_no_trade_engine.py -vv`

Expected: fail until the structural coverage checks exist.

- [ ] **Step 3: Implement the minimal readiness degradation**

```python
def pool_has_directional_coverage(pool: CandidatePoolQualityReport, regime: str | None) -> bool:
    regime_name = normalize_regime(regime)
    if regime_name == "BEARISH":
        return pool.bearish_count > 0
    if regime_name == "RANGE":
        return pool.range_count > 0
    if regime_name == "CHOP":
        return (
            pool.total_count >= 3
            and pool.directional_concentration < 0.65
            and pool.range_count > 0
            and pool.quality_score > 0.35
        )
    return True
```

Use this only to degrade readiness / favor no-trade when the pool is structurally one-sided. Do not hard-block a single mismatched candidate if the rest of the pool is healthy.

Candidate-level mismatch and pool-level weakness must stay separate:
- `candidate_regime_mismatch_penalty(candidate)` is ranking-only and must apply even when the pool contains a valid aligned candidate.
- `pool_regime_coverage_penalty(pool, regime)` is readiness/no-trade only and applies when the whole pool is structurally weak.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `PYTHONPATH=. pytest -q tests/test_candidate_pool_quality.py tests/test_no_trade_engine.py -vv`

Expected: PASS.

## Task 3: Penalize mismatched candidates in ranking without changing generation

**Files:**
- Modify: `core/expectancy/edge_ranking.py`
- Modify: `tests/test_edge_ranking.py`
- Modify: `tests/test_top_opportunity_selector.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_regime_compatible_bearish_candidate_beats_mismatched_bullish_candidate():
    bearish = _row(direction="BUY_PUT", strategy_family="mean_reversion", regime="BEARISH", expectancy_status="KEEP", expectancy_sample_count=60, expectancy_avg_cost_adjusted_r=0.20)
    bullish = _row(direction="BUY_CALL", strategy_family="breakout", regime="BEARISH", expectancy_status="KEEP", expectancy_sample_count=60, expectancy_avg_cost_adjusted_r=0.20)
    bearish_ranked = apply_edge_ranking(bearish)
    bullish_ranked = apply_edge_ranking(bullish)
    assert bearish_ranked["edge_rank_score"] > bullish_ranked["edge_rank_score"]
    assert bullish_ranked["edge_rank_score"] > 0.0


def test_range_candidate_beats_weak_breakout_in_range_regime():
    range_candidate = _row(direction="BUY_CALL", strategy_family="mean_reversion", regime="RANGE", expectancy_status="KEEP", expectancy_sample_count=60, expectancy_avg_cost_adjusted_r=0.15)
    breakout = _row(direction="BUY_CALL", strategy_family="breakout", regime="RANGE", expectancy_status="KEEP", expectancy_sample_count=60, expectancy_avg_cost_adjusted_r=0.15)
    range_ranked = apply_edge_ranking(range_candidate)
    breakout_ranked = apply_edge_ranking(breakout)
    assert range_ranked["edge_rank_score"] >= breakout_ranked["edge_rank_score"]
    assert breakout_ranked["edge_rank_score"] > 0.0
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `PYTHONPATH=. pytest -q tests/test_edge_ranking.py tests/test_top_opportunity_selector.py -vv`

Expected: fail until the penalty and coverage-aware ranking exists.

- [ ] **Step 3: Implement the minimal ranking penalty**

```python
def candidate_regime_mismatch_penalty(candidate: Candidate) -> float:
    penalty = 0.0
    if normalize_regime(candidate.regime) == "BEARISH" and candidate.directional_exposure == "BULLISH":
        penalty += 0.12
    if normalize_regime(candidate.regime) == "RANGE" and candidate.setup_family in {"breakout", "momentum", "trend"}:
        penalty += 0.12
    if normalize_regime(candidate.regime) in {"CHOP", "NOISE", "UNCLEAR"} and candidate.directional_exposure in {"BULLISH", "BEARISH"}:
        penalty += 0.08
    return min(penalty, 0.20)


def pool_regime_coverage_penalty(pool: CandidatePoolQualityReport, regime: str | None) -> float:
    penalty = 0.0
    regime_name = normalize_regime(regime)
    if regime_name == "BEARISH" and pool.bearish_count == 0:
        penalty += 0.20
    if regime_name == "RANGE" and pool.range_count == 0:
        penalty += 0.20
    if regime_name in {"CHOP", "NOISE", "UNCLEAR"} and (
        pool.directional_concentration > 0.65 or pool.total_count < 3 or pool.quality_score <= 0.35
    ):
        penalty += 0.20
    return min(penalty, 0.25)
```

Subtract `candidate_regime_mismatch_penalty(candidate)` from ranking only. Use `pool_regime_coverage_penalty(pool, regime)` only for readiness / no-trade. Never let either override fallback, stale-feed, non-executable, or Phase 2 safety outcomes.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `PYTHONPATH=. pytest -q tests/test_edge_ranking.py tests/test_top_opportunity_selector.py -vv`

Expected: PASS.

## Task 4: Prove safety dominance stays intact

**Files:**
- Modify: `tests/test_review_queue_fallback_execution.py`
- Modify: `tests/test_engine_phase2_adapter.py`
- Modify: `tests/test_option_spread_truth_gate.py`
- Modify: `tests/test_edge_79_strategy_conflict_consensus.py`

- [ ] **Step 1: Add/refresh regression assertions**

```python
def test_fallback_bearish_candidate_still_cannot_be_executable():
    row = _row(
        direction="BUY_PUT",
        strategy_family="mean_reversion",
        row_kind="recovered_fallback",
        candidate_class="fallback",
        candidate_origin="fallback_rest",
        quote_source="rest_fallback",
        trade_id="softrej_T-FALLBACK-BEARISH",
        fallback_used=True,
        expectancy_status="KEEP",
        expectancy_sample_count=60,
        expectancy_avg_cost_adjusted_r=0.20,
    )
    out = apply_edge_ranking(row)
    assert out["reportable_executable"] is False
    assert out["execution_allowed"] is False


def test_chop_directional_heavy_pool_still_prefers_no_trade():
    pool = analyze_candidate_pool([
        _row(direction="BUY_CALL", strategy_family="breakout", regime="CHOP"),
        _row(direction="BUY_CALL", strategy_family="breakout", regime="CHOP"),
    ])
    assert no_trade_assessment(pool).reason.startswith("NO_TRADE")
```

- [ ] **Step 2: Run the regression suite**

Run: `PYTHONPATH=. pytest -q tests/test_review_queue_fallback_execution.py tests/test_engine_phase2_adapter.py tests/test_option_spread_truth_gate.py tests/test_edge_79_strategy_conflict_consensus.py -vv`

Expected: PASS.

## Task 5: Validate and document the change

**Files:**
- Create: `docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md`

- [ ] **Step 1: Write the agent review evidence doc**

Document:
- the coverage weakness that was found
- the files changed
- the exact behavior changed
- the tests run
- what was intentionally not touched
- why this improves actual trading edge
- whether the PR changes generation, classification, ranking, or readiness

- [ ] **Step 2: Run repository safety gates**

Run:

```bash
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_06_changed_paths.txt
```

- [ ] **Step 3: Verify worktree and prepare PR**

Run:

```bash
git status --short
git rev-parse --abbrev-ref HEAD
```

Expected: clean worktree on a `ram/` feature branch before PR creation.

## Scope Guard

- Do not rewrite strategy generation.
- Do not add new strategies.
- Do not create fake bearish/range candidates.
- Do not loosen safety gates to inflate candidate counts.
- Do not touch broker/order/live behavior, dashboard/UI, or websocket/feed lifecycle.
- Prove strategy generation was not changed by reviewing the final diff before PR creation and ensuring no `strategies/trade_builder.py` or `strategies/pro_layer/pro_strategy_engine.py` changes were introduced unless a documented hard representation bug was found.
- If the inspection proves a hard representation bug, fix only the smallest representation gap needed to preserve valid bearish/range candidates.

## Acceptance Proof

- Bearish candidates survive classification/normalization and can rank fairly when regime supports them.
- Range/mean-reversion candidates survive classification/normalization and can rank fairly when regime supports them.
- One-sided bullish-only pools in bearish/range/chop conditions degrade readiness and can drive no-trade.
- Fallback/stale/non-executable/Phase 2/safety gates still dominate and remain fail-closed.
- Existing ranking/baseline/Top-N/fallback/no-trade regressions remain green.
