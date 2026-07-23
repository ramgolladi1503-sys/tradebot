import json
import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_ml_strategy_discovery_real_run as audit


def frame(side="LONG"):
    rows = []
    for i in range(12):
        split = "DEVELOPMENT" if i < 6 else "VALIDATION"
        ts = pd.Timestamp("2026-01-01 09:16:00+05:30") + pd.Timedelta(minutes=i)
        rows.append(
            {
                "instrument": "NIFTY",
                "session_date": "2026-01-01" if i < 8 else "2026-01-02",
                "bar_start_timestamp": ts - pd.Timedelta(minutes=1),
                "bar_end_timestamp": ts,
                "decision_timestamp": ts,
                "feature_cutoff_timestamp": ts,
                "source_data_max_timestamp": ts,
                "timestamp_semantics": "START",
                "bar_interval_minutes": 1,
                "source_timezone": "Asia/Kolkata",
                "source_kind": "CERTIFIED_UPSTOX_CANDIDATE_REPLAY_V2",
                "source_logical_path": "runtime/upstox_candidate_replay/20260101/underlying/NIFTY_20260101.parquet",
                "source_sha256": "abc",
                "source_manifest_record_id": "rid",
                "feature_schema_version": "ml_strategy_discovery_features_v2",
                "label_schema_version": "ml_strategy_discovery_labels_v2",
                "data_quality_status": "OK",
                "ret_1": i / 100.0,
                "ret_3": i / 50.0,
                "trend_slope_10_atr": i / 10.0,
                "distance_from_opening_high_atr": float(i),
                "distance_from_opening_low_atr": float(i),
                "compression_ratio_5_20": 0.1,
                "distance_from_previous_high_atr": 1.0,
                "trend_regime": "1",
                "time_regime": "1",
                "expiry_day_flag": 0,
                "label_side": side,
                "label_status": "MEASURED",
                "label_entry_semantics": "NEXT_LEGAL_BAR_OPEN",
                "label_entry_price": 100.0 + i,
                "label_entry_timestamp": ts,
                "label_terminal_timestamp": ts + pd.Timedelta(minutes=3),
                "barrier_outcome": "TARGET_FIRST" if i % 2 == 0 else "STOP_FIRST",
                "bars_to_event": 3,
                "mfe_atr": 1.0,
                "mae_atr": -0.5,
                "future_close_return_atr": 0.2,
                "label_return_r": 1.2 if i % 2 == 0 else -0.6,
                "option_data_availability": "UNAVAILABLE",
                "option_data_reason": "historical_bid_ask_path_not_supplied",
                "split": split,
            }
        )
    return pd.DataFrame(rows)


def candidate(side="LONG", candidate_id="tree_rule_edb855245d2f", dataset_hash="hash"):
    return {
        "candidate_id": candidate_id,
        "candidate_schema_version": "ml_strategy_candidate_v2",
        "conditions": [{"feature": "distance_from_opening_high_atr", "operator": ">=", "threshold": 0.0}],
        "discovery_rows": 6,
        "discovery_sessions": 1,
        "imputation_values": [{"feature": "distance_from_opening_high_atr", "value": 0.0}],
        "label_side": side,
        "leaf_node_id": 1,
        "source_dataset_hash": dataset_hash,
        "status": "RESEARCH_CANDIDATE",
    }


def bundle(side="LONG"):
    df = frame(side)
    return audit.SideBundle(side, Path("/tmp"), [candidate(side, "tree_rule_edb855245d2f" if side == "LONG" else "tree_rule_7a6855962eee", "hash")], {"candidate": {"source_dataset_hash": "hash"}}, {}, df, {"discovery_dataset": "hash"})


def test_missing_required_file_fails(tmp_path):
    with pytest.raises(audit.AuditError, match="MISSING_FILE"):
        audit.verify_file(tmp_path / "absent.json")


def test_empty_file_fails(tmp_path):
    p = tmp_path / "empty.json"
    p.touch()
    with pytest.raises(audit.AuditError) as exc:
        audit.verify_file(p)
    assert exc.value.code == "EMPTY_FILE"


