from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import json

import pandas as pd
import pytest

from core.option_backtest import (
    OptionBacktestConfig,
    OptionReplayWFAConfig,
    OptionReplayWFAGates,
    OptionReplayWFARange,
    build_wfa_partition_plan,
    run_option_replay_wfa,
)
from core.option_backtest.models import OptionBacktestResult, ResearchMode
import core.option_backtest.wfa as wfa_module


def _wfa_row(ts: str, **overrides):
    row = {
        "timestamp": ts,
        "symbol": "NIFTY24APR25500CE",
        "open": 100.0,
        "high": 101.0,
        "low": 99.5,
        "close": 100.5,
        "volume": 500,
        "oi": 900,
        "bid": 100.0,
        "ask": 100.5,
        "bid_qty": 50,
        "ask_qty": 50,
        "underlying": "NIFTY",
        "option_type": "CE",
        "strike": 25500,
        "expiry": "2026-04-30",
        "provider": "upstox",
        "dataset_hash": "hash-1",
        "bar_interval": "1m",
        "quote_timestamp": (pd.Timestamp(ts) - pd.Timedelta(seconds=20)).strftime("%Y-%m-%d %H:%M:%S"),
        "feature_cutoff_ts": ts,
        "signal_ts": ts,
        "earliest_entry_ts": (pd.Timestamp(ts) + pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "signal_score": 0.92,
        "selected_for_execution": True,
        "target_price": 103.0,
        "stop_price": 98.0,
        "setup_id": "breakout",
        "regime": "trend",
        "is_oos": False,
    }
    row.update(overrides)
    return row


def _strict_base_config(path: Path) -> OptionBacktestConfig:
    return OptionBacktestConfig(
        symbol="NIFTY24APR25500CE",
        data_path=path,
        research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
        allow_derived_levels=False,
        fill_model_run_id="wfa",
    )


def _make_wfa_csv(path: Path) -> None:
    rows = [
        _wfa_row("2026-04-01 09:15:00"),
        _wfa_row("2026-04-01 09:16:00", selected_for_execution=False, signal_score=0.20, open=100.5, high=101.2, low=100.0, close=100.4, bid=100.2, ask=100.5),
        _wfa_row("2026-04-01 09:17:00", selected_for_execution=False, signal_score=0.10, open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1),
        _wfa_row("2026-04-02 09:15:00"),
        _wfa_row("2026-04-02 09:16:00", selected_for_execution=False, signal_score=0.20, open=100.5, high=101.2, low=100.0, close=100.4, bid=100.2, ask=100.5),
        _wfa_row("2026-04-02 09:17:00", selected_for_execution=False, signal_score=0.10, open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1),
        _wfa_row("2026-04-03 09:15:00"),
        _wfa_row("2026-04-03 09:16:00", selected_for_execution=False, signal_score=0.20, open=100.5, high=101.2, low=100.0, close=100.4, bid=100.2, ask=100.5, is_oos=True),
        _wfa_row("2026-04-03 09:17:00", selected_for_execution=False, signal_score=0.10, open=101.8, high=103.5, low=101.6, close=103.0, bid=102.8, ask=103.1, is_oos=True),
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def _wfa_cfg(path: Path, output_dir: Path) -> OptionReplayWFAConfig:
    return OptionReplayWFAConfig(
        base_config=_strict_base_config(path),
        train_range=OptionReplayWFARange(start="2026-04-01 09:15:00", end="2026-04-01 09:17:00"),
        validation_range=OptionReplayWFARange(start="2026-04-02 09:15:00", end="2026-04-02 09:17:00"),
        holdout_range=OptionReplayWFARange(start="2026-04-03 09:15:00", end="2026-04-03 09:17:00"),
        gates=OptionReplayWFAGates(
            min_trades=1,
            min_net_expectancy=0.1,
            min_profit_factor=1.0,
            max_drawdown=10.0,
            max_ambiguity_count=0,
            max_contamination_count=0,
            min_positive_partition_fraction=1.0,
        ),
        output_dir=output_dir,
    )


def _fake_result(*, trades_taken: int = 1, expectancy: float = 1.0, profit_factor: float | None = 2.0, drawdown: float = 0.5, result_label: str = "CERTIFICATION_CANDIDATE", certifiable: bool = True, blockers: list[str] | None = None, net_pnl: float = 1.0) -> OptionBacktestResult:
    summary = {
        "signals_total": 3,
        "trades_taken": trades_taken,
        "after_cost_expectancy": expectancy,
        "profit_factor": profit_factor,
        "profit_factor_unbounded": False,
        "wins": 1 if net_pnl > 0 else 0,
        "losses": 0 if net_pnl > 0 else 1,
        "max_drawdown": drawdown,
        "ambiguity_count": 0,
        "diagnostics": {
            "fallback_rows": 0,
            "derived_geometry_rows": 0,
            "derived_timing_rows": 0,
            "proxy_exit_mark_rows": 0,
            "strict_exit_quote_rejections": 0,
            "timing_ambiguity_count": 0,
        },
        "setup_breakdown": {"breakout": {"trades": trades_taken, "pnl": net_pnl}},
        "regime_breakdown": {"trend": {"trades": trades_taken, "pnl": net_pnl}},
        "result_label": result_label,
        "certifiable": certifiable,
        "certification_blockers": blockers or [],
        "net_pnl_value": net_pnl,
    }
    return OptionBacktestResult(config=_strict_base_config(Path("/tmp/fake.csv")), summary=summary, trades=[], diagnostics=summary["diagnostics"], sampled_decisions=[])


def test_wfa_partition_plan_is_chronological_and_non_overlapping(tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    plan = build_wfa_partition_plan(_wfa_cfg(data_path, tmp_path / "out"))
    assert plan["partitions"]["train"]["raw_end"] < plan["partitions"]["validation"]["raw_start"]
    assert plan["partitions"]["validation"]["raw_end"] < plan["partitions"]["holdout"]["raw_start"]


def test_wfa_partition_plan_applies_purge_and_embargo(tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    cfg = replace(
        _wfa_cfg(data_path, tmp_path / "out"),
        train_range=OptionReplayWFARange(start="2026-04-01 09:00:00", end="2026-04-01 10:00:00"),
        validation_range=OptionReplayWFARange(start="2026-04-01 10:20:00", end="2026-04-01 11:40:00"),
        holdout_range=OptionReplayWFARange(start="2026-04-01 12:30:00", end="2026-04-01 13:00:00"),
        max_feature_lookback_minutes=15,
    )
    plan = build_wfa_partition_plan(cfg)
    assert plan["effective_boundary_minutes"] == 45
    assert plan["partitions"]["train"]["effective_end"].endswith("09:35:00+05:30")
    assert plan["partitions"]["validation"]["effective_start"].endswith("10:45:00+05:30")
    assert plan["partitions"]["validation"]["effective_end"].endswith("11:40:00+05:30")


def test_legacy_wfa_purges_overlapping_training_rows_and_applies_embargo():
    from core.backtesting.wfa import WalkForwardAnalyzer

    index = pd.date_range("2024-12-31 15:25", periods=8, freq="min", tz="Asia/Kolkata").append(
        pd.date_range("2025-01-01 09:15", periods=4, freq="min", tz="Asia/Kolkata")
    )
    data = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index)
    analyzer = WalkForwardAnalyzer(data, train_years=1, test_years=1, label_horizon_minutes=60, embargo_minutes=2)
    window = analyzer.generate_windows()[0]
    assert window["train_df"].index.max() + pd.Timedelta(minutes=60) < window["raw_test_start"]
    assert window["test_df"].index.min() >= window["raw_test_start"] + pd.Timedelta(minutes=2)


def test_legacy_wfa_explicit_purge_contract_cannot_be_negative():
    from core.backtesting.wfa import WalkForwardAnalyzer

    data = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-01", tz="Asia/Kolkata")]),
    )
    with pytest.raises(ValueError, match="wfa_boundaries_must_be_nonnegative"):
        WalkForwardAnalyzer(data, purge_minutes=-1)


def test_legacy_wfa_exposes_fold_and_parameter_ledgers():
    from core.backtesting.wfa import WalkForwardAnalyzer

    index = pd.date_range("2024-01-01", periods=4, freq="D", tz="Asia/Kolkata").append(
        pd.date_range("2025-01-01", periods=4, freq="D", tz="Asia/Kolkata")
    ).append(pd.date_range("2026-01-01", periods=4, freq="D", tz="Asia/Kolkata"))
    data = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index)
    analyzer = WalkForwardAnalyzer(data, train_years=1, test_years=1)
    windows = analyzer.generate_windows()
    for i, window in enumerate(windows, start=1):
        analyzer.parameter_freeze_ledger.append({
            "fold_id": i,
            "parameter_selection_data_end": str(window["train_df"].index.max()),
            "parameter_freeze_time": str(window["train_df"].index.max()),
            "test_start": str(window["test_df"].index.min()),
        })
        analyzer.fold_ledger.append({"fold_id": i, "overlap_rows": 0})
    assert len(analyzer.fold_ledger) == len(windows)
    assert all(row["overlap_rows"] == 0 for row in analyzer.fold_ledger)
    assert all(pd.Timestamp(row["parameter_selection_data_end"]) < pd.Timestamp(row["test_start"]) for row in analyzer.parameter_freeze_ledger)


def test_legacy_wfa_session_aggregation_and_uncertainty_are_deterministic():
    from core.backtesting.wfa import WalkForwardAnalyzer

    results = pd.DataFrame({"pl": [100.0, 100.0, -50.0], "session_date": ["A", "A", "B"]})
    aggregate = WalkForwardAnalyzer._session_aggregate(results)
    assert aggregate == {
        "event_count": 3,
        "session_count": 2,
        "event_mean": 50.0,
        "session_equal_mean": 25.0,
        "positive_fraction": 2 / 3,
    }
    first = WalkForwardAnalyzer._session_bootstrap(results, repetitions=20, seed=7)
    second = WalkForwardAnalyzer._session_bootstrap(results, repetitions=20, seed=7)
    assert first == second
    assert first["unit"] == "session"
    assert first["statistic"] == "session_equal_mean"


def test_legacy_wfa_accepts_independent_signal_builder_seam():
    from core.backtesting.wfa import WalkForwardAnalyzer

    index = pd.date_range("2024-01-01", periods=3, freq="D", tz="Asia/Kolkata").append(
        pd.date_range("2025-01-01", periods=3, freq="D", tz="Asia/Kolkata")
    )
    data = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=index)
    calls = []

    def builder(frame, config):
        calls.append(len(frame))
        return pd.DataFrame({
            "signal_side": ["BUY"], "entry_price": [100.0], "target": [100.5],
            "stop_loss": [99.5], "qty": [1], "lot_size": [1],
        }, index=[0])

    analyzer = WalkForwardAnalyzer(data, train_years=1, test_years=1, signal_builder=builder)
    analyzer.run({"horizon": [1]})
    assert calls == [3, 3]


