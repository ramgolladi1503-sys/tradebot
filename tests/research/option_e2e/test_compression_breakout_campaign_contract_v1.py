"""Synthetic fixture contract tests; not market-performance evidence."""

from __future__ import annotations

import pandas as pd
import pytest

from research.option_e2e_recertification_v4.compression_breakout_option_campaign_v1 import (
    CompressionCampaignConfig,
    CompressionLedgerConfig,
    build_chronological_split_manifest,
    build_compression_signal_ledger,
    run_compression_campaign,
)


def _fixture_session(
    session_date: str,
    *,
    direction: str = "BULLISH",
    volume: float = 1000.0,
) -> pd.DataFrame:
    start = pd.Timestamp(f"{session_date}T09:15:00+05:30")
    rows: list[dict[str, object]] = []
    for index in range(30):
        centre = 100.0
        half_range = 0.30 if index < 25 else 0.05
        close = centre + (0.01 if index % 2 == 0 else -0.01)
        rows.append(
            {
                "timestamp": start + pd.Timedelta(minutes=index),
                "symbol": "NIFTY",
                "open": centre,
                "high": centre + half_range,
                "low": centre - half_range,
                "close": close,
                "volume": volume,
            }
        )
    if direction == "BULLISH":
        opened, high, low, close = 100.4, 101.2, 100.35, 101.0
    else:
        opened, high, low, close = 99.6, 99.65, 98.8, 99.0
    rows.extend(
        [
            {
                "timestamp": start + pd.Timedelta(minutes=30),
                "symbol": "NIFTY",
                "open": opened,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            {
                "timestamp": start + pd.Timedelta(minutes=31),
                "symbol": "NIFTY",
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": volume,
            },
        ]
    )
    return pd.DataFrame(rows)


def _fixture_sessions(count: int) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=count)
    return pd.concat(
        [_fixture_session(day.date().isoformat()) for day in dates],
        ignore_index=True,
    )


def test_fixture_signal_contract_maps_call_and_put_directions() -> None:
    call_result = build_compression_signal_ledger(
        _fixture_session("2026-07-14"), source_dataset_hash="fixture-source"
    )
    put_result = build_compression_signal_ledger(
        _fixture_session("2026-07-14", direction="BEARISH"),
        source_dataset_hash="fixture-source",
    )

    call_signal = call_result.signals.iloc[0]
    put_signal = put_result.signals.iloc[0]
    assert call_signal["strategy_id"] == "compression_breakout_v1"
    assert call_signal["direction"] == "BULLISH"
    assert call_signal["candidate_direction"] == "BUY_CALL"
    assert put_signal["direction"] == "BEARISH"
    assert put_signal["candidate_direction"] == "BUY_PUT"
    assert call_signal["signal_ts"].startswith("2026-07-14T09:45:00")
    assert call_signal["feature_cutoff_ts"].startswith("2026-07-14T09:46:00")
    assert call_signal["earliest_entry_ts"] == call_signal["feature_cutoff_ts"]
    assert call_result.summary["outcomes_read"] is False
    assert call_result.summary["option_prices_read"] is False


def test_fixture_later_bar_change_preserves_earlier_rows_and_schema_boundary() -> None:
    baseline = _fixture_session("2026-07-14")
    changed = baseline.copy()
    changed.loc[changed.index[-1], ["open", "high", "low", "close"]] = [
        120.0,
        121.0,
        119.0,
        120.0,
    ]

    first = build_compression_signal_ledger(
        baseline, source_dataset_hash="fixture-source"
    )
    second = build_compression_signal_ledger(
        changed, source_dataset_hash="fixture-source"
    )
    cutoff = "2026-07-14T09:45:00+05:30"
    first_rows = first.signals.loc[first.signals["signal_ts"] <= cutoff]
    second_rows = second.signals.loc[second.signals["signal_ts"] <= cutoff]
    forbidden = ("outcome", "pnl", "future_return", "exit_price")

    assert first_rows.to_dict("records") == second_rows.to_dict("records")
    assert all(
        not any(token in str(column).lower() for token in forbidden)
        for column in first.signals.columns
    )