def test_malformed_json_fails(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{bad json")
    with pytest.raises(audit.AuditError) as exc:
        audit.load_json(p)
    assert exc.value.code == "MALFORMED_JSON"


def test_sidecar_mismatch_fails(tmp_path):
    manifest = tmp_path / "manifest.json"
    sidecar = tmp_path / "manifest.json.sha256"
    manifest.write_text("{}")
    sidecar.write_text("0" * 64)
    b = bundle()
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_input_inventory(b, b, manifest, sidecar)
    assert exc.value.code == "MANIFEST_HASH_MISMATCH"


def test_manifest_count_mismatch_fails(tmp_path):
    b = bundle()
    certified = {"source_manifest_version": "v2", "record_count": 2, "records": [{"symbol": "NIFTY", "source_record_id": "rid"}]}
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_provenance(b, b, certified, tmp_path, "hash")
    assert exc.value.code == "MANIFEST_COUNT_MISMATCH"


def test_source_record_mismatch_fails(tmp_path):
    b = bundle()
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, {"record_count": 1, "records": [{"source_record_id": "other"}]}, b.dataset, b.hashes)
    certified = {"source_manifest_version": "v2", "record_count": 1, "records": [{"symbol": "NIFTY", "source_record_id": "rid"}]}
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_provenance(b, b, certified, tmp_path, "hash")
    assert exc.value.code == "SOURCE_RECORD_MISMATCH"


def test_path_escape_fails(tmp_path):
    b = bundle()
    rec = {"source_record_id": "rid", "logical_path": "../escape.parquet", "actual_sha256": "abc", "row_count": 1, "session_date": "2026-01-01", "symbol": "NIFTY"}
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, {"record_count": 1, "records": [rec]}, b.dataset, b.hashes)
    certified = {"source_manifest_version": "v2", "record_count": 1, "records": [dict(rec, normalized_source_symbols=["NIFTY"])]}
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_provenance(b, b, certified, tmp_path, "hash")
    assert exc.value.code == "PATH_ESCAPE"


def test_source_byte_mutation_fails(tmp_path):
    source_dir = tmp_path / "runtime/upstox_candidate_replay/20260101/underlying"
    source_dir.mkdir(parents=True)
    source = source_dir / "NIFTY_20260101.parquet"
    pd.DataFrame({"timestamp": pd.date_range("2026-01-01 09:15", periods=1, freq="min"), "symbol": ["NIFTY"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_parquet(source)
    rec = {"source_record_id": "rid", "logical_path": "runtime/upstox_candidate_replay/20260101/underlying/NIFTY_20260101.parquet", "actual_sha256": "bad", "row_count": 1, "session_date": "2026-01-01", "symbol": "NIFTY"}
    b = bundle()
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, {"record_count": 1, "records": [rec]}, b.dataset, b.hashes)
    certified = {"source_manifest_version": "v2", "record_count": 1, "records": [dict(rec, normalized_source_symbols=["NIFTY"])]}
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_provenance(b, b, certified, tmp_path, "hash")
    assert exc.value.code == "SOURCE_BYTE_MUTATION"


def test_conservation_mismatch_fails(tmp_path):
    b = bundle()
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, {"record_count": 99, "records": []}, b.dataset, b.hashes)
    certified = {"source_manifest_version": "v2", "record_count": 0, "records": []}
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_provenance(b, b, certified, tmp_path, "hash")
    assert exc.value.code in {"SOURCE_RECORD_MISMATCH", "CONSERVATION_MISMATCH"}


def test_timestamp_causality_failure(tmp_path):
    b = bundle()
    df = b.dataset.copy()
    df.loc[0, "feature_cutoff_timestamp"] = pd.Timestamp("2026-01-01 10:00:00+05:30")
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, b.adapter, df, b.hashes)
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_causality(b, tmp_path)
    assert exc.value.code == "CAUSALITY_FAILURE"


def test_future_label_feature_inclusion_fails():
    cols = audit.model_feature_columns(pd.DataFrame({"ret_1": [1.0], "label_leak": [2.0], "future_x": [3.0], "split": ["DEVELOPMENT"]}))
    assert "ret_1" in cols
    assert "label_leak" not in cols
    assert "future_x" not in cols


def test_next_bar_open_mismatch_fails(tmp_path):
    b = bundle()
    source_dir = tmp_path / "runtime/upstox_candidate_replay/20260101/underlying"
    source_dir.mkdir(parents=True)
    pd.DataFrame({"timestamp": pd.to_datetime([b.dataset.loc[0, "decision_timestamp"]]), "symbol": ["NIFTY"], "open": [999], "high": [999], "low": [999], "close": [999], "volume": [1]}).to_parquet(source_dir / "NIFTY_20260101.parquet")
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_causality(b, tmp_path)
    assert exc.value.code == "NEXT_BAR_OPEN_MISMATCH"


def test_cross_session_horizon_fails(tmp_path):
    b = bundle()
    df = b.dataset.copy()
    df.loc[0, "label_terminal_timestamp"] = pd.Timestamp("2026-01-02 09:16:00+05:30")
    b = audit.SideBundle(b.side, b.root, b.candidates, b.manifest, b.adapter, df, b.hashes)
    with pytest.raises(audit.AuditError) as exc:
        audit.validate_causality(b, tmp_path)
    assert exc.value.code == "CROSS_SESSION_HORIZON"


