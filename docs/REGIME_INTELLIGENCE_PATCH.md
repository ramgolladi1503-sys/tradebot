# Regime Intelligence Patch for `core/opportunity_engine.py`

Base branch: `main-v2`
Working branch: `feature/regime-intelligence-layer`

This patch documents the exact code changes needed to add regime-aware scoring on top of the already merged execution-truth guard.

## Current state

- `_candidate_class()` and `_execution_truth()` are already merged into `main-v2`.
- `build_opportunity_score()` still uses a mostly flat weighted blend.
- `main-v2` still needs class score caps inside `build_opportunity_score()`.
- regime handling is currently too weak because `regime_alignment` is just one component instead of changing scoring behavior.

## Add these helpers near the existing scoring helpers

```python
def _score_cap_for_candidate_class(candidate_class: str) -> float | None:
    caps = {
        "fallback": 0.39,
        "planning_only": 0.34,
        "synthetic": 0.36,
        "softened": 0.44,
        "advisory": 0.44,
    }
    return caps.get(str(candidate_class or "").strip().lower())


def _normalize_regime(value: Any) -> str:
    return str(value or "").strip().upper()


def _regime_score_adjustments(candidate: Any) -> dict[str, float]:
    regime = _normalize_regime(_get_value(candidate, "regime"))
    countertrend = bool(_get_value(candidate, "countertrend", False))

    adjustments = {
        "builder_mult": 1.0,
        "gating_mult": 1.0,
        "confluence_mult": 1.0,
        "liquidity_mult": 1.0,
        "spread_mult": 1.0,
        "rr_mult": 1.0,
        "threshold_shift": 0.0,
    }

    if regime in {"RANGE", "RANGE_VOLATILE"}:
        adjustments.update({
            "builder_mult": 0.88,
            "gating_mult": 0.92,
            "confluence_mult": 0.90,
            "rr_mult": 1.20,
            "liquidity_mult": 1.05,
            "spread_mult": 1.05,
            "threshold_shift": 0.02,
        })
    elif regime in {"TREND", "TREND_STRONG", "VOLATILE_TREND"}:
        adjustments.update({
            "builder_mult": 1.08,
            "gating_mult": 1.06,
            "confluence_mult": 1.08,
            "rr_mult": 1.05,
            "threshold_shift": -0.01,
        })
    elif regime in {"EVENT", "PANIC"}:
        adjustments.update({
            "builder_mult": 0.82,
            "gating_mult": 0.85,
            "confluence_mult": 0.85,
            "rr_mult": 0.95,
            "liquidity_mult": 0.90,
            "spread_mult": 0.85,
            "threshold_shift": 0.04,
        })

    if countertrend:
        adjustments["builder_mult"] *= 0.9
        adjustments["gating_mult"] *= 0.9
        adjustments["threshold_shift"] += 0.02

    return adjustments
```

## Patch `build_opportunity_score()`

After raw component extraction and before score composition, add:

```python
regime = _normalize_regime(_get_value(candidate, "regime"))
regime_adj = _regime_score_adjustments(candidate)

builder_confidence = _clamp01(builder_confidence * regime_adj["builder_mult"], default=0.0) or 0.0
gating_confidence = _clamp01(gating_confidence * regime_adj["gating_mult"], default=builder_confidence)
confluence_score = _clamp01(confluence_score * regime_adj["confluence_mult"], default=0.5)
liquidity_quality = _clamp01(liquidity_quality * regime_adj["liquidity_mult"], default=0.35) or 0.35
spread_quality = _clamp01(spread_quality * regime_adj["spread_mult"], default=0.0) or 0.0
risk_adjusted_quality = _clamp01(risk_adjusted_quality * regime_adj["rr_mult"], default=0.5) or 0.5
```

Replace the weighted score block with:

```python
score = _weighted_average([
    (builder_confidence, 0.26),
    (permission_confidence, 0.10),
    (gating_confidence, 0.18),
    (confluence_score, 0.14),
    (risk_adjusted_quality, 0.12),
    (regime_alignment, 0.08),
    (liquidity_quality, 0.07),
    (spread_quality, 0.03),
    (freshness_quality, 0.02),
])
```

Keep the execution-quality penalty, then add class cap logic:

```python
score = _clamp01(score - float(execution_quality.spread_penalty or 0.0), default=0.0) or 0.0

candidate_class = _candidate_class(candidate)
class_score_cap = _score_cap_for_candidate_class(candidate_class)
if class_score_cap is not None:
    score = min(score, float(class_score_cap))
```

Shift threshold by regime:

```python
threshold_context = _adaptive_execution_threshold_context(candidate)
threshold_effective = _clamp01(
    float(threshold_context["threshold_effective"]) + float(regime_adj["threshold_shift"]),
    default=float(threshold_context["threshold_effective"]),
) or float(threshold_context["threshold_effective"])
```

Extend return payload:

```python
"regime": regime,
"regime_adjustments": regime_adj,
"candidate_class": candidate_class,
"class_score_cap": class_score_cap,
"adaptive_execution_threshold": float(threshold_effective),
"threshold_effective": float(threshold_effective),
```

## Add test file

Create `tests/test_opportunity_engine_regime_scoring.py` with these cases:

```python
from core.opportunity_engine import build_opportunity_score


def _candidate(**overrides):
    base = {
        "trade_id": "t1",
        "symbol": "NIFTY",
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "display_entry": 100.0,
        "display_entry_status": "displayable",
        "builder_confidence": 0.82,
        "permission_confidence": 0.82,
        "gating_final_confidence": 0.82,
        "sizing_confluence_score": 0.80,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_range_regime_penalizes_directional_setup():
    trend = _candidate(trade_id="trend", regime="TREND")
    range_case = _candidate(trade_id="range", regime="RANGE")
    assert build_opportunity_score(trend)["opportunity_score"] > build_opportunity_score(range_case)["opportunity_score"]


def test_hostile_regime_raises_execution_threshold():
    trend = _candidate(trade_id="trend-threshold", regime="TREND")
    panic = _candidate(trade_id="panic-threshold", regime="PANIC")
    assert build_opportunity_score(panic)["adaptive_execution_threshold"] > build_opportunity_score(trend)["adaptive_execution_threshold"]


def test_class_caps_still_apply_under_regime_adjustments():
    fallback = _candidate(trade_id="fallback", regime="TREND", row_kind="recovered_fallback", source_flags={"candidate_origin": "fallback"})
    planning = _candidate(trade_id="planning", regime="RANGE", planning_only=True, source_flags={"candidate_origin": "planning_only"})
    assert build_opportunity_score(fallback)["opportunity_score"] <= 0.39
    assert build_opportunity_score(planning)["opportunity_score"] <= 0.34
```

## Expected behavioral outcomes

1. Trend setups score higher in trend regimes.
2. Range regimes penalize directional conviction and emphasize RR/liquidity.
3. Hostile regimes raise the adaptive execution threshold.
4. Class caps still prevent fallback/planning rows from polluting the ranking.
