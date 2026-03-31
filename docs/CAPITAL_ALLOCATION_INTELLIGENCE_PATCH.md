# Capital Allocation Intelligence Patch

Base branch: `main-v2`
Working branch: `feature/capital-allocation-intelligence`

This patch is the next layer after execution truth, regime-aware scoring, and symbol clustering. It converts the engine from simple candidate selection into controlled capital deployment.

## Why this patch is needed

Current behavior:
- `annotate_ranked_opportunities()` can mark candidates selected for execution
- `allocate_capital_slots()` exists, but selection still depends too much on row order and static slot behavior
- there is no explicit risk-budget-based sizing step driven by stop distance, execution quality, and opportunity quality

This causes these problems:
1. strong and weak trades can get similar size
2. concentrated risk can sneak in even after symbol clustering
3. execution-quality-aware opportunities are not rewarded with better sizing
4. capital usage is not explicitly bounded by a portfolio risk budget

## Add these helpers in `core/opportunity_engine.py`

```python
def _candidate_risk_cost(candidate: Any) -> float:
    entry_price = _safe_float(_get_value(candidate, "entry_price")) or _safe_float(_get_value(candidate, "execution_entry"))
    stop_loss = _safe_float(_get_value(candidate, "stop_loss"))
    qty = _safe_float(_get_value(candidate, "qty_units")) or _safe_float(_get_value(candidate, "qty")) or 1.0
    if entry_price in (None, 0.0) or stop_loss is None:
        return max(1.0, float(qty))
    per_unit_risk = max(abs(float(entry_price) - float(stop_loss)), 0.01)
    return max(0.01, per_unit_risk * max(float(qty), 1.0))


def _capital_allocation_score(candidate: Any, metrics: dict[str, Any]) -> float:
    opportunity_score = float(metrics.get("opportunity_score") or 0.0)
    execution_quality = float(metrics.get("execution_quality_score") or 0.0)
    fill_probability = float(metrics.get("fill_probability") or 0.0)
    rr_quality = float(metrics.get("risk_adjusted_quality") or 0.0)
    gating_confidence = float(metrics.get("gating_final_confidence") or 0.0)
    return (
        (opportunity_score * 0.35)
        + (execution_quality * 0.20)
        + (fill_probability * 0.15)
        + (rr_quality * 0.15)
        + (gating_confidence * 0.15)
    )


def _size_multiplier_from_quality(score: float) -> float:
    score = max(0.0, min(1.0, float(score)))
    if score >= 0.85:
        return 1.00
    if score >= 0.70:
        return 0.75
    if score >= 0.55:
        return 0.50
    if score >= 0.40:
        return 0.25
    return 0.0


def _allocate_capital_by_risk_budget(
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    *,
    max_positions: int,
    max_total_risk_budget: float,
    max_per_trade_risk: float,
) -> dict[str, dict[str, float | str | bool]]:
    selected: dict[str, dict[str, float | str | bool]] = {}
    used_risk = 0.0

    ranked = sorted(
        scored,
        key=lambda item: (
            _capital_allocation_score(item[1], item[2]),
            float(item[2].get("opportunity_score") or 0.0),
            float(item[2].get("execution_quality_score") or 0.0),
        ),
        reverse=True,
    )

    for _sort_key, candidate, metrics in ranked:
        if len(selected) >= max_positions:
            break
        key = str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "instrument_id") or "")
        if not key:
            continue

        risk_cost_raw = _candidate_risk_cost(candidate)
        risk_cost = min(float(risk_cost_raw), float(max_per_trade_risk)) if max_per_trade_risk > 0 else float(risk_cost_raw)
        quality_score = _capital_allocation_score(candidate, metrics)
        size_mult = _size_multiplier_from_quality(quality_score)

        effective_risk = risk_cost * size_mult
        if size_mult <= 0:
            selected[key] = {
                "allocated": False,
                "capital_reason": "below_quality_floor",
                "capital_score": round(quality_score, 6),
                "risk_cost": round(risk_cost, 6),
                "size_multiplier": 0.0,
            }
            continue

        if max_total_risk_budget > 0 and (used_risk + effective_risk) > max_total_risk_budget:
            selected[key] = {
                "allocated": False,
                "capital_reason": "risk_budget_exceeded",
                "capital_score": round(quality_score, 6),
                "risk_cost": round(risk_cost, 6),
                "size_multiplier": round(size_mult, 6),
            }
            continue

        used_risk += effective_risk
        selected[key] = {
            "allocated": True,
            "capital_reason": "allocated",
            "capital_score": round(quality_score, 6),
            "risk_cost": round(risk_cost, 6),
            "size_multiplier": round(size_mult, 6),
            "effective_risk": round(effective_risk, 6),
            "used_total_risk": round(used_risk, 6),
        }

    return selected
```

## Patch `annotate_ranked_opportunities()`