def test_parameter_selection_records_train_only_candidate_provenance():
    from core.backtesting.wfa import WalkForwardAnalyzer

    index = pd.date_range("2024-01-01", periods=3, freq="D", tz="Asia/Kolkata").append(
        pd.date_range("2025-01-01", periods=3, freq="D", tz="Asia/Kolkata")
    )
    data = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=index,
    )

    def builder(frame, config):
        return pd.DataFrame({
            "signal_side": ["BUY"], "entry_price": [100.0], "target": [200.0],
            "stop_loss": [50.0], "qty": [1], "lot_size": [1],
        }, index=[0])

    analyzer = WalkForwardAnalyzer(
        data, train_years=1, test_years=1, signal_builder=builder,
        purge_minutes=0, embargo_minutes=0,
    )
    analyzer.run({"horizon": [1, 2]})
    assert len(analyzer.parameter_selection_ledger) == 1
    row = analyzer.parameter_selection_ledger[0]
    assert row["selection_source"] == "TRAIN_ONLY"
    assert len(row["candidate_scores"]) == 2
    assert row["candidate_ledger_sha256"]
    assert all(
        pd.Timestamp(candidate["selection_data_end"]) < pd.Timestamp(row["test_start"])
        for candidate in row["candidate_scores"]
    )


def test_legacy_wfa_producer_ledgers_fail_closed_under_mutation():
    from core.backtesting.wfa import (
        validate_feature_causality_ledger,
        validate_fold_ledger,
        validate_parameter_freeze_ledger,
        validate_parameter_selection_ledger,
    )

    fold = [{
        "train_start": "2025-01-01T09:15:00+05:30",
        "train_end": "2025-01-01T09:17:00+05:30",
        "test_start": "2025-01-01T09:18:00+05:30",
        "test_end": "2025-01-01T09:20:00+05:30",
        "overlap_rows": 0,
        "purge_interval": "0 days",
        "embargo_interval": "0 days",
    }]
    assert validate_fold_ledger(fold)
    mutated_fold = [dict(fold[0], overlap_rows=1)]
    with pytest.raises(ValueError, match="wfa_fold_ledger_overlap"):
        validate_fold_ledger(mutated_fold)

    feature = [{
        "feature_name": "test_feature",
        "feature_source_start_timestamp": "2025-01-01T09:15:00+05:30",
        "feature_source_end_timestamp": "2025-01-01T09:15:00+05:30",
        "decision_timestamp": "2025-01-01T09:15:00+05:30",
        "feature_source_timestamp": "2025-01-01T09:15:00+05:30",
        "feature_cutoff_ts": "2025-01-01T09:15:00+05:30",
        "session_id": "2025-01-01",
        "fold_id": 1,
        "available_at_decision": True,
        "feature_builder_sha256": "builder-hash",
        "feature_builder_id": "builder-v1",
        "source_partition_sha256": "source-hash",
        "corpus_freeze_sha256": "corpus-hash",
        "normalization_fit_scope": "TRAIN_ONLY",
        "normalization_fit_start": "2024-01-01T09:15:00+05:30",
        "normalization_fit_end": "2024-12-31T15:29:00+05:30",
        "normalization_fit_fold_id": 1,
        "normalization_fit_source_sha256": "source-hash",
        "fit_uses_test_data": False,
        "leakage_detected": False,
    }]
    assert validate_feature_causality_ledger(feature)
    with pytest.raises(ValueError, match="wfa_feature_causality_violation"):
        validate_feature_causality_ledger([dict(feature[0], feature_source_end_timestamp="2025-01-01T09:16:00+05:30")])

    parameter = [{
        "parameter_selection_data_end": "2025-01-01T09:15:00+05:30",
        "test_start": "2025-01-01T09:16:00+05:30",
    }]
    assert validate_parameter_freeze_ledger(parameter)
    with pytest.raises(ValueError, match="wfa_parameter_freeze_violation"):
        validate_parameter_freeze_ledger([dict(parameter[0], parameter_selection_data_end="2025-01-01T09:17:00+05:30")])

    selection = [{
        "selection_data_end": "2025-01-01T09:17:00+05:30",
        "test_start": "2025-01-02T09:15:00+05:30",
        "selected_parameters": {"horizon": 1},
        "candidate_scores": [{"parameters": {"horizon": 1}, "train_net_pl": 1.0,
                              "selection_data_end": "2025-01-01T09:17:00+05:30"}],
        "candidate_ledger_sha256": "",
        "selection_source": "TRAIN_ONLY",
    }]
    selection[0]["candidate_ledger_sha256"] = hashlib.sha256(
        json.dumps(selection[0]["candidate_scores"], sort_keys=True, default=str).encode()
    ).hexdigest()
    assert validate_parameter_selection_ledger(selection)
    with pytest.raises(ValueError, match="wfa_parameter_selection_test_leakage"):
        validate_parameter_selection_ledger([dict(selection[0], test_start="2025-01-01T09:17:00+05:30")])


