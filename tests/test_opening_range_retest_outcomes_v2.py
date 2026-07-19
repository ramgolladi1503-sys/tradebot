from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.opening_range_retest_outcomes_v2.audit import verify_sidecar
from research.opening_range_retest_outcomes_v2.artifacts import write_json
from research.opening_range_retest_outcomes_v2.contract import build_contract, canonical_json_bytes, sha256_bytes, sha256_file
from research.opening_range_retest_outcomes_v2.engine import _read_source, measure_candidate
from research.opening_range_retest_outcomes_v2.overlap import build_overlap


def _frame() -> pd.DataFrame:
    ts = pd.date_range("2026-07-06 09:15", periods=375, freq="min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "symbol": ["NIFTY"] * len(ts),
            "open": [100.0 + i for i in range(len(ts))],
            "high": [101.0 + i for i in range(len(ts))],
            "low": [99.0 + i for i in range(len(ts))],
            "close": [100.5 + i for i in range(len(ts))],
            "volume": [1] * len(ts),
        }
    )


def _source_file(tmp_path: Path) -> tuple[dict[str, object], pd.DataFrame]:
    path = tmp_path / "runtime" / "upstox_candidate_replay" / "20260706" / "underlying" / "NIFTY_20260706.parquet"
    path.parent.mkdir(parents=True)
    frame = _frame()
    frame.to_parquet(path, index=False)
    return (
        {
            "source_record_id": "source",
            "logical_path": str(path.relative_to(tmp_path)),
            "actual_sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
            "session_date": "2026-07-06",
            "symbol": "NIFTY",
        },
        frame,
    )


def _candidate(direction: str = "BUY_CALL", ready: str = "2026-07-06T09:20:00+05:30") -> dict[str, object]:
    return {
        "candidate_id": "candidate",
        "candidate_core": {
            "strategy_id": "opening_range_retest_v1",
            "symbol": "NIFTY",
            "direction": direction,
            "status": "RAW_CANDIDATE",
            "raw_score": 1.0,
            "entry_trigger": "entry",
            "invalid_if": "invalid",
            "rank_reason": "rank",
            "proposal_ready_at_iso": ready,
            "setup_id": "setup",
            "history_hash": "history",
            "session_date": "2026-07-06",
        },
        "source_provenance": {
            "source_record_id": "source",
            "source_logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet",
            "source_actual_sha256": "sha",
            "source_manifest_semantic_hash": "243efbbda2dfbe90817408e50a54c5377f45dbb86db460918edb334fc57d3039",
            "source_manifest_version": "v2",
            "source_session_date": "2026-07-06",
            "source_symbol": "NIFTY",
        },
    }


