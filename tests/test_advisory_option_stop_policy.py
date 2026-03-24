from __future__ import annotations

from core.advisory_row_integrity import recompute_levels_from_final_entry


def _row(
    *,
    entry: float,
    stop_loss: float | None = None,
    side: str = "BUY",
    instrument_type: str = "OPT",
    bid: float | None = None,
    ask: float | None = None,
) -> dict:
    payload: dict = {
        "final_entry": entry,
        "side": side,
        "instrument_type": instrument_type,
    }
    if stop_loss is not None:
        payload["stop_loss"] = stop_loss
    if bid is not None:
        payload["best_bid"] = bid
    if ask is not None:
        payload["best_ask"] = ask
    return payload


def test_option_stop_caps_deep_drawdown_for_buy_options():
    row = _row(entry=100.0, stop_loss=20.0)
    out = recompute_levels_from_final_entry(
        row,
        option_stop_tighten=True,
        option_stop_max_pct=0.35,
        option_stop_min_pct=0.1,
    )

    assert float(out["stop_loss"]) == 65.0
    assert float(out["target"]) > 100.0


def test_option_stop_allows_deeper_drawdown_when_configured():
    row = _row(entry=100.0, stop_loss=20.0)
    out = recompute_levels_from_final_entry(
        row,
        option_stop_tighten=True,
        option_stop_max_pct=0.9,
        option_stop_min_pct=0.05,
    )

    assert float(out["stop_loss"]) == 20.0


def test_option_stop_floor_uses_min_pct_and_spread_floor():
    row = _row(entry=50.0, stop_loss=None, bid=49.0, ask=51.0)
    out = recompute_levels_from_final_entry(
        row,
        option_stop_tighten=True,
        option_stop_max_pct=0.35,
        option_stop_min_pct=0.1,
        option_stop_spread_mult=2.0,
    )

    assert float(out["stop_loss"]) == 45.0
