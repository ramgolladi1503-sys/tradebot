# Pro Strategy Layer Elite Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the pro strategy layer into a conservative, high-precision signal engine that emits fewer but materially better candidates, ranks them deterministically, and stays isolated from `main` until offline validation proves it is safe.

**Architecture:** Keep the pro layer separate from the legacy ensemble. Each signal family becomes a specialist detector with explicit confirmation and invalidation rules. Time-window logic becomes a booster, not a standalone signal. Ranking is deterministic and conservative, with conflict suppression, provenance preservation, and downstream candidate scoring that never inflates weak signals. Integration stays behind an explicit feature flag until the branch proves itself offline.

**Tech Stack:** Python, `pytest`, `core.decision_engine`, `core.execution_quality`, `config.config`, existing `strategies.pro_layer` modules.

---

## Files in Scope

- Modify: `strategies/pro_layer/pro_strategy_engine.py` - tighten signal gates, make time-window a booster-only concept, and suppress conflicting or low-quality signals more aggressively.
- Modify: `strategies/pro_layer/pro_decision_adapter.py` - apply conservative rank normalization, preserve provenance, and avoid tradability inflation.
- Create: `tests/strategies/test_pro_strategy_engine_elite.py` - precision-first signal tests and conflict suppression coverage.
- Create: `tests/strategies/test_pro_decision_adapter_elite.py` - adapter ranking and provenance tests.
- Create: `tests/strategies/test_pro_strategy_replay_elite.py` - deterministic offline replay checks.
- Modify: `config/config.py` - add a flag-gated integration seam only after offline gates pass.
- Create: `core/pro_strategy_pipeline.py` - flag-gated entrypoint for later integration; default-off.
- Modify: `core/orchestrator.py` - only call the pro pipeline when the new flag is enabled; no default behavior change.
- Create: `tests/test_pro_strategy_pipeline.py` - prove the integration seam is disabled by default.

## Task 1: Make the signal layer precision-first

**Files:**
- Modify: `strategies/pro_layer/pro_strategy_engine.py`
- Create: `tests/strategies/test_pro_strategy_engine_elite.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine


def test_time_window_never_emits_without_primary_confirmation():
    engine = ProStrategyEngine()
    market_data = {
        "regime": "TREND",
        "hour": 9,
        "minute": 35,
        "ltp_change_window": 0.9,
        "ltp": 100.0,
        "vwap": 100.0,
        "atr": 0.0,
        "vol_z": 0.0,
        "quote_age_sec": 1.0,
        "spread_pct": 0.008,
    }
    assert engine.run(market_data) == []


@pytest.mark.parametrize(
    "market_data",
    [
        {
            "regime": "TREND",
            "atr": 2.0,
            "ltp_change_window": 1.6,
            "vol_z": 2.2,
            "bid_qty": 900,
            "ask_qty": 100,
            "quote_age_sec": 12.0,
            "spread_pct": 0.038,
        },
        {
            "regime": "RANGE",
            "ltp": 112.0,
            "vwap": 100.0,
            "rsi": 0.25,
            "quote_age_sec": 1.0,
            "spread_pct": 0.009,
        },
    ],
)
def test_precision_rules_fail_closed_on_stale_or_weak_context(market_data):
    assert ProStrategyEngine().run(market_data) == []
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pytest -q tests/strategies/test_pro_strategy_engine_elite.py -q`
Expected: fail because the current engine still emits the time-window signal and still allows some weak-context signals through.

- [ ] **Step 3: Implement the stricter signal gates**

