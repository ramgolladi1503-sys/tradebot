# Symbol Clustering + Portfolio Selection Patch

Base branch: `main-v2`
Working branch: `feature/symbol-clustering-portfolio-selection`

This patch is the next layer after execution truth and regime intelligence. It stops one symbol from flooding ranking and adds a basket-selection step so top-ranked does not automatically mean selected-for-execution.

## Why this patch is needed

Current behavior in `core/opportunity_engine.py`:
- candidates are globally sorted
- `rank_within_symbol` is annotated, but symbol crowding is not constrained
- capital allocator and portfolio optimizer run after ranking, but there is no explicit pre-selection clustering step

This causes these problems:
1. NIFTY can dominate the board by volume, even if several rows are near-duplicates.
2. Slightly lower-ranked but diversifying setups can be buried.
3. The engine behaves like a row sorter, not a basket selector.

## Add these helpers in `core/opportunity_engine.py`

```python
def _symbol_key(candidate: Any) -> str:
    return str(_get_value(candidate, "symbol") or "").strip().upper()


def _underlying_family(candidate: Any) -> str:
    source_flags = dict(_get_value(candidate, "source_flags", {}) or {})
    return str(
        _get_value(candidate, "underlying_family")
        or source_flags.get("underlying_family")
        or _symbol_key(candidate)
    ).strip().upper()


def _cluster_candidates_by_symbol(
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    *,
    max_per_symbol: int,
) -> list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]]:
    if max_per_symbol <= 0:
        return list(scored)

    grouped: dict[str, list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]]] = {}
    for item in scored:
        symbol = _symbol_key(item[1])
        grouped.setdefault(symbol, []).append(item)

    clustered: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]] = []
    for _symbol, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda item: item[0], reverse=True)
        clustered.extend(rows_sorted[:max_per_symbol])

    clustered.sort(key=lambda item: item[0], reverse=True)
    return clustered


def _portfolio_selection_score(candidate: Any, metrics: dict[str, Any]) -> float:
    base = float(metrics.get("opportunity_score") or 0.0)
    execution_quality = float(metrics.get("execution_quality_score") or 0.0)
    fill_probability = float(metrics.get("fill_probability") or 0.0)
    rr_quality = float(metrics.get("risk_adjusted_quality") or 0.0)
    return (
        (base * 0.45)
        + (execution_quality * 0.20)
        + (fill_probability * 0.20)
        + (rr_quality * 0.15)
    )


def _select_portfolio_candidates(
    scored: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]],
    *,
    max_positions: int,
    max_per_family: int,
) -> list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]]:
    if max_positions <= 0:
        return []

    selected: list[tuple[tuple[int, float, float, float], Any, dict[str, Any]]] = []
    family_counts: dict[str, int] = {}

    rescored = sorted(
        scored,
        key=lambda item: (
            _portfolio_selection_score(item[1], item[2]),
            float(item[2].get("opportunity_score") or 0.0),
            float(item[2].get("execution_quality_score") or 0.0),
        ),
        reverse=True,
    )

    for item in rescored:
        candidate = item[1]
        family = _underlying_family(candidate)
        if max_per_family > 0 and family_counts.get(family, 0) >= max_per_family:
            continue
        selected.append(item)
        family_counts[family] = family_counts.get(family, 0) + 1
        if len(selected) >= max_positions:
            break

    return selected
```

## Patch `annotate_ranked_opportunities()`

Right after `scored.sort(...)`, add symbol clustering:

```python
max_per_symbol = max(0, int(getattr(cfg, "OPPORTUNITY_MAX_PER_SYMBOL", 2) or 0))
scored = _cluster_candidates_by_symbol(scored, max_per_symbol=max_per_symbol)
```

Then, after clustering and before final annotation loop, add basket pre-selection:

```python
max_positions = max(1, int(getattr(cfg, "OPPORTUNITY_MAX_PORTFOLIO_POSITIONS", executable_top_n) or executable_top_n))
max_per_family = max(0, int(getattr(cfg, "OPPORTUNITY_MAX_PER_UNDERLYING_FAMILY", 1) or 0))
portfolio_selected = _select_portfolio_candidates(
    [item for item in scored if bool(item[2].get("execution_eligible"))],
    max_positions=max_positions,
    max_per_family=max_per_family,
)
portfolio_selected_keys = {
    str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "instrument_id") or "")
    for _sort_key, candidate, _metrics in portfolio_selected
}
```

Then change `selected = ...` in the annotation loop to:

```python
candidate_key = str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or _get_value(candidate, "instrument_id") or "")
selected = bool(
    metrics["execution_eligible"]
    and candidate_key in portfolio_selected_keys
    and score >= adaptive_threshold
)
```

## Add metadata to output/source_flags

Add these fields where you already update `source_flags` and candidate payloads:

```python
"underlying_family": _underlying_family(candidate),
"portfolio_selection_score": round(_portfolio_selection_score(candidate, metrics), 6),
"cluster_symbol": _symbol_key(candidate),
```

## Suggested config additions

Add these in config if missing:

```python
OPPORTUNITY_MAX_PER_SYMBOL = 2
OPPORTUNITY_MAX_PORTFOLIO_POSITIONS = 3
OPPORTUNITY_MAX_PER_UNDERLYING_FAMILY = 1
```

## Add tests

Create `tests/test_symbol_clustering_portfolio_selection.py`

```python
from core.opportunity_engine import annotate_ranked_opportunities


def _candidate(trade_id, symbol, score_bias=0.82, **overrides):
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
        "builder_confidence": score_bias,
        "permission_confidence": score_bias,
        "gating_final_confidence": score_bias,
        "sizing_confluence_score": score_bias,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_symbol_clustering_limits_symbol_crowding(monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "OPPORTUNITY_MAX_PER_SYMBOL", 2, raising=False)

    candidates = [
        _candidate(f"n{i}", "NIFTY", score_bias=0.90 - (i * 0.01))
        for i in range(5)
    ] + [
        _candidate("b1", "BANKNIFTY", score_bias=0.84),
        _candidate("s1", "SENSEX", score_bias=0.83),
    ]

    ranked = annotate_ranked_opportunities(candidates, scope="unit", top_n=5)
    selected = [row for row in ranked if row.get("selected_for_execution")]
    nifty_selected = [row for row in selected if row.get("symbol") == "NIFTY"]
    assert len(nifty_selected) <= 2


def test_portfolio_selection_prefers_diversified_basket(monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "OPPORTUNITY_MAX_PER_SYMBOL", 2, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_MAX_PORTFOLIO_POSITIONS", 3, raising=False)
    monkeypatch.setattr(cfg, "OPPORTUNITY_MAX_PER_UNDERLYING_FAMILY", 1, raising=False)

    candidates = [
        _candidate("n1", "NIFTY", score_bias=0.90),
        _candidate("n2", "NIFTY", score_bias=0.89),
        _candidate("b1", "BANKNIFTY", score_bias=0.84),
        _candidate("s1", "SENSEX", score_bias=0.83),
    ]

    ranked = annotate_ranked_opportunities(candidates, scope="unit", top_n=5)
    selected = [row for row in ranked if row.get("selected_for_execution")]
    families = {row.get("source_flags", {}).get("underlying_family", row.get("symbol")) for row in selected}
    assert len(selected) <= 3
    assert len(families) == len(selected)
```

## Expected outcomes

1. NIFTY no longer floods the top list by raw candidate count.
2. Slightly lower-ranked but diversifying symbols remain visible and selectable.
3. Final execution set becomes a basket, not just the first few rows from one symbol.
4. Portfolio optimizer works on a cleaner pre-selected opportunity set.
