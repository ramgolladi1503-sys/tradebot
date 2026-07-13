from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import backtest_all_strategies_available_data as mod


def _sample_data(path: Path) -> Path:
    rows = []
    for instrument, base in (("NIFTY", 100.0), ("BANKNIFTY", 200.0), ("SENSEX", 300.0), ("INDIAVIX", 12.0)):
        for i in range(40):
            rows.append(
                {
                    "date": pd.Timestamp("2026-06-29 09:15:00") + pd.Timedelta(minutes=i),
                    "open": base + i * 0.1,
                    "high": base + i * 0.1 + 0.2,
                    "low": base + i * 0.1 - 0.2,
                    "close": base + i * 0.1 + 0.05,
                    "volume": 0,
                    "instrument": instrument,
                }
            )
    df = pd.DataFrame(rows)
    df.to_parquet(path)
    return path


def test_schema_inspection_marks_zero_volume_vwap_partial(tmp_path: Path) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")

    dataset = mod.load_dataset(data_path)
    inspection = mod.inspect_dataset(dataset)
    matrix = mod.build_capability_matrix(inspection)

    assert inspection.volume_quality == "ZERO_VOLUME"
    vwap_rows = matrix[matrix["required_inputs"].str.contains("vwap", case=False, na=False)]
    assert not vwap_rows.empty
    assert "SUPPORTED_PROXY" not in set(vwap_rows["capability_bucket"])
    assert set(vwap_rows["test_mode"]).intersection({"PARTIAL_PROXY", "INVALID_VOLUME_PROXY", "SIGNAL_ONLY"})


def test_no_broker_api_called_by_harness(tmp_path: Path, monkeypatch) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")
    out_dir = tmp_path / "out"
    called = {"broker": False}

    def _broker_call(*_args, **_kwargs):
        called["broker"] = True
        raise AssertionError("broker should not be called")

    monkeypatch.setattr(mod, "_forbidden_broker_call_sentinel", _broker_call)

    result = mod.run_backtest(data_path=data_path, out_dir=out_dir, trade_date="2026-06-29")

    assert called["broker"] is False
    assert result["safety"]["broker_api_called"] is False
    assert result["safety"]["is_order_action"] is False


def test_unsupported_option_strategies_do_not_produce_pnl_claims(tmp_path: Path) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")
    out_dir = tmp_path / "out"

    mod.run_backtest(data_path=data_path, out_dir=out_dir, trade_date="2026-06-29")
    matrix = pd.read_csv(out_dir / "strategy_data_capability_matrix.csv")
    proxy = pd.read_csv(out_dir / "all_strategy_proxy_summary.csv")

    unsupported = set(matrix.loc[matrix["capability_bucket"] == "UNSUPPORTED_EXECUTABLE", "strategy"])
    assert unsupported
    assert unsupported.isdisjoint(set(proxy["strategy"]))


def test_fallback_advisory_signals_are_not_marked_executable(tmp_path: Path) -> None:
    signal = mod.normalize_signal(
        strategy="x",
        instrument="NIFTY",
        timestamp=pd.Timestamp("2026-06-29 09:15:00"),
        direction="BUY_CALL",
        score=0.1,
        reason="soft",
        advisory=True,
        fallback=True,
    )

    assert signal is not None
    assert signal.executable is False
    assert signal.signal_only is True