```python
def _is_fresh_enough(market_data: dict[str, Any], max_age_sec: float = 6.0) -> bool:
    age = _safe_float(market_data.get("quote_age_sec"), default=999.0)
    return age <= max_age_sec


class ProSignalAggregator:
    def aggregate(self, signals: Iterable[ProSignal]) -> list[ProSignal]:
        signals = list(signals or [])
        if not signals:
            return []

        primary = [s for s in signals if s.family != "time_window"]
        boosters = [s for s in signals if s.family == "time_window"]
        if not primary:
            return []

        call_strength = sum(s.score * s.confidence for s in primary if s.direction == "BUY_CALL")
        put_strength = sum(s.score * s.confidence for s in primary if s.direction == "BUY_PUT")
        if call_strength and put_strength:
            stronger = "BUY_CALL" if call_strength > put_strength else "BUY_PUT"
            weaker_strength = min(call_strength, put_strength)
            stronger_strength = max(call_strength, put_strength)
            conflict_ratio = weaker_strength / max(stronger_strength, 1e-6)
            if conflict_ratio >= 0.55:
                return []
            primary = [sig for sig in primary if sig.direction == stronger]

        if boosters:
            booster = max(boosters, key=lambda s: s.score * s.confidence)
            for sig in primary:
                if sig.direction == booster.direction:
                    sig.evidence = {**sig.evidence, "time_window_boost": round(booster.score * booster.confidence, 4)}

        kept = [sig for sig in primary if sig.score >= 0.60 and sig.confidence >= 0.55]
        return sorted(kept, key=lambda s: (s.score * s.confidence, s.confidence, s.score), reverse=True)
```

- [ ] **Step 4: Re-run the test and confirm it passes**

Run: `pytest -q tests/strategies/test_pro_strategy_engine_elite.py -q`
Expected: pass, with the engine emitting fewer signals and never returning the time-window signal by itself.

- [ ] **Step 5: Commit**

```bash
git add strategies/pro_layer/pro_strategy_engine.py tests/strategies/test_pro_strategy_engine_elite.py
git commit -m "feat: harden pro strategy signal gating"
```

## Task 2: Make ranking deterministic and conservative

**Files:**
- Modify: `strategies/pro_layer/pro_decision_adapter.py`
- Create: `tests/strategies/test_pro_decision_adapter_elite.py`

- [ ] **Step 1: Write the failing tests**

```python
from strategies.pro_layer.pro_decision_adapter import pro_signal_to_candidate
from strategies.pro_layer.pro_strategy_engine import ProSignal


def test_adapter_penalizes_stale_and_weak_quality():
    signal = ProSignal(
        name="vol_expansion",
        direction="BUY_CALL",
        score=0.92,
        confidence=0.90,
        reason="high-momentum confirmation",
        family="volatility_expansion",
        regime_tags=["TREND"],
        evidence={"move_atr": 1.9},
    )
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "123",
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "quote_age_sec": 14.0,
        "spread_pct": 0.032,
        "data_confidence": 0.38,
    }
    candidate = pro_signal_to_candidate(signal, market_data)
    assert candidate["tradable"] is False
    assert candidate["confidence_final"] < candidate["raw_edge_score"]
    assert candidate["rank_score"] < candidate["raw_edge_score"]


def test_adapter_preserves_signal_provenance():
    signal = ProSignal(
        name="liquidity_imbalance",
        direction="BUY_PUT",
        score=0.80,
        confidence=0.84,
        reason="depth imbalance",
        family="order_flow",
        regime_tags=["TREND"],
        evidence={"imbalance": -0.41},
    )
    candidate = pro_signal_to_candidate(signal, {"symbol": "BANKNIFTY", "instrument_id": "456"})
    assert candidate["source_flags"]["strategy_name"] == "liquidity_imbalance"
    assert candidate["source_flags"]["pro_signal"]["family"] == "order_flow"
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pytest -q tests/strategies/test_pro_decision_adapter_elite.py -q`
Expected: fail because the current adapter still mirrors edge into all rank/confidence fields and leaves tradability too permissive.

- [ ] **Step 3: Implement the conservative rank normalization**

