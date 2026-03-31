# Adaptive Position Sizing + Drawdown Control Patch

Base branch: `main-v2`
Working branch: `feature/adaptive-position-sizing-drawdown-control`

This patch is the next layer after capital allocation intelligence. It prevents the system from sizing the same way through winning and losing conditions, and adds guardrails that reduce aggression during drawdowns.

## Why this patch is needed

Current behavior:
- selection and capital allocation can choose the right trades
- but size still does not react enough to portfolio stress, recent hit rate, or drawdown state
- the engine can remain too aggressive after a losing streak

This causes these problems:
1. the bot can keep firing full-risk trades into a bad regime
2. losses can cluster and compound before size adapts
3. winning regimes are not exploited efficiently enough
4. portfolio risk budget is static rather than context-aware

## Add these helpers in `core/opportunity_engine.py`

```python
def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _portfolio_health_snapshot(current_portfolio_exposure: Any = None) -> dict[str, float]:
    exposure = current_portfolio_exposure or {}
    if not isinstance(exposure, dict):
        exposure = {}

    drawdown_pct = _safe_float(exposure.get("drawdown_pct")) or 0.0
    recent_win_rate = _safe_float(exposure.get("recent_win_rate")) or 0.5
    losing_streak = _safe_int(exposure.get("losing_streak")) or 0
    daily_pnl = _safe_float(exposure.get("daily_pnl")) or 0.0
    peak_to_trough = _safe_float(exposure.get("peak_to_trough_drawdown_pct")) or drawdown_pct

    return {
        "drawdown_pct": max(0.0, float(drawdown_pct)),
        "recent_win_rate": max(0.0, min(1.0, float(recent_win_rate))),
        "losing_streak": max(0, int(losing_streak)),
        "daily_pnl": float(daily_pnl),
        "peak_to_trough_drawdown_pct": max(0.0, float(peak_to_trough)),
    }


def _drawdown_risk_multiplier(snapshot: dict[str, float]) -> tuple[float, str]:
    drawdown_pct = float(snapshot.get("drawdown_pct") or 0.0)
    losing_streak = int(snapshot.get("losing_streak") or 0)
    win_rate = float(snapshot.get("recent_win_rate") or 0.5)

    mult = 1.0
    reasons: list[str] = []

    if drawdown_pct >= 8.0:
        mult *= 0.25
        reasons.append("drawdown>=8")
    elif drawdown_pct >= 5.0:
        mult *= 0.50
        reasons.append("drawdown>=5")
    elif drawdown_pct >= 3.0:
        mult *= 0.75
        reasons.append("drawdown>=3")

    if losing_streak >= 5:
        mult *= 0.50
        reasons.append("losing_streak>=5")
    elif losing_streak >= 3:
        mult *= 0.75
        reasons.append("losing_streak>=3")

    if win_rate <= 0.35:
        mult *= 0.75
        reasons.append("win_rate<=0.35")
    elif win_rate >= 0.65 and drawdown_pct < 3.0:
        mult *= 1.10
        reasons.append("win_rate>=0.65")

    mult = max(0.10, min(1.15, mult))
    return mult, ";".join(reasons) if reasons else "base"


def _adaptive_size_multiplier(
    base_size_multiplier: float,
    capital_size_multiplier: float,
    current_portfolio_exposure: Any = None,
) -> tuple[float, dict[str, Any]]:
    snapshot = _portfolio_health_snapshot(current_portfolio_exposure)
    risk_mult, reason = _drawdown_risk_multiplier(snapshot)
    raw = float(base_size_multiplier) * float(capital_size_multiplier) * float(risk_mult)
    final_mult = max(0.0, min(1.0, raw))
    return final_mult, {
        "portfolio_health": snapshot,
        "drawdown_risk_multiplier": round(float(risk_mult), 6),
        "adaptive_size_reason": reason,
        "adaptive_size_multiplier": round(float(final_mult), 6),
    }
```

## Patch `annotate_ranked_opportunities()`

Inside the final annotation loop, after existing `size_multiplier` and `capital_meta` are available, add:

```python
capital_size_multiplier = _safe_float(capital_meta.get("size_multiplier")) or 1.0
adaptive_size_multiplier, adaptive_meta = _adaptive_size_multiplier(
    base_size_multiplier=size_multiplier,
    capital_size_multiplier=capital_size_multiplier,
    current_portfolio_exposure=current_portfolio_exposure,
)
```

