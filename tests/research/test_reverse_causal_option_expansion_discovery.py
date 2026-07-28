from pathlib import Path

import pandas as pd

from scripts.run_reverse_causal_option_expansion_discovery import (
    add_forward_labels,
    build_controls,
    build_inventory,
    capability_matrix,
    is_lfs_pointer,
    schema_fingerprint,
    sha256_file,
    suppress_overlaps,
    verdict_from_matrix,
    write_outputs,
)


def test_real_file_versus_lfs_pointer_detection(tmp_path: Path) -> None:
    real = tmp_path / "real.parquet"
    pointer = tmp_path / "pointer.parquet"
    pd.DataFrame([{"timestamp": "2025-01-01", "close": 1.0}]).to_parquet(real)
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        "size 123\n"
    )

    assert not is_lfs_pointer(real)
    assert is_lfs_pointer(pointer)
    assert len(sha256_file(real)) == 64


def test_schema_fingerprint_is_deterministic() -> None:
    df = pd.DataFrame({"a": [1], "b": [1.0]})

    assert schema_fingerprint(df) == schema_fingerprint(df.copy())


def test_stage_b_and_c_can_run_without_spread_depth_when_source_integrity_is_valid(tmp_path: Path) -> None:
    source_root = make_source_root(tmp_path)
    contracts = pd.read_parquet(source_root / "manifests" / "contract_inventory.parquet")
    inventory = build_inventory(source_root, contracts, tmp_path)
    matrix = capability_matrix(inventory)

    assert matrix["A_SOURCE_INTEGRITY"]["can_run"] is True
    assert matrix["B_CAUSAL_STRUCTURAL_DISCOVERY"]["can_run"] is True
    assert matrix["C_GROSS_OUTCOME_EVALUATION"]["can_run"] is True
    assert matrix["E_EXECUTION_CERTIFICATION"]["can_run"] is False
    assert "AUTHORITATIVE_QUOTE_OR_SPREAD_MISSING" in matrix["E_EXECUTION_CERTIFICATION"]["blockers"]


def test_next_observation_execution_and_overlap_suppression() -> None:
    df = option_frame("NSE_FO|1|01-01-2025", [100, 101, 102, 103, 104, 105, 106, 107], highs=[100, 130, 131, 132, 133, 134, 135, 136])
    labeled = add_forward_labels(df, horizon=3)
    first = labeled.iloc[0]

    assert first["entry_price_next_open"] == 101
    assert first["forward_mfe_points"] == 31
    clustered = suppress_overlaps(labeled, cooldown_minutes=30)
    assert clustered["move_cluster_id"].dropna().nunique() == 1


def test_matched_and_near_miss_controls_are_constructed() -> None:
    rows = []
    for session in ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]:
        frame = option_frame(f"NSE_FO|{session}", [100, 101, 102, 103, 104, 105, 106, 107], session=session)
        rows.append(add_forward_labels(frame, horizon=3))
    labeled = pd.concat(rows, ignore_index=True)
    labeled["is_expansion_event"] = False
    labeled.loc[0, "is_expansion_event"] = True
    labeled.loc[1:3, "forward_mfe_points"] = 20
    labeled["premium_band"] = 2
    labeled["days_to_expiry"] = 0
    labeled["minute_of_day"] = 600
    labeled["move_cluster_id"] = pd.NA
    labeled.loc[0, "move_cluster_id"] = "cluster-1"

    matched, near, quality = build_controls(labeled)

    assert quality["matched_control_rows"] > 0
    assert len(near) > 0
    assert matched["control_type"].eq("matched_ordinary").all()
    assert near["control_type"].eq("near_miss").all()


def test_verdict_selects_gross_tier_not_invalid_for_missing_quotes(tmp_path: Path) -> None:
    source_root = make_source_root(tmp_path)
    contracts = pd.read_parquet(source_root / "manifests" / "contract_inventory.parquet")
    inventory = build_inventory(source_root, contracts, tmp_path)
    matrix = capability_matrix(inventory)

    assert verdict_from_matrix(matrix, precursor_rows=1) == "ASSUMPTION_BASED_COST_STRESS_ONLY"


def test_outputs_are_deterministic_for_same_inputs(tmp_path: Path) -> None:
    source_root = make_source_root(tmp_path)
    contracts = pd.read_parquet(source_root / "manifests" / "contract_inventory.parquet")
    inventory = build_inventory(source_root, contracts, tmp_path)
    matrix = capability_matrix(inventory)
    package1 = write_outputs(tmp_path / "out1", inventory, matrix, "abc", {"accepted_precursors": 0})
    package2 = write_outputs(tmp_path / "out2", inventory, matrix, "abc", {"accepted_precursors": 0})

    assert package1["principal_verdict"] == package2["principal_verdict"]
    assert package1["holdout_status"] == "NOT_OPENED_NO_FROZEN_MECHANISM"


def make_source_root(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    option_dir = source_root / "normalized/candles_1minute/underlying=NIFTY/expiry=2025-01-01/option_type=CE/strike=24000.0"
    option_dir.mkdir(parents=True)
    manifests = source_root / "manifests"
    manifests.mkdir()
    option_path = option_dir / "part.parquet"
    option_frame("NSE_FO|1|01-01-2025", [100, 101, 102, 103, 104, 105, 106, 107]).to_parquet(option_path)
    underlying = tmp_path / "underlying.parquet"
    pd.DataFrame(
        [{"timestamp": "2025-01-01 09:15:00+05:30", "symbol": "NIFTY", "close": 24000.0}]
    ).to_parquet(underlying)
    underlying_hash = sha256_file(underlying)
    pd.DataFrame(
        [
            {
                "final_status": "VALID_COMPLETE",
                "expired_instrument_key": "NSE_FO|1|01-01-2025",
                "expiry": "2025-01-01",
                "strike": 24000.0,
                "option_type": "CE",
                "trading_symbol": "NIFTY 24000 CE 01 JAN 25",
                "normalized_1m_path": str(option_path.relative_to(source_root)),
                "one_minute_row_count": 8,
                "unique_session_count": 1,
                "first_candle": "2025-01-01 09:15:00+05:30",
                "last_candle": "2025-01-01 09:22:00+05:30",
            }
        ]
    ).to_parquet(manifests / "contract_inventory.parquet")
    pd.DataFrame(
        [{"underlying_source_path": str(underlying), "underlying_source_hash": underlying_hash}]
    ).to_parquet(manifests / "atm_selection_ledger.parquet")
    return source_root


def option_frame(instrument: str, opens: list[float], highs: list[float] | None = None, session: str = "2025-01-01") -> pd.DataFrame:
    timestamps = pd.date_range(f"{session} 09:15:00+05:30", periods=len(opens), freq="min")
    highs = highs or [value + 1 for value in opens]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": [value - 1 for value in opens],
            "close": opens,
            "volume": [1000] * len(opens),
            "open_interest": [100] * len(opens),
            "expiry": ["2025-01-01"] * len(opens),
            "strike": [24000.0] * len(opens),
            "option_type": ["CE"] * len(opens),
            "trading_symbol": ["NIFTY 24000 CE 01 JAN 25"] * len(opens),
            "expired_instrument_key": [instrument] * len(opens),
        }
    )
