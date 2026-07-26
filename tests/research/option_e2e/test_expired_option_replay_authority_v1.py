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
    replay_intent,
    resolve_contract,
)
from scripts.run_expired_option_contract_replay_v1 import _read_intents, _wfa_rows

IST = ZoneInfo("Asia/Kolkata")


def _intent(*, partition: str = "validation") -> OptionIntent:
    signal = datetime(2026, 7, 14, 10, 0, tzinfo=IST)
    return OptionIntent(
        strategy_id="OPENING_DRIVE",
        underlying="NIFTY",
        signal_timestamp=signal,
        earliest_entry_timestamp=signal + timedelta(minutes=1),
        direction="BUY_CALL",
        option_type="CE",
        underlying_price=21400,
        signal_identity_hash="signal",
        partition=partition,
    )


def _contract(*, sessions: tuple[date, ...]) -> Contract:
    return Contract(
        underlying="NIFTY",
        expiry=date(2026, 7, 16),
        option_type="CE",
        strike=21400,
        instrument_key="NSE_FO|1",
        trading_symbol="NIFTY 21400 CE",
        lot_size=65,
        raw_contract_path="contracts.json",
        raw_candle_path="candles.json",
        session_dates=sessions,
    )


def test_contract_resolution_requires_signal_day_coverage() -> None:
    with pytest.raises(
        ReplayDataError, match="no_contract_with_same_session_price_authority"
    ):
        resolve_contract(
            _intent(),
            [_contract(sessions=(date(2026, 7, 15),))],
        )


def test_replay_cannot_enter_on_a_later_trading_day(tmp_path: Path) -> None:
    contract = _contract(sessions=(date(2026, 7, 14),))
    (tmp_path / contract.raw_candle_path).write_text(
        json.dumps(
            {
                "data": {
                    "candles": [
                        [
                            "2026-07-15T10:01:00+05:30",
                            100,
                            101,
                            99,
                            100,
                            1,
                            1,
                        ]
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ReplayDataError, match="selected_contract_has_no_same_session_candles"
    ):
        replay_intent(
            _intent(),
            tmp_path,
            [contract],
            partition="validation",
        )


def test_inventory_freezes_actual_contract_session_dates(tmp_path: Path) -> None:
    expiry_root = (
        tmp_path / "raw" / "responses" / "NIFTY" / "expiry=2026-07-16"
    )
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
                        [
                            "2026-07-14T10:00:00+05:30",
                            100,
                            101,
                            99,
                            100,
                            1,
                            1,
                        ],
                        [
                            "2026-07-15T10:00:00+05:30",
                            110,
                            111,
                            109,
                            110,
                            1,
                            1,
                        ],
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
        underlying="NIFTY",
        option_type="CE",
        expiry="2026-07-16",
        strike=21400,
        instrument_key="NSE_FO|1",
        entry_timestamp=f"2026-07-14 10:{minute:02d}:00+05:30",
        entry_price=100,
        exit_timestamp=f"2026-07-14 10:{minute + 1:02d}:00+05:30",
        exit_price=101 if pnl > 0 else 99,
        exit_reason="time_exit",
        quantity=1,
        gross_pnl=pnl,
        friction_cost=0,
        net_pnl=pnl,
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
    assert rows[0]["verdict"] == "INSUFFICIENT_MATCHED_TRADES_FOR_WFA"
    assert rows[0]["holdout_profit_factor"] == "SEALED"
