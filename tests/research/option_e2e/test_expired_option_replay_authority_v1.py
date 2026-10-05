from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    Contract,
    OptionIntent,
    ReplayDataError,
    ReplayTrade,
    build_contract_inventory,
    build_contract_universe,
    replay_intent,
    resolve_contract,
    resolve_expiry,
)
from scripts.run_expired_option_contract_replay_v1 import _read_intents, _wfa_rows

IST = ZoneInfo("Asia/Kolkata")


def _intent(*, partition: str = "validation", price: float = 21400) -> OptionIntent:
    signal = datetime(2026, 7, 14, 10, 0, tzinfo=IST)
    return OptionIntent(
        strategy_id="OPENING_DRIVE",
        underlying="NIFTY",
        signal_timestamp=signal,
        earliest_entry_timestamp=signal + timedelta(minutes=1),
        direction="BUY_CALL",
        option_type="CE",
        underlying_price=price,
        signal_identity_hash="signal",
        partition=partition,
    )


def _contract(
    *,
    expiry: date = date(2026, 7, 16),
    strike: float = 21400,
    sessions: tuple[date, ...] = (date(2026, 7, 14),),
    candle_path: str = "candles.json",
) -> Contract:
    return Contract(
        underlying="NIFTY",
        expiry=expiry,
        option_type="CE",
        strike=strike,
        instrument_key=f"NSE_FO|{int(strike)}|{expiry}",
        trading_symbol="NIFTY CE",
        lot_size=65,
        raw_contract_path="contracts.json",
        raw_candle_path=candle_path,
        session_dates=sessions,
    )


def test_true_nearest_expiry_is_resolved_before_candle_coverage() -> None:
    nearest_metadata_only = _contract(
        expiry=date(2026, 7, 16), sessions=(), candle_path=""
    )
    later_with_candles = _contract(expiry=date(2026, 7, 23))
    assert resolve_expiry(_intent(), [nearest_metadata_only, later_with_candles]) == date(
        2026, 7, 16
    )
    with pytest.raises(
        ReplayDataError, match="nearest_expiry_has_no_same_session_price_authority"
    ):
        resolve_contract(
            _intent(),
            [later_with_candles],
            contract_universe=[nearest_metadata_only, later_with_candles],
        )


def test_expiry_universe_gap_over_seven_days_is_rejected() -> None:
    with pytest.raises(ReplayDataError, match="nearest_expiry_universe_gap_exceeds_7_days"):
        resolve_expiry(
            _intent(),
            [_contract(expiry=date(2026, 7, 30), sessions=(), candle_path="")],
        )


def test_contract_resolution_requires_signal_day_coverage() -> None:
    with pytest.raises(
        ReplayDataError, match="nearest_expiry_has_no_same_session_price_authority"
    ):
        resolve_contract(
            _intent(),
            [_contract(sessions=(date(2026, 7, 15),))],
        )