Then update final selection logic to require non-zero adaptive size:

```python
selected = bool(
    metrics["execution_eligible"]
    and capital_allocated
    and adaptive_size_multiplier > 0.0
    and score >= adaptive_threshold
)
```

## Add metadata to source_flags and payload

Add these to source flags and candidate payloads:

```python
"drawdown_risk_multiplier": adaptive_meta.get("drawdown_risk_multiplier"),
"adaptive_size_reason": adaptive_meta.get("adaptive_size_reason"),
"adaptive_size_multiplier": adaptive_meta.get("adaptive_size_multiplier"),
"portfolio_drawdown_pct": adaptive_meta.get("portfolio_health", {}).get("drawdown_pct"),
"portfolio_recent_win_rate": adaptive_meta.get("portfolio_health", {}).get("recent_win_rate"),
"portfolio_losing_streak": adaptive_meta.get("portfolio_health", {}).get("losing_streak"),
```

For dict/object payloads also set:

```python
"drawdown_risk_multiplier": adaptive_meta.get("drawdown_risk_multiplier"),
"adaptive_size_reason": adaptive_meta.get("adaptive_size_reason"),
"adaptive_size_multiplier": adaptive_meta.get("adaptive_size_multiplier"),
```

When computing final `size_mult`, replace the current multiplication with adaptive size:

```python
"size_mult": (
    (_safe_float(updated.get("size_mult")) or 1.0) * adaptive_size_multiplier
    if selected
    else (_safe_float(updated.get("size_mult")) or 1.0)
)
```

## Suggested config additions

```python
OPPORTUNITY_DRAWDOWN_SOFT_LIMIT_PCT = 3.0
OPPORTUNITY_DRAWDOWN_HARD_LIMIT_PCT = 8.0
OPPORTUNITY_LOSING_STREAK_SOFT_LIMIT = 3
OPPORTUNITY_LOSING_STREAK_HARD_LIMIT = 5
```

The helper above is self-contained, but these settings document the intended thresholds.

## Add tests

Create `tests/test_adaptive_position_sizing_drawdown.py`

```python
from core.opportunity_engine import annotate_ranked_opportunities


def _candidate(trade_id, symbol="NIFTY", builder=0.85, **overrides):
    base = {
        "trade_id": trade_id,
        "symbol": symbol,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "display_entry": 100.0,
        "display_entry_status": "displayable",
        "builder_confidence": builder,
        "permission_confidence": builder,
        "gating_final_confidence": builder,
        "sizing_confluence_score": builder,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "qty_units": 10,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_drawdown_reduces_size_multiplier():
    candidate = _candidate("t1")

    normal = annotate_ranked_opportunities(
        [candidate],
        scope="unit",
        top_n=1,
        current_portfolio_exposure={"drawdown_pct": 0.0, "recent_win_rate": 0.55, "losing_streak": 0},
    )[0]

    stressed = annotate_ranked_opportunities(
        [candidate],
        scope="unit",
        top_n=1,
        current_portfolio_exposure={"drawdown_pct": 6.0, "recent_win_rate": 0.30, "losing_streak": 4},
    )[0]

    assert float(stressed.get("adaptive_size_multiplier") or 0.0) < float(normal.get("adaptive_size_multiplier") or 0.0)


def test_extreme_drawdown_can_zero_or_near_zero_aggression():
    candidate = _candidate("t2")
    stressed = annotate_ranked_opportunities(
        [candidate],
        scope="unit",
        top_n=1,
        current_portfolio_exposure={"drawdown_pct": 9.0, "recent_win_rate": 0.25, "losing_streak": 6},
    )[0]

    assert float(stressed.get("drawdown_risk_multiplier") or 0.0) <= 0.25


def test_healthy_portfolio_can_keep_fuller_size():
    candidate = _candidate("t3")
    healthy = annotate_ranked_opportunities(
        [candidate],
        scope="unit",
        top_n=1,
        current_portfolio_exposure={"drawdown_pct": 0.5, "recent_win_rate": 0.70, "losing_streak": 0},
    )[0]

    assert float(healthy.get("adaptive_size_multiplier") or 0.0) > 0.5
```

## Expected outcomes

1. After a losing streak, the engine automatically cuts aggression.
2. Deep drawdowns force materially smaller size.
3. Healthy periods can keep fuller size without breaking hard budget rules.
4. Risk management becomes adaptive rather than static.
5. The engine becomes much harder to kill during bad market phases.