def test_wfa_uses_option_backtest_engine_only(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    calls: list[str] = []

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            calls.append(f"{self.cfg.date_from}|{self.cfg.date_to}")
            return _fake_result()

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert calls == [
        "2026-04-01T09:15:00+05:30|2026-04-01T09:17:00+05:30",
        "2026-04-02T09:15:00+05:30|2026-04-02T09:17:00+05:30",
        "2026-04-03T09:15:00+05:30|2026-04-03T09:17:00+05:30",
    ]
    assert report["engine"] == "OptionBacktestEngine"
    assert report["engine_module"] == "core.option_backtest.engine.OptionBacktestEngine"


def test_wfa_missing_metrics_fail_closed(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            return _fake_result(profit_factor=None)

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["verdict"] == "FAILED"
    assert any(g["gate"] == "min_profit_factor" and g["missing"] for g in report["gates"]["validation"])


def test_wfa_insufficient_trades_fail_closed(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            return _fake_result(trades_taken=0)

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["verdict"] == "FAILED"
    assert any(g["gate"] == "min_trades" and not g["passed"] for g in report["gates"]["validation"])


def test_wfa_unknown_setup_regime_oos_fails_certification(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            return _fake_result(result_label="OPTION_REPLAY_RESEARCH", certifiable=False, blockers=["unknown_setup_id"])

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["verdict"] == "FAILED"
    assert any(g["gate"] == "require_known_setup_regime_oos" and not g["passed"] for g in report["gates"]["validation"])


def test_wfa_hardcoded_pass_behavior_is_impossible(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            return _fake_result(trades_taken=0, expectancy=-1.0, profit_factor=None, drawdown=100.0, result_label="PROXY_RESEARCH_ONLY", certifiable=False, blockers=["missing_setup_id_column"], net_pnl=-1.0)

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["verdict"] != "PASSED_OPTION_REPLAY_CERTIFICATION"


def test_wfa_failed_validation_prevents_holdout_certification(monkeypatch, tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    calls: list[str] = []

    class FakeEngine:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self):
            calls.append(str(self.cfg.date_from))
            if len(calls) == 2:
                return _fake_result(expectancy=-1.0, net_pnl=-1.0)
            return _fake_result()

    monkeypatch.setattr(wfa_module, "OptionBacktestEngine", FakeEngine)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert calls == [
        "2026-04-01T09:15:00+05:30",
        "2026-04-02T09:15:00+05:30",
    ]
    assert report["partitions"]["holdout"]["status"] == "skipped_validation_failed"
    assert report["verdict"] == "FAILED"


def test_wfa_final_holdout_pass_requires_all_gates(tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["verdict"] == "PASSED_OPTION_REPLAY_CERTIFICATION"
    assert report["partitions"]["validation"]["metrics"]["result_label"] == "CERTIFICATION_CANDIDATE"
    assert report["partitions"]["holdout"]["metrics"]["result_label"] == "CERTIFICATION_CANDIDATE"


def test_wfa_report_safety_flags_are_false_for_live_execution(tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    report = run_option_replay_wfa(_wfa_cfg(data_path, tmp_path / "out"))
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False
    assert report["allowed_for_live_execution"] is False


def test_wfa_repeated_holdout_run_is_blocked(tmp_path: Path):
    data_path = tmp_path / "wfa.csv"
    _make_wfa_csv(data_path)
    cfg = _wfa_cfg(data_path, tmp_path / "out")
    first = run_option_replay_wfa(cfg)
    second = run_option_replay_wfa(cfg)
    assert first["verdict"] == "PASSED_OPTION_REPLAY_CERTIFICATION"
    assert second["verdict"] == "BLOCKED"
    assert second["holdout_tracking"]["repeated_holdout_run"] is True