```python
def _quality_penalty(market_data: dict[str, Any]) -> float:
    quote_age = _safe_float(market_data.get("quote_age_sec"), default=0.0)
    spread_pct = _safe_float(market_data.get("spread_pct"), default=0.0)
    data_confidence = _safe_float(market_data.get("data_confidence"), default=1.0)
    freshness = max(0.0, 1.0 - min(quote_age / 8.0, 1.0))
    spread_quality = max(0.0, 1.0 - min(spread_pct / 0.02, 1.0))
    return max(0.0, min(1.0, (freshness * 0.40) + (spread_quality * 0.30) + (data_confidence * 0.30)))


def pro_signal_to_candidate(signal: ProSignal, market_data: dict[str, Any]) -> dict[str, Any]:
    source_flags = dict(market_data.get("source_flags") or {})
    source_flags.update(
        {
            "strategy_layer": "pro",
            "strategy_name": signal.name,
            "strategy_reason": signal.reason,
            "pro_signal": asdict(signal),
        }
    )
    edge = _signal_edge_score(signal)
    quality = _quality_penalty(market_data)
    rank = max(0.0, min(1.0, (edge * 0.72) + (quality * 0.28)))
    tradable = bool(
        market_data.get("execution_allowed", False)
        and quote_ok
        and liquidity_ok
        and spread_ok
        and quality >= 0.55
    )
    return {
        "symbol": market_data.get("symbol"),
        "instrument_id": market_data.get("instrument_id"),
        "direction": signal.direction,
        "side": "BUY",
        "strategy": signal.name,
        "strategy_family": "pro_layer",
        "reason": signal.reason,
        "raw_edge_score": edge,
        "confidence_raw": edge,
        "confidence": edge,
        "gating_final_confidence": rank,
        "confidence_final": rank,
        "rank_score": rank,
        "tradable": tradable,
        "execution_allowed": tradable,
        "source_flags": {
            **source_flags,
            "pro_rank_quality": round(quality, 4),
        },
    }
```

- [ ] **Step 4: Re-run the test and confirm it passes**

Run: `pytest -q tests/strategies/test_pro_decision_adapter_elite.py -q`
Expected: pass, with candidate ranking lower on stale or weak-quality data and provenance preserved.

- [ ] **Step 5: Commit**

```bash
git add strategies/pro_layer/pro_decision_adapter.py tests/strategies/test_pro_decision_adapter_elite.py
git commit -m "feat: make pro strategy ranking conservative"
```

## Task 3: Prove determinism and offline precision

**Files:**
- Create: `tests/strategies/test_pro_strategy_replay_elite.py`
- Modify: `tests/strategies/test_pro_strategy_engine_elite.py`
- Modify: `tests/strategies/test_pro_decision_adapter_elite.py`

- [ ] **Step 1: Write the replay test**

```python
from strategies.pro_layer.pro_decision_adapter import evaluate_pro_strategy_candidates, best_pro_strategy_decision


def test_pro_strategy_replay_is_deterministic():
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "789",
        "regime": "TREND",
        "atr": 1.8,
        "ltp_change_window": 1.45,
        "vol_z": 1.7,
        "bid_qty": 860,
        "ask_qty": 120,
        "quote_age_sec": 1.1,
        "spread_pct": 0.009,
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "execution_allowed": True,
        "data_confidence": 0.92,
    }
    first = evaluate_pro_strategy_candidates(market_data)
    second = evaluate_pro_strategy_candidates(dict(market_data))
    assert first == second
    assert best_pro_strategy_decision(market_data) == (first[0] if first else None)
```

- [ ] **Step 2: Run the test to confirm it fails on current behavior**

Run: `pytest -q tests/strategies/test_pro_strategy_replay_elite.py -q`
Expected: fail if the current adapter/aggregator ordering is not stable or if quality gates still let borderline candidates through.

- [ ] **Step 3: Lock down replay-friendly behavior**

```python
def _sort_key(candidate: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        float(candidate.get("final_score") or candidate.get("final_rank_score") or 0.0),
        float(candidate.get("confidence_final") or candidate.get("confidence") or 0.0),
        float(candidate.get("raw_edge_score") or 0.0),
        str(candidate.get("strategy") or ""),
    )


def evaluate_pro_strategy_candidates(market_data: dict[str, Any]) -> list[dict[str, Any]]:
    engine = ProStrategyEngine()
    decisions: list[dict[str, Any]] = []
    for signal in engine.run(market_data):
        candidate = pro_signal_to_candidate(signal, market_data)
        decisions.append(evaluate_candidate_decision(candidate))
    decisions.sort(key=_sort_key, reverse=True)
    return decisions
```

- [ ] **Step 4: Re-run the test and confirm it passes**

Run: `pytest -q tests/strategies/test_pro_strategy_replay_elite.py -q`
Expected: pass, with identical inputs producing identical ranked outputs.

- [ ] **Step 5: Commit**

```bash
git add tests/strategies/test_pro_strategy_replay_elite.py strategies/pro_layer/pro_decision_adapter.py
git commit -m "test: lock in pro strategy replay determinism"
```

## Task 4: Add a flag-gated integration seam without changing default behavior