def test_replay_cannot_enter_on_a_later_trading_day(tmp_path: Path) -> None:
    contract = _contract()
    (tmp_path / contract.raw_candle_path).write_text(
        json.dumps(
            {
                "data": {
                    "candles": [
                        ["2026-07-15T10:01:00+05:30", 100, 101, 99, 100, 1, 1]
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ReplayDataError, match="selected_contract_has_no_same_session_candles"
    ):
        replay_intent(_intent(), tmp_path, [contract], partition="validation")


def test_universe_keeps_metadata_without_candle_authority(tmp_path: Path) -> None:
    expiry_root = tmp_path / "raw" / "responses" / "NIFTY" / "expiry=2026-07-16"
    expiry_root.mkdir(parents=True)
    contract_row = {
        "underlying_symbol": "NIFTY",
        "expiry": "2026-07-16",
        "instrument_type": "CE",
        "instrument_key": "NSE_FO|1",
        "trading_symbol": "NIFTY 21400 CE",
        "strike_price": 21400,
        "lot_size": 65,
    }
    (expiry_root / "contracts.json").write_text(
        json.dumps({"data": [contract_row]}), encoding="utf-8"
    )
    universe = build_contract_universe(tmp_path)
    inventory = build_contract_inventory(tmp_path)
    assert len(universe) == 1
    assert universe[0].has_price_authority is False
    assert inventory == ()


def test_inventory_freezes_actual_contract_session_dates(tmp_path: Path) -> None:
    expiry_root = tmp_path / "raw" / "responses" / "NIFTY" / "expiry=2026-07-16"
    expiry_root.mkdir(parents=True)
    contract_row = {
        "underlying_symbol": "NIFTY",
        "expiry": "2026-07-16",
        "instrument_type": "CE",
        "instrument_key": "NSE_FO|1",
        "trading_symbol": "NIFTY 21400 CE",
        "strike_price": 21400,
        "lot_size": 65,
    }
    (expiry_root / "contracts.json").write_text(
        json.dumps({"data": [contract_row]}), encoding="utf-8"
    )
    candle_root = expiry_root / "instrument=NSE_FO_1_16-07-2026"
    candle_root.mkdir()
    (candle_root / "candles_1minute.json").write_text(
        json.dumps(
            {
                "data": {
                    "candles": [
                        ["2026-07-14T10:00:00+05:30", 100, 101, 99, 100, 1, 1],
                        ["2026-07-15T10:00:00+05:30", 110, 111, 109, 110, 1, 1],
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    inventory = build_contract_inventory(tmp_path)
    assert len(inventory) == 1
    assert inventory[0].session_dates == (
        date(2026, 7, 14),
        date(2026, 7, 15),
    )


def test_csv_partition_is_preserved_as_authority(tmp_path: Path) -> None:
    path = tmp_path / "intents.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "strategy_id",
                "underlying",
                "signal_timestamp",
                "earliest_entry_timestamp",
                "direction",
                "signal_time_underlying_price",
                "intended_option_type",
                "partition",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "strategy_id": "OPENING_DRIVE",
                "underlying": "NIFTY",
                "signal_timestamp": "2026-07-14T10:00:00+05:30",
                "earliest_entry_timestamp": "2026-07-14T10:01:00+05:30",
                "direction": "BUY_CALL",
                "signal_time_underlying_price": 21400,
                "intended_option_type": "CE",
                "partition": "validation",
            }
        )
    intents = _read_intents(path)
    assert intents[0].partition == "validation"


def _trade(*, partition: str, pnl: float, minute: int) -> ReplayTrade:
    return ReplayTrade(
        strategy_id="OPENING_DRIVE",
        signal_identity_hash=f"{partition}-{minute}",
        signal_timestamp=f"2026-07-14 10:{minute:02d}:00+05:30",
        earliest_entry_timestamp=f"2026-07-14 10:{minute:02d}:30+05:30",
        signal_to_entry_seconds=60.0,
        earliest_entry_to_entry_seconds=30.0,
        underlying="NIFTY",
        underlying_price=21400,
        option_type="CE",
        expiry="2026-07-16",
        atm_strike=21400,
        strike=21400,
        strike_offset_steps=0,
        strike_distance_points=0,
        instrument_key="NSE_FO|1",
        entry_timestamp=f"2026-07-14 10:{minute:02d}:00+05:30",
        entry_price=100,
        exit_timestamp=f"2026-07-14 10:{minute + 1:02d}:00+05:30",
        exit_price=101 if pnl > 0 else 99,
        exit_reason="time_exit",
        quantity=1,
        unit_gross_pnl=pnl,
        unit_friction_cost=0,
        unit_net_pnl=pnl,
        gross_pnl=pnl,
        friction_cost=0,
        net_pnl=pnl,
        gross_return_pct=pnl,
        net_return_pct=pnl,
        return_pct=pnl,
        partition=partition,
    )


def test_wfa_requires_both_development_and_validation_samples() -> None:
    intents = [_intent(partition="development"), _intent()]
    trades = [
        _trade(partition="development", pnl=1.0, minute=1),
        _trade(partition="validation", pnl=1.0, minute=2),
    ]
    rows = _wfa_rows(intents, trades, minimum_partition_trades=2)
    assert rows[0]["verdict"] == "INSUFFICIENT_OPTION_TRANSLATION_SAMPLE"
    assert rows[0]["holdout_profit_factor"] == "SEALED"