def test_fixture_vwap_authority_and_split_boundaries_are_explicit() -> None:
    proxy = build_compression_signal_ledger(
        _fixture_session("2026-07-14", volume=0.0),
        source_dataset_hash="fixture-source",
    )
    rejected = build_compression_signal_ledger(
        _fixture_session("2026-07-14", volume=0.0),
        config=CompressionLedgerConfig(allow_typical_price_vwap_proxy=False),
        source_dataset_hash="fixture-source",
    )
    manifest = build_chronological_split_manifest(
        pd.bdate_range("2025-01-02", periods=150)
    )
    partitions = manifest["partitions"]

    assert set(proxy.signals["vwap_authority"]) == {
        "SESSION_TYPICAL_PRICE_PROXY"
    }
    assert proxy.summary["vwap_proxy_signal_count"] == len(proxy.signals)
    assert rejected.signals.empty
    assert "session_volume_missing_for_vwap" in set(rejected.rejections["reason"])
    assert manifest["coverage_verdict"] == "DEVELOPMENT_VALIDATION_HOLDOUT_READY"
    assert max(partitions["development"]) < min(partitions["validation"])
    assert max(partitions["validation"]) < min(partitions["holdout"])
    assert manifest["holdout_sealed"] is True


def test_fixture_campaign_exercises_ce_screen_cost_grid_and_controls() -> None:
    underlying = _fixture_sessions(3)
    ledger = build_compression_signal_ledger(
        underlying, source_dataset_hash="fixture-source"
    )
    signal = ledger.signals.loc[
        ledger.signals["sample_partition"] == "development"
    ].iloc[0]
    signal_ts = pd.Timestamp(signal["signal_ts"])
    session_date = str(signal["session_date"])
    symbol = "NIFTY_FIXTURE_100_CE"
    catalog = pd.DataFrame(
        [
            {
                "session_date": session_date,
                "contract_symbol": symbol,
                "underlying": "NIFTY",
                "option_type": "CE",
                "strike": 100.0,
                "expiry": (
                    pd.Timestamp(session_date) + pd.Timedelta(days=7)
                ).date().isoformat(),
            }
        ]
    )
    option_bars = pd.DataFrame(
        [
            {
                "contract_symbol": symbol,
                "timestamp": signal_ts + pd.Timedelta(minutes=1),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 1000.0,
            },
            {
                "contract_symbol": symbol,
                "timestamp": signal_ts + pd.Timedelta(minutes=2),
                "open": 110.0,
                "high": 160.0,
                "low": 109.0,
                "close": 150.0,
                "volume": 1000.0,
            },
        ]
    )

    result = run_compression_campaign(
        underlying_bars=underlying,
        contract_catalog=catalog,
        option_bars=option_bars,
        config=CompressionCampaignConfig(
            partition="development",
            minimum_trades=1,
            fixed_cost_per_order=0.0,
        ),
        source_dataset_hash="fixture-source",
    )

    assert result.base_result is not None
    assert result.base_result.summary["trades"] >= 1
    assert result.base_result.trades[0].option_type == "CE"
    assert len(result.sensitivity["scenarios"]) == 4
    assert result.controls["control_status"] == "COMPLETED"
    assert result.summary["holdout_outcomes_read"] is False
    assert result.summary["executable_option_pnl_certified"] is False


def test_fixture_campaign_rejects_supplied_holdout_option_rows() -> None:
    underlying = _fixture_sessions(3)
    ledger = build_compression_signal_ledger(
        underlying, source_dataset_hash="fixture-source"
    )
    holdout_date = ledger.split_manifest["partitions"]["holdout"][0]
    catalog = pd.DataFrame(
        [
            {
                "session_date": holdout_date,
                "contract_symbol": "NIFTY_FIXTURE_100_CE",
                "underlying": "NIFTY",
                "option_type": "CE",
                "strike": 100.0,
                "expiry": (
                    pd.Timestamp(holdout_date) + pd.Timedelta(days=7)
                ).date().isoformat(),
            }
        ]
    )
    option_bars = pd.DataFrame(
        [
            {
                "contract_symbol": "NIFTY_FIXTURE_100_CE",
                "timestamp": f"{holdout_date}T09:46:00+05:30",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="holdout_option_outcomes_supplied"):
        run_compression_campaign(
            underlying_bars=underlying,
            contract_catalog=catalog,
            option_bars=option_bars,
            config=CompressionCampaignConfig(partition="development"),
            source_dataset_hash="fixture-source",
        )