def test_strict_later_entry_skips_same_timestamp_bar(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate()
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["same_timestamp_bar_disposition"] == "SKIPPED_FOR_PRIMARY"
    assert outcome["legal_entry"]["start"] == "2026-07-06T09:21:00+05:30"
    assert outcome["legal_entry"]["open"] == 106.0
    assert outcome["horizons"]["1"]["terminal_start"] == "2026-07-06T09:21:00+05:30"
    assert outcome["horizons"]["3"]["terminal_start"] == "2026-07-06T09:23:00+05:30"


def test_buy_call_and_put_directional_returns_and_mfe_mae(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    call = _candidate("BUY_CALL")
    put = _candidate("BUY_PUT")
    call["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    put["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    call_out = measure_candidate(call, source, frame, "contract")
    put_out = measure_candidate(put, source, frame, "contract")
    assert call_out["horizons"]["1"]["directional_underlying_return"] > 0
    assert put_out["horizons"]["1"]["directional_underlying_return"] < 0
    assert call_out["horizons"]["1"]["mfe"] > 0
    assert put_out["horizons"]["1"]["mae"] < 0


def test_missing_exact_horizon_minute_does_not_fall_forward(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate()
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:25")]
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["horizons"]["5"]["status"] == "MISSING_EXPECTED_MINUTE"


def test_no_legal_entry_for_final_bar_ready(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate(ready="2026-07-06T15:30:00+05:30")
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["terminal_reason"] == "NO_LEGAL_ENTRY_BAR"
    assert set(outcome["horizons"]) == {"1", "3", "5", "15", "30"}
    assert all(item["status"] == "NO_LEGAL_ENTRY_BAR" for item in outcome["horizons"].values())


def test_source_byte_mismatch_fails_before_measurement(tmp_path: Path) -> None:
    source, _frame_obj = _source_file(tmp_path)
    source["actual_sha256"] = "0" * 64
    try:
        _read_source(source, tmp_path)
    except ValueError as exc:
        assert str(exc) == "SOURCE_BYTE_IDENTITY_MISMATCH"
    else:
        raise AssertionError("expected source byte mismatch")


def test_output_sidecar_mismatch_detected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    write_json(path, {"a": 1})
    path.write_text('{"a":2}\n', encoding="utf-8")
    assert verify_sidecar(path)["sidecar_match"] is False


def test_overlap_uses_half_open_adjacency() -> None:
    ledger = {
        "records": [
            {"candidate_id": "a", "candidate_core": {"symbol": "NIFTY", "direction": "BUY_CALL", "session_date": "2026-07-06"}, "legal_entry": {"status": "LEGAL_ENTRY_FOUND", "start": "2026-07-06T09:21:00+05:30"}, "horizons": {"1": {"status": "MEASURED", "terminal_end": "2026-07-06T09:22:00+05:30"}}},
            {"candidate_id": "b", "candidate_core": {"symbol": "NIFTY", "direction": "BUY_PUT", "session_date": "2026-07-06"}, "legal_entry": {"status": "LEGAL_ENTRY_FOUND", "start": "2026-07-06T09:22:00+05:30"}, "horizons": {"1": {"status": "MEASURED", "terminal_end": "2026-07-06T09:23:00+05:30"}}},
            {"candidate_id": "c", "candidate_core": {"symbol": "NIFTY", "direction": "BUY_PUT", "session_date": "2026-07-06"}, "legal_entry": {"status": "LEGAL_ENTRY_FOUND", "start": "2026-07-06T09:22:30+05:30"}, "horizons": {"1": {"status": "MEASURED", "terminal_end": "2026-07-06T09:23:30+05:30"}}},
        ]
    }
    overlap = build_overlap(ledger)
    assert overlap["horizons"]["1"]["overlapping_pair_count"] == 1
    assert overlap["horizons"]["1"]["max_simultaneous_candidates"] == 2


def test_contract_hash_is_stable() -> None:
    a = build_contract(source_authority_root="/tmp/root", base_main_sha="base", execution_commit_sha="head", frozen_code_sha="frozen", implementation_tree_hash="tree")
    b = build_contract(source_authority_root="/other/root", base_main_sha="base", execution_commit_sha="other", frozen_code_sha="frozen", implementation_tree_hash="tree")
    assert a["contract_hash"] == b["contract_hash"]
    assert a["decision"] == "ORB_OUTCOME_CONTRACT_V2_FROZEN"
    assert a["diagnostic_source_authority_root"] != b["diagnostic_source_authority_root"]


def test_unsupported_direction_fails_closed(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate("SELL_CALL")
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["terminal_reason"] == "CANDIDATE_DIRECTION_UNSUPPORTED"
    assert outcome["measured_horizon_count"] == 0
    assert len(outcome["horizons"]) == 5


def test_outcome_id_includes_measured_horizon_count(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate()
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    outcome = measure_candidate(candidate, source, frame, "contract")
    changed = dict(outcome)
    changed["measured_horizon_count"] = 999
    assert sha256_bytes(canonical_json_bytes({k: v for k, v in changed.items() if k != "outcome_id"})) != outcome["outcome_id"]


def test_off_grid_readiness_fails_closed(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate(ready="2026-07-06T09:20:30+05:30")
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["terminal_reason"] == "CANDIDATE_READY_OFF_GRID"


def test_join_symbol_mismatch_fails_closed(tmp_path: Path) -> None:
    source, frame = _source_file(tmp_path)
    candidate = _candidate()
    candidate["source_provenance"]["source_actual_sha256"] = source["actual_sha256"]
    candidate["source_provenance"]["source_symbol"] = "BANKNIFTY"
    outcome = measure_candidate(candidate, source, frame, "contract")
    assert outcome["terminal_reason"] == "SOURCE_PROVENANCE_MISMATCH"