def test_strategy_error_is_captured_without_stopping_run(tmp_path: Path) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")
    out_dir = tmp_path / "out"

    result = mod.run_backtest(
        data_path=data_path,
        out_dir=out_dir,
        trade_date="2026-06-29",
        extra_strategies=[
            mod.StrategySpec(
                strategy="bad_strategy",
                module="tests",
                callable="boom",
                required_inputs=("close",),
                option_specific=False,
                volume_dependent=False,
                vwap_dependent=False,
                runner=lambda _market: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        ],
    )

    errors = pd.read_csv(out_dir / "strategy_errors.csv")
    assert result["error_count"] >= 1
    assert "bad_strategy" in set(errors["strategy"])
    assert (out_dir / "all_strategy_report_20260629.json").exists()


def test_orb_levels_do_not_use_future_opening_range_before_it_completes(tmp_path: Path) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")

    frames = mod._prepare_frames(mod.load_dataset(data_path))
    nifty = frames["NIFTY"]

    assert pd.isna(nifty.loc[0, "orb_high"])
    assert pd.isna(nifty.loc[14, "orb_high"])
    assert nifty.loc[15, "orb_high"] == nifty.loc[:14, "high"].max()
    assert nifty.loc[15, "orb_low"] == nifty.loc[:14, "low"].min()


def test_proxy_trade_uses_current_close_and_future_exit_without_option_pnl_claim(tmp_path: Path) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")
    frames = mod._prepare_frames(mod.load_dataset(data_path))
    idx_by_instrument = {
        instrument: {pd.Timestamp(row.date).isoformat(): int(idx) for idx, row in frame.iterrows()}
        for instrument, frame in frames.items()
    }
    signal = mod.normalize_signal(
        strategy="directional_proxy",
        instrument="NIFTY",
        timestamp=frames["NIFTY"].loc[5, "date"],
        direction="BUY_CALL",
    )

    rows = mod._proxy_trade_rows(signal, frames, idx_by_instrument)
    horizon_5_zero_cost = next(row for row in rows if row["exit_horizon_min"] == 5 and row["cost_bps"] == 0.0)

    assert horizon_5_zero_cost["entry_underlying"] == frames["NIFTY"].loc[5, "close"]
    assert horizon_5_zero_cost["exit_underlying"] == frames["NIFTY"].loc[10, "close"]
    assert horizon_5_zero_cost["executable"] is False
    assert horizon_5_zero_cost["verdict"] == mod.FINAL_VERDICT


def test_proxy_trade_rows_stay_within_the_same_session_and_do_not_jump_to_future_dates(tmp_path: Path) -> None:
    rows = []
    for ts, close in [
        ("2026-07-01 09:15:00", 100.0),
        ("2026-07-01 09:16:00", 101.0),
        ("2026-07-01 15:28:00", 110.0),
        ("2026-07-01 15:29:00", 111.0),
        ("2026-07-10 09:15:00", 200.0),
        ("2026-07-10 09:16:00", 201.0),
    ]:
        rows.append(
            {
                "date": pd.Timestamp(ts),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100,
                "instrument": "NIFTY",
            }
        )
    data_path = tmp_path / "session_gap.parquet"
    pd.DataFrame(rows).to_parquet(data_path)

    frames = mod._prepare_frames(mod.load_dataset(data_path))
    idx_by_instrument = {
        instrument: {pd.Timestamp(row.date).isoformat(): int(idx) for idx, row in frame.iterrows()}
        for instrument, frame in frames.items()
    }
    signal = mod.normalize_signal(
        strategy="directional_proxy",
        instrument="NIFTY",
        timestamp="2026-07-01 15:28:00",
        direction="BUY_CALL",
    )

    rows = mod._proxy_trade_rows(signal, frames, idx_by_instrument)
    horizon_15_zero_cost = next(row for row in rows if row["exit_horizon_min"] == 15 and row["cost_bps"] == 0.0)

    assert horizon_15_zero_cost["entry_timestamp"].startswith("2026-07-01T15:28:00")
    assert horizon_15_zero_cost["exit_timestamp"].startswith("2026-07-01T15:29:00")
    assert horizon_15_zero_cost["entry_session"] == "2026-07-01"
    assert horizon_15_zero_cost["exit_session"] == "2026-07-01"
    assert horizon_15_zero_cost["exit_underlying"] == frames["NIFTY"].loc[3, "close"]
    assert pd.Timestamp(horizon_15_zero_cost["exit_timestamp"]).date() == pd.Timestamp(horizon_15_zero_cost["entry_timestamp"]).date()


def test_proxy_trade_rows_reject_last_candle_without_any_same_session_forward_rows(tmp_path: Path) -> None:
    rows = []
    for ts, close in [
        ("2026-07-01 15:29:00", 111.0),
        ("2026-07-10 09:15:00", 200.0),
        ("2026-07-10 09:16:00", 201.0),
    ]:
        rows.append(
            {
                "date": pd.Timestamp(ts),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100,
                "instrument": "NIFTY",
            }
        )
    data_path = tmp_path / "last_candle.parquet"
    pd.DataFrame(rows).to_parquet(data_path)

    frames = mod._prepare_frames(mod.load_dataset(data_path))
    idx_by_instrument = {
        instrument: {pd.Timestamp(row.date).isoformat(): int(idx) for idx, row in frame.iterrows()}
        for instrument, frame in frames.items()
    }
    signal = mod.normalize_signal(
        strategy="directional_proxy",
        instrument="NIFTY",
        timestamp="2026-07-01 15:29:00",
        direction="BUY_CALL",
    )

    assert mod._proxy_trade_rows(signal, frames, idx_by_instrument) == []


def test_report_writer_does_not_require_optional_tabulate(tmp_path: Path, monkeypatch) -> None:
    data_path = _sample_data(tmp_path / "bars.parquet")
    out_dir = tmp_path / "out"

    def _missing_tabulate(*_args, **_kwargs):
        raise ImportError("tabulate is intentionally unavailable")

    monkeypatch.setattr(pd.DataFrame, "to_markdown", _missing_tabulate, raising=False)

    mod.run_backtest(data_path=data_path, out_dir=out_dir, trade_date="2026-06-29")

    report = (out_dir / "all_strategy_report_20260629.md").read_text(encoding="utf-8")
    assert "Final verdict" in report
    assert "NOT_EXECUTABLE_OPTION_BACKTEST" in report
