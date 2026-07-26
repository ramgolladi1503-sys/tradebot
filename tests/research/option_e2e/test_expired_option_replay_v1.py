from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    Contract,
    OptionIntent,
    ReplayDataError,
    build_contract_inventory,
    chronological_partitions,
    metrics,
    replay_intent,
    resolve_contract,
)

IST = ZoneInfo("Asia/Kolkata")


def _intent(*, price: float = 21426.0, option_type: str = "CE", day: int = 14) -> OptionIntent:
    signal = datetime(2026, 7, day, 10, 0, tzinfo=IST)
    return OptionIntent(
        strategy_id="opening_range_retest_v1",
        underlying="NIFTY",
        signal_timestamp=signal,
        earliest_entry_timestamp=signal + timedelta(minutes=1),
        direction="BUY_CALL" if option_type == "CE" else "BUY_PUT",
        option_type=option_type,
        underlying_price=price,
        signal_identity_hash="signal-1",
    )


def _contract(strike: float, option_type: str = "CE") -> Contract:
    return Contract(
        underlying="NIFTY",
        expiry=datetime(2026, 7, 14).date(),
        option_type=option_type,
        strike=strike,
        instrument_key=f"NSE_FO|{int(strike)}|14-07-2026",
        trading_symbol=f"NIFTY {strike} {option_type}",
        lot_size=65,
        raw_contract_path="contracts.json",
        raw_candle_path=f"{strike}.json",
    )


def test_entry_must_be_strictly_after_signal() -> None:
    signal = datetime(2026, 7, 14, 10, 0, tzinfo=IST)
    with pytest.raises(ReplayDataError, match="entry_must_be_strictly_after_signal"):
        OptionIntent(
            strategy_id="x",
            underlying="NIFTY",
            signal_timestamp=signal,
            earliest_entry_timestamp=signal,
            direction="BUY_CALL",
            option_type="CE",
            underlying_price=21400,
        )


def test_resolves_nearest_non_expired_atm_contract() -> None:
    selected = resolve_contract(_intent(), [_contract(21350), _contract(21400), _contract(21450)])
    assert selected.strike == 21450


def test_inventory_rejects_empty_raw_response(tmp_path: Path) -> None:
    base = tmp_path / "raw" / "responses" / "NIFTY" / "expiry=2026-07-14"
    base.mkdir(parents=True)
    contract = {
        "underlying_symbol": "NIFTY",
        "expiry": "2026-07-14",
        "instrument_type": "CE",
        "instrument_key": "NSE_FO|51203|14-07-2026",
        "trading_symbol": "NIFTY 21400 CE 14 JUL 26",
        "strike_price": 21400.0,
        "lot_size": 65,
    }
    (base / "contracts.json").write_text(json.dumps({"data": [contract]}), encoding="utf-8")
    candle_dir = base / "instrument=NSE_FO_51203_14-07-2026"
    candle_dir.mkdir()
    (candle_dir / "candles_1minute.json").write_text(json.dumps({"data": {"candles": []}}), encoding="utf-8")
    assert build_contract_inventory(tmp_path) == ()


def test_replay_uses_next_legal_bar_and_real_option_prices(tmp_path: Path) -> None:
    contract = _contract(21400)
    path = tmp_path / contract.raw_candle_path
    candles = [
        ["2026-07-14T10:00:00+05:30", 100, 102, 99, 101, 10, 1000],
        ["2026-07-14T10:01:00+05:30", 103, 110, 102, 109, 12, 1000],
        ["2026-07-14T10:02:00+05:30", 109, 145, 108, 140, 15, 1000],
    ]
    path.write_text(json.dumps({"data": {"candles": candles}}), encoding="utf-8")
    trade = replay_intent(_intent(price=21400), tmp_path, [contract], partition="development")
    assert trade.entry_timestamp.startswith("2026-07-14 10:01:00")
    assert trade.entry_price == 103
    assert trade.exit_reason == "target"
    assert trade.net_pnl > 0
    assert trade.authority == "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE"


def test_chronological_wfa_keeps_holdout_separate() -> None:
    intents = [_intent(day=day) for day in (10, 11, 12, 13, 14)]
    split = chronological_partitions(intents)
    assert split["development"].isdisjoint(split["validation"])
    assert split["development"].isdisjoint(split["holdout"])
    assert split["validation"].isdisjoint(split["holdout"])
    assert max(split["development"]) < min(split["holdout"])


def test_metrics_empty_are_truthful() -> None:
    result = metrics([])
    assert result["trades"] == 0
    assert result["profit_factor"] is None
    assert result["expectancy"] is None
