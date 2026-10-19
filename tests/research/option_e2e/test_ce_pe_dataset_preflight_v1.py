from __future__ import annotations

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_dataset_preflight_v1.build_preflight import (
    _assemble_outputs,
    _inspect_dataframe,
)


def test_underlying_data_cannot_pass_as_option_data(tmp_path) -> None:
    path = tmp_path / "nifty_1m.parquet"
    pd.DataFrame(
        {
            "timestamp": ["2026-07-14 09:15:00"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert result["actual_strict_loader_invoked"] is False
    assert "missing_ce_coverage" in result["raw_source_rejection_reasons"]
    assert "missing_pe_coverage" in result["raw_source_rejection_reasons"]


def test_ltp_without_bid_ask_cannot_pass(tmp_path) -> None:
    path = tmp_path / "option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0],
            "instrument_key": ["NSE_FO|1"],
            "ltp": [10.0],
            "instrument_type": ["CE"],
            "strike_price": [25000.0],
            "expiry": ["2026-07-30"],
            "provider": ["test"],
            "dataset_hash": ["abc"],
            "bar_interval": ["1m"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert "missing_bid_ask_columns" in result["raw_source_rejection_reasons"]


def test_ce_only_reports_missing_pe(tmp_path) -> None:
    path = tmp_path / "option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0],
            "instrument_key": ["NSE_FO|1"],
            "bid": [9.9],
            "ask": [10.1],
            "instrument_type": ["CE"],
            "strike_price": [25000.0],
            "expiry": ["2026-07-30"],
            "provider": ["test"],
            "dataset_hash": ["abc"],
            "bar_interval": ["1m"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert "missing_pe_coverage" in result["raw_source_rejection_reasons"]


def test_partial_bid_ask_coverage_never_becomes_strict_acceptance(tmp_path) -> None:
    path = tmp_path / "upstox_option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0, 1784006405.0],
            "instrument_key": ["CE1", "PE1"],
            "bid_price": [9.9, None],
            "ask_price": [10.1, None],
            "instrument_type": ["CE", "PE"],
            "strike_price": [25000.0, 25000.0],
            "expiry": ["2026-07-30", "2026-07-30"],
            "provider": ["upstox", "upstox"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["raw_source_acceptance"] is True
    assert result["bid_ask_joint_coverage"] == 0.5
    assert result["strict_loader_acceptance"] is False
    assert "incomplete_bid_ask_coverage" in result["strict_replay_rejection_reasons"]


def test_path_inferred_provider_is_limitation_qualified(tmp_path) -> None:
    path = tmp_path / "upstox_option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0, 1784006405.0],
            "instrument_key": ["CE1", "PE1"],
            "bid_price": [9.9, 9.8],
            "ask_price": [10.1, 10.0],
            "instrument_type": ["CE", "PE"],
            "strike_price": [25000.0, 25000.0],
            "expiry": ["2026-07-30", "2026-07-30"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["provider_claim"] == "upstox"
    assert result["provider_authority"] == "PATH_INFERRED_LIMITATION"
    assert result["strict_loader_acceptance"] is False
    assert "provider_provenance_not_authoritative" in result["strict_replay_rejection_reasons"]


def test_raw_tick_source_does_not_authorize_replay_dataset() -> None:
    raw = {
        "candidate_id": "RAW:combined.parquet",
        "classification": "RAW_OPTION_TICK_DATASET",
        "physical_sha256": "abc",
        "physical_sha256_matches_snapshot": True,
        "raw_source_acceptance": True,
        "strict_loader_acceptance": False,
        "actual_strict_loader_invoked": False,
        "bid_ask_joint_coverage": 0.97,
        "contract_metadata_coverage": 0.95,
        "row_count": 100,
        "session_count": 1,
    }

    _, preflight, oracle = _assemble_outputs(
        candidates=[raw],
        denied_metadata_only_candidates=0,
    )

    assert preflight["raw_source_verdict"] == "RAW_CE_PE_TICK_SOURCE_VALIDATED"
    assert preflight["verdict"] == "STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED"
    assert preflight["accepted_dataset_id"] is None
    assert preflight["chronological_coverage_verdict"] == "ONE_SESSION_SMOKE_ONLY"
    assert preflight["primary_oracle_agreement"] == "NOT_ESTABLISHED"
    assert oracle["oracle_verdict"] == "INDEPENDENT_ORACLE_REQUIRED"