**Files:**
- Modify: `config/config.py`
- Create: `core/pro_strategy_pipeline.py`
- Modify: `core/orchestrator.py`
- Create: `tests/test_pro_strategy_pipeline.py`

- [ ] **Step 1: Write the failing integration-seam test**

```python
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


def test_pro_pipeline_disabled_by_default():
    result = run_pro_strategy_pipeline([{"symbol": "NIFTY"}])
    assert result["enabled"] is False
    assert result["flags"]["ENABLE_PRO_STRATEGY_LAYER"] is False
    assert result["candidates"] == []
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pytest -q tests/test_pro_strategy_pipeline.py -q`
Expected: fail until the gated pipeline exists.

- [ ] **Step 3: Add the gated pipeline and config flag**

```python
# config/config.py
ENABLE_PRO_STRATEGY_LAYER = os.getenv("ENABLE_PRO_STRATEGY_LAYER", "false").lower() == "true"
PRO_STRATEGY_LAYER_STRICT_MODE = os.getenv("PRO_STRATEGY_LAYER_STRICT_MODE", "true").lower() == "true"

# core/pro_strategy_pipeline.py
from config import config as cfg
from strategies.pro_layer.pro_decision_adapter import evaluate_pro_strategy_candidates


def run_pro_strategy_pipeline(market_data_list, *, now_ts=None):
    flags = {
        "ENABLE_PRO_STRATEGY_LAYER": bool(getattr(cfg, "ENABLE_PRO_STRATEGY_LAYER", False)),
        "PRO_STRATEGY_LAYER_STRICT_MODE": bool(getattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True)),
    }
    if not flags["ENABLE_PRO_STRATEGY_LAYER"]:
        return {"enabled": False, "flags": flags, "candidates": []}
    market_data_list = list(market_data_list or [])
    candidates = []
    for market_data in market_data_list:
        best = best_pro_strategy_decision(market_data)
        if best:
            candidates.append(best)
    return {"enabled": True, "flags": flags, "candidates": candidates, "errors": []}
```

- [ ] **Step 4: Wire the pipeline behind the flag only**

```python
# core/orchestrator.py
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


def maybe_run_pro_strategy_layer(market_data_list):
    if not bool(getattr(cfg, "ENABLE_PRO_STRATEGY_LAYER", False)):
        return {"enabled": False, "candidates": []}
    return run_pro_strategy_pipeline(market_data_list)
```

- [ ] **Step 5: Re-run the test and confirm it passes**

Run: `pytest -q tests/test_pro_strategy_pipeline.py -q`
Expected: pass with the pipeline disabled by default and no change to current live behavior.

- [ ] **Step 6: Commit**

```bash
git add config/config.py core/pro_strategy_pipeline.py core/orchestrator.py tests/test_pro_strategy_pipeline.py
git commit -m "feat: add gated pro strategy integration seam"
```

## Validation Sequence

Run these after each task, in order:

```bash
pytest -q tests/strategies/test_pro_strategy_engine_elite.py -q
pytest -q tests/strategies/test_pro_decision_adapter_elite.py -q
pytest -q tests/strategies/test_pro_strategy_replay_elite.py -q
pytest -q tests/test_pro_strategy_pipeline.py -q
pytest -q tests/strategies
```

## Migration Notes

- New config keys:
  - `ENABLE_PRO_STRATEGY_LAYER` defaults to `false`
  - `PRO_STRATEGY_LAYER_STRICT_MODE` defaults to `true`
- Existing live behavior stays unchanged until the new flag is enabled.
- Time-window logic stops acting like a standalone trade trigger; it becomes a booster only.
- The adapter becomes intentionally more conservative, so a lower candidate count is a success condition, not a regression.
- Do not wire the new flag on in live execution until offline replay and shadow validation are clean.

## Rollout Steps

1. Harden signal generation in the isolated worktree.
2. Tighten ranking and provenance handling in the adapter.
3. Prove deterministic replay and lower false-positive behavior offline.
4. Add the flag-gated integration seam with the flag disabled by default.
5. Re-run the validation sequence and only then consider a shadow-only promotion path.

## Open Risks

- If the signal gates are too strict, the layer may over-suppress valid opportunities.
- If the adapter quality penalty is too aggressive, the decision engine may receive too few candidates.
- If the integration seam is enabled too early, the branch can start changing live behavior before the offline bar is met.