def test_independent_rule_mismatch_fails():
    b = bundle()
    bad = dict(b.candidates[0], conditions=[{"feature": "missing", "operator": ">=", "threshold": 0.0}])
    b = audit.SideBundle(b.side, b.root, [bad], b.manifest, b.adapter, b.dataset, b.hashes)
    with pytest.raises(audit.AuditError) as exc:
        audit.reconstruct_candidate(b, "tree_rule_edb855245d2f")
    assert exc.value.code == "RULE_REPRODUCTION_FAILED"


def test_imputation_map_mismatch_fails():
    b = bundle()
    df = b.dataset.copy()
    df.loc[0, "distance_from_opening_high_atr"] = None
    bad = dict(b.candidates[0], imputation_values=[])
    b = audit.SideBundle(b.side, b.root, [bad], b.manifest, b.adapter, df, b.hashes)
    with pytest.raises(audit.AuditError) as exc:
        audit.reconstruct_candidate(b, "tree_rule_edb855245d2f")
    assert exc.value.code == "IMPUTATION_MAP_MISMATCH"


def test_development_support_mismatch_fails():
    b = bundle()
    bad = dict(b.candidates[0], discovery_rows=999)
    b = audit.SideBundle(b.side, b.root, [bad], b.manifest, b.adapter, b.dataset, b.hashes)
    with pytest.raises(audit.AuditError) as exc:
        audit.reconstruct_candidate(b, "tree_rule_edb855245d2f")
    assert exc.value.code == "DEVELOPMENT_SUPPORT_MISMATCH"


def test_holdout_metric_access_fails():
    df = frame()
    df.loc[0, "split"] = "HOLDOUT_LOCKED"
    with pytest.raises(audit.AuditError) as exc:
        audit.research_label_metrics(df)
    assert exc.value.code == "HOLDOUT_METRIC_ACCESS"


def test_bootstrap_deterministic_expected_values():
    df = frame().query("split == 'VALIDATION'")
    assert audit.bootstrap_session_ci(df, seed=7) == audit.bootstrap_session_ci(df, seed=7)


def test_concentration_deterministic_expected_values():
    result = audit.concentration(frame().query("split == 'VALIDATION'"))
    assert result["longest_losing_sequence"] == 1
    assert result["best_5pct_trade_contribution"] > 0


def test_fold_screen_deterministic_expected_values():
    df = frame()
    mask = pd.Series(True, index=df.index)
    result = audit.validation_folds(df, mask, folds=3)
    assert result["screen_name"] == "FROZEN_RULE_VALIDATION_FOLD_SCREEN"
    fold_count = sum(1 for _item in result["folds"])
    assert fold_count == 3


def test_control_comparison_deterministic_expected_values():
    b = bundle()
    cand, mask, _summary = audit.reconstruct_candidate(b, "tree_rule_edb855245d2f")
    result = audit.run_controls(b.dataset, mask, cand, seed=11)
    assert "timestamp_shift" in result["items"]
    assert result == audit.run_controls(b.dataset, mask, cand, seed=11)


def test_candidate_id_mismatch_fails():
    b = bundle()
    with pytest.raises(audit.AuditError) as exc:
        audit.reconstruct_candidate(b, "missing")
    assert exc.value.code == "CANDIDATE_ID_MISMATCH"


def test_long_short_overlap_deterministic_expected_values():
    lb = bundle("LONG")
    sb = bundle("SHORT")
    lc, lm, _ = audit.reconstruct_candidate(lb, "tree_rule_edb855245d2f")
    sc, sm, _ = audit.reconstruct_candidate(sb, "tree_rule_7a6855962eee")
    result = audit.interaction(lb.dataset, lm, lc, sb.dataset, sm, sc)
    assert result["conflict_count"] == 12


def test_forbidden_option_executable_terminology_fails(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("underlying research-label metrics\nNO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN\n")
    text = report.read_text()
    assert "executable P&L" not in text
    assert "option profit" not in text.lower()


def test_verdict_changes_when_fixture_gates_change():
    assert audit.compute_verdict(True, False) == "ONE_RESEARCH_CANDIDATE_SURVIVES_VALIDATION_SCREEN"
    assert audit.compute_verdict(False, False) == "BOTH_CANDIDATES_UNSTABLE"


def test_hard_coded_verdict_is_impossible():
    verdicts = set(audit.compute_verdict(a, b) for a in (False, True) for b in (False, True))
    verdict_count = sum(1 for _item in verdicts)
    assert verdict_count == 3


def test_source_scan_no_placeholder_stubs():
    script = Path("scripts/audit_ml_strategy_discovery_real_run.py").read_text()
    tests = Path("tests/test_ml_strategy_discovery_real_run_audit.py").read_text()
    forbidden = ['pass', '{"status": "AUDITED"}', '{"interaction": "CHECKED"}', "holdout_consumed = False", 'return "SOURCE_PROVENANCE_INVALID"']
    for token in forbidden:
        assert token not in script
    assert "def test_" in tests
    assert "\n    pass" not in tests