After your symbol clustering / portfolio-selection stage, add capital allocation over the executable subset:

```python
capital_max_positions = max(1, int(getattr(cfg, "OPPORTUNITY_CAPITAL_MAX_POSITIONS", executable_top_n) or executable_top_n))
capital_total_risk_budget = max(0.0, float(getattr(cfg, "OPPORTUNITY_CAPITAL_TOTAL_RISK_BUDGET", 0.0) or 0.0))
capital_per_trade_risk = max(0.0, float(getattr(cfg, "OPPORTUNITY_CAPITAL_MAX_PER_TRADE_RISK", 0.0) or 0.0))

capital_map = _allocate_capital_by_risk_budget(
    [item for item in scored if bool(item[2].get("execution_eligible"))],
    max_positions=capital_max_positions,
    max_total_risk_budget=capital_total_risk_budget,
    max_per_trade_risk=capital_per_trade_risk,
)
```

Then inside the final annotation loop, after `candidate_key` is known, apply:

```python
capital_meta = capital_map.get(candidate_key, {})
capital_allocated = bool(capital_meta.get("allocated", False))
selected = bool(
    metrics["execution_eligible"]
    and capital_allocated
    and score >= adaptive_threshold
)
```

## Add metadata to source_flags and payload

Add these fields in the `source_flags` update and candidate update blocks:

```python
"capital_score": capital_meta.get("capital_score"),
"capital_reason": capital_meta.get("capital_reason"),
"capital_allocated": bool(capital_meta.get("allocated", False)),
"risk_cost": capital_meta.get("risk_cost"),
"size_multiplier": capital_meta.get("size_multiplier"),
"effective_risk": capital_meta.get("effective_risk"),
"used_total_risk": capital_meta.get("used_total_risk"),
```

For dict/object payloads also set:

```python
"capital_score": capital_meta.get("capital_score"),
"capital_reason": capital_meta.get("capital_reason"),
"capital_allocated": bool(capital_meta.get("allocated", False)),
"risk_cost": capital_meta.get("risk_cost"),
"effective_risk": capital_meta.get("effective_risk"),
```

## Suggested config additions

```python
OPPORTUNITY_CAPITAL_MAX_POSITIONS = 3
OPPORTUNITY_CAPITAL_TOTAL_RISK_BUDGET = 1500.0
OPPORTUNITY_CAPITAL_MAX_PER_TRADE_RISK = 700.0
```

These are just placeholders. Your actual values should match your account size and option lot risk.

## Add tests

Create `tests/test_capital_allocation_intelligence.py`

```python
from core.opportunity_engine import annotate_ranked_opportunities


def _candidate(trade_id, symbol, builder=0.82, entry=100.0, stop=95.0, target=110.0, qty=10, **overrides):
    base = {
        "trade_id": trade_id,
        "symbol": symbol,
        "execution_entry": entry,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "display_entry": entry,
        "display_entry_status": "displayable",
        "builder_confidence": builder,
        "permission_confidence": builder,
        "gating_final_confidence": builder,
        "sizing_confluence_score": builder,
        "entry_price": entry,
        "stop_loss": stop,
        "target": target,
        "qty_units": qty,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_capital_budget_blocks_excess_risk(monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_MAX_POSITIONS", 3, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_TOTAL_RISK_BUDGET", 200.0, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_MAX_PER_TRADE_RISK", 150.0, raising=False)

    candidates = [
        _candidate("t1", "NIFTY", builder=0.90, qty=20),
        _candidate("t2", "BANKNIFTY", builder=0.88, qty=20),
        _candidate("t3", "SENSEX", builder=0.86, qty=20),
    ]

    ranked = annotate_ranked_opportunities(candidates, scope="unit", top_n=5)
    selected = [row for row in ranked if row.get("selected_for_execution")]
    assert len(selected) < 3
    assert any((row.get("capital_reason") == "risk_budget_exceeded") for row in ranked)


def test_better_quality_gets_higher_size_multiplier(monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_MAX_POSITIONS", 3, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_TOTAL_RISK_BUDGET", 1000.0, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_CAPITAL_MAX_PER_TRADE_RISK", 700.0, raising=False)

    high = _candidate("high", "NIFTY", builder=0.92)
    mid = _candidate("mid", "BANKNIFTY", builder=0.60)

    ranked = annotate_ranked_opportunities([high, mid], scope="unit", top_n=5)
    rows = {row["trade_id"]: row for row in ranked}
    assert float(rows["high"].get("size_multiplier") or 0.0) >= float(rows["mid"].get("size_multiplier") or 0.0)
```

## Expected outcomes

1. Better trades get bigger size multipliers.
2. Weak trades get reduced size or zero allocation.
3. Total portfolio risk stays inside an explicit budget.
4. Selection becomes capital-aware, not just rank-aware.
5. Engine becomes much closer to a real deployment system.
