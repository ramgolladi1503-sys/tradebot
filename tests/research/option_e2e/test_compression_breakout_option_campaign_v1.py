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


def _session(
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
    rows.append(
        {
            "timestamp": start + pd.Timedelta(minutes=30),
            "symbol": "NIFTY",
            "open": opened,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    rows.append(
        {
            "timestamp": start + pd.Timedelta(minutes=31),
            "symbol": "NIFTY",
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": volume,
        }
    )
    return pd.DataFrame(rows)


def _multi_session(count: int) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=count)
    return pd.concat(
        [_session(day.date().isoformat(), direction="BULLISH") for day in dates],
        ignore_index=True,
    )


def test_real_generator_builds_causal_bullish_signal_ledger() -> None:
    result = build_compression_signal_ledger(
        _session("2026-07-14"), source_dataset_hash="source-hash"
    )

    assert not result.signals.empty
    signal = result.signals.iloc[0]
    assert signal["strategy_id"] == "compression_breakout_v1"
    assert signal["direction"] == "BULLISH"
    assert signal["candidate_direction"] == "BUY_CALL"
    assert signal["signal_ts"].startswith("2026-07-14T09:45:00")
    assert signal["feature_cutoff_ts"].startswith("2026-07-14T09:46:00")
    assert signal["earliest_entry_ts"] == signal["feature_cutoff_ts"]
    assert signal["params_hash"]
    assert signal["selected_for_execution"]
    assert result.summary["outcomes_read"] is False
    assert result.summary["option_prices_read"] is False


def test_real_generator_builds_bearish_signal_for_pe_mapping() -> None:
    result = build_compression_signal_ledger(
        _session("2026-07-14", direction="BEARISH"),
        source_dataset_hash="source-hash",
    )

    assert not result.signals.empty
    assert result.signals.iloc[0]["direction"] == "BEARISH"
    assert result.signals.iloc[0]["candidate_direction"] == "BUY_PUT"


def test_future_bar_mutation_cannot_change_prior_signal_identity() -> None:
    original = _session("2026-07-14")
    mutated = original.copy()
    mutated.loc[mutated.index[-1], ["open", "high", "low", "close"]] = [
        120.0,
        121.0,
        119.0,
        120.0,
    ]

    first = build_compression_signal_ledger(original, source_dataset_hash="same-source")
    second = build_compression_signal_ledger(mutated, source_dataset_hash="same-source")
    cutoff = "2026-07-14T09:45:00+05:30"
    first_prior = first.signals.loc[first.signals["signal_ts"] <= cutoff]
    second_prior = second.signals.loc[second.signals["signal_ts"] <= cutoff]

    assert first_prior.to_dict("records") == second_prior.to_dict("records")


def test_signal_ledger_contains_no_outcome_or_pnl_columns() -> None:
    result = build_compression_signal_ledger(
        _session("2026-07-14"), source_dataset_hash="source-hash"
    )
    forbidden = ("outcome", "pnl", "future_return", "exit_price")

    assert all(
        not any(token in str(column).lower() for token in forbidden)
        for column in result.signals.columns
    )


def test_zero_volume_vwap_proxy_is_explicitly_counted() -> None:
    result = build_compression_signal_ledger(
        _session("2026-07-14", volume=0.0), source_dataset_hash="source-hash"
    )

    assert not result.signals.empty
    assert set(result.signals["vwap_authority"]) == {"SESSION_TYPICAL_PRICE_PROXY"}
    assert result.summary["vwap_proxy_signal_count"] == len(result.signals)


def test_disallowing_vwap_proxy_rejects_zero_volume_session() -> None:
    result = build_compression_signal_ledger(
        _session("2026-07-14", volume=0.0),
        config=CompressionLedgerConfig(allow_typical_price_vwap_proxy=False),
        source_dataset_hash="source-hash",
    )

    assert result.signals.empty
    assert "session_volume_missing_for_vwap" in set(result.rejections["reason"])


def test_split_manifest_is_chronological_and_holdout_sealed() -> None:
    dates = pd.bdate_range("2025-01-02", periods=150)
    manifest = build_chronological_split_manifest(dates)
    partitions = manifest["partitions"]

    assert manifest["coverage_verdict"] == "DEVELOPMENT_VALIDATION_HOLDOUT_READY"
    assert max(partitions["development"]) < min(partitions["validation"])
    assert max(partitions["validation"]) < min(partitions["holdout"])
    assert manifest["holdout_sealed"] is True
    assert manifest["holdout_outcomes_read"] is False


def test_repeated_signal_ledger_runs_are_byte_semantically_deterministic() -> None:
    bars = _multi_session(4)
    first = build_compression_signal_ledger(bars, source_dataset_hash="source-hash")
    second = build_compression_signal_ledger(bars, source_dataset_hash="source-hash")

    assert first.summary == second.summary
    assert first.split_manifest == second.split_manifest
    assert first.signals.to_dict("records") == second.signals.to_dict("records")


def test_campaign_runs_actual_ce_candle_economics_and_cost_stress() -> None:
    underlying = _multi_session(3)
    ledger = build_compression_signal_ledger(
        underlying, source_dataset_hash="source-hash"
    )
    development_signal = ledger.signals.loc[
        ledger.signals["sample_partition"] == "development"
    ].iloc[0]
    signal_ts = pd.Timestamp(development_signal["signal_ts"])
    session_date = str(development_signal["session_date"])
    contract_symbol = "NIFTY_TEST_100_CE"
    catalog = pd.DataFrame(
        [
            {
                "session_date": session_date,
                "contract_symbol": contract_symbol,
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
                "contract_symbol": contract_symbol,
                "timestamp": signal_ts + pd.Timedelta(minutes=1),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 1000.0,
            },
            {
                "contract_symbol": contract_symbol,
                "timestamp": signal_ts + pd.Timedelta(minutes=2),
                "open": 110.0,
                "high": 160.0,
                "low": 109.0,
                "close": 150.0,
                "volume": 1000.0,
            },
            {
                "contract_symbol": contract_symbol,
                "timestamp": signal_ts + pd.Timedelta(minutes=3),
                "open": 150.0,
                "high": 151.0,
                "low": 149.0,
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
            quantity=1,
            fixed_cost_per_order=0.0,
        ),
        source_dataset_hash="source-hash",
    )

    assert result.base_result is not None
    assert result.base_result.summary["trades"] >= 1
    assert result.base_result.trades[0].option_type == "CE"
    assert result.summary["holdout_outcomes_read"] is False
    assert result.summary["executable_option_pnl_certified"] is False
    assert len(result.sensitivity["scenarios"]) == 4
    assert result.controls["control_status"] == "COMPLETED"


def test_campaign_rejects_holdout_option_outcomes() -> None:
    underlying = _multi_session(3)
    ledger = build_compression_signal_ledger(
        underlying, source_dataset_hash="source-hash"
    )
    holdout_date = ledger.split_manifest["partitions"]["holdout"][0]
    catalog = pd.DataFrame(
        [
            {
                "session_date": holdout_date,
                "contract_symbol": "NIFTY_TEST_100_CE",
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
                "contract_symbol": "NIFTY_TEST_100_CE",
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
            source_dataset_hash="source-hash",
        )
