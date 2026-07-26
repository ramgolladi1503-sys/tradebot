from __future__ import annotations

import pandas as pd

from scripts.run_kite_underlying_directional_edge_campaign import (
    audit_corpus,
    build_partitions,
    generate_signals,
    run_campaign,
    _controls,
    _intent_rows,
    _simulate_signal,
)


def _bars(start: str = "2026-07-01 09:15:00+05:30", rows: int = 40, *, mock: bool = False):
    ts = pd.date_range(start, periods=rows, freq="5min")
    out = []
    price = 100.0
    for i, stamp in enumerate(ts):
        price += 0.2
        close = price + (2 if i == 21 else 0)
        out.append({"date": stamp, "open": price, "high": max(price, close) + 1, "low": min(price, close) - 1, "close": close, "volume": 1, "instrument": "NIFTY", "instrument_token": 1, "interval": "5minute", "source": "kite", "synthetic": False, "fallback": False, "mock": mock, "fetch_date": "2026-07-01"})
    return out


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path)


def test_five_minute_files_are_not_labelled_one_minute(tmp_path) -> None:
    root = tmp_path / "kite"
    _write(root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet", _bars())
    _, by_file, _, _ = audit_corpus(root)
    assert by_file[0]["bar_interval"] == "5minute"
    assert by_file[0]["authority_classification"] == "REAL_KITE_UNDERLYING_CANDLES"


def test_synthetic_fallback_mock_rows_are_excluded(tmp_path) -> None:
    root = tmp_path / "kite"
    _write(root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet", _bars(mock=True))
    sessions, by_file, _, rejected = audit_corpus(root)
    assert sessions == {}
    assert by_file[0]["authority_classification"] == "SYNTHETIC_OR_MOCK_ONLY"
    assert rejected["mock_true_rows"] == 40


def test_actual_files_drive_session_partitions(tmp_path) -> None:
    root = tmp_path / "kite"
    for day in ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]:
        _write(root / day / "underlying" / f"NIFTY_{day}.parquet", _bars(day + " 09:15:00+05:30"))
    sessions, _, _, _ = audit_corpus(root)
    partition = build_partitions(sessions)
    assert partition["indexes"]["NIFTY"]["session_count"] == 5
    assert partition["indexes"]["NIFTY"]["holdout_dates"]
    assert partition["holdout_outcomes_read"] is False


def test_no_same_bar_entry_and_future_mutation_does_not_alter_signal() -> None:
    df = pd.DataFrame(_bars())
    df["timestamp"] = pd.to_datetime(df["date"])
    signals = generate_signals("LATE_DAY_MOMENTUM", df, "2026-07-01", "NIFTY")
    first = signals[0]
    mutated = df.copy()
    mutated.loc[first["signal_bar_index"] + 2 :, "close"] = 9999
    assert first == generate_signals("LATE_DAY_MOMENTUM", mutated, "2026-07-01", "NIFTY")[0]
    trade = _simulate_signal(first, df, "development")
    assert trade is not None
    assert trade["entry_timestamp"] > first["signal_timestamp"]


def test_directional_pnl_is_not_labelled_option_pnl_and_intents_map_ce_pe() -> None:
    bull = {"strategy_id": "SIMPLE_ORB", "index": "NIFTY", "direction": "bullish", "signal_price": 101.0, "signal_timestamp": "2026-07-01 09:30:00+05:30", "entry_timestamp": "2026-07-01 09:35:00+05:30", "signal_identity_hash": "a", "partition": "validation"}
    bear = {**bull, "direction": "bearish", "signal_identity_hash": "b"}
    rows = _intent_rows([bull, bear], {("SIMPLE_ORB", "NIFTY")})
    assert {row["intended_option_type"] for row in rows} == {"CE", "PE"}
    assert {row["status"] for row in rows} == {"OPTION_INTENT_ONLY_NO_PREMIUM_PNL"}
    assert rows[0]["intended_ATM_strike"] == 100


def test_negative_controls_are_deterministic() -> None:
    trades = [{"net_points": 1.0}, {"net_points": -0.5}, {"net_points": 0.2}]
    assert _controls("SIMPLE_ORB", "NIFTY", trades) == _controls("SIMPLE_ORB", "NIFTY", trades)


def test_campaign_does_not_generate_option_pf_without_contract_authority(tmp_path) -> None:
    root = tmp_path / "kite"
    for day in ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]:
        _write(root / day / "underlying" / f"NIFTY_{day}.parquet", _bars(day + " 09:15:00+05:30"))
    out = tmp_path / "out"
    manifest = run_campaign(root, out)
    assert not (out / "targeted_option_pf_results.csv").exists()
    assert manifest["allowed_for_live_execution"] is False
    assert manifest["holdout_outcomes_read"] is False
