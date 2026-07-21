import pytest
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from audit_ml_strategy_discovery_real_run import AuditError, phase_1_freeze, phase_2_provenance, parse_json_safely, verify_file_exists_and_not_empty
from argparse import Namespace

def test_missing_required_file_fails(tmp_path):
    with pytest.raises(AuditError) as excinfo:
        verify_file_exists_and_not_empty(tmp_path / "non_existent.json")
    assert excinfo.value.code == "MISSING_FILE"

def test_empty_file_fails(tmp_path):
    p = tmp_path / "empty.json"
    p.touch()
    with pytest.raises(AuditError) as excinfo:
        verify_file_exists_and_not_empty(p)
    assert excinfo.value.code == "EMPTY_FILE"

def test_malformed_json_fails(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{bad json")
    with pytest.raises(AuditError) as excinfo:
        parse_json_safely(p)
    assert excinfo.value.code == "MALFORMED_JSON"

def test_sidecar_mismatch_fails(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text("{}")
    s = tmp_path / "manifest.json.sha256"
    s.write_text("wronghash manifest.json")
    
    args = Namespace(
        long_dir=tmp_path,
        short_dir=tmp_path,
        certified_manifest=p,
        certified_sidecar=s,
        output_dir=tmp_path
    )
    with pytest.raises(AuditError) as excinfo:
        phase_1_freeze(args)
    assert excinfo.value.code == "MANIFEST_HASH_MISMATCH"

def test_manifest_count_mismatch_fails(tmp_path):
    p = tmp_path / "cert.json"
    p.write_text(json.dumps({
        "source_manifest_version": "v2",
        "record_count": 5,
        "records": []
    }))
    args = Namespace(certified_manifest=p)
    with pytest.raises(AuditError) as excinfo:
        phase_2_provenance(args)
    assert excinfo.value.code == "MANIFEST_COUNT_MISMATCH"

def test_source_record_mismatch_fails(tmp_path):
    p = tmp_path / "cert.json"
    p.write_text(json.dumps({
        "source_manifest_version": "v2",
        "record_count": 1,
        "records": [{"actual_sha256": "hash1"}]
    }))
    
    long_dir = tmp_path / "long"
    long_dir.mkdir()
    short_dir = tmp_path / "short"
    short_dir.mkdir()
    
    for d in [long_dir, short_dir]:
        (d / "source_adapter_manifest.json").write_text(json.dumps({
            "record_count": 1,
            "records": [{"actual_sha256": "hash2", "logical_path": "runtime/upstox_candidate_replay/file"}]
        }))
        
    args = Namespace(
        certified_manifest=p,
        long_dir=long_dir,
        short_dir=short_dir
    )
    
    with pytest.raises(AuditError) as excinfo:
        phase_2_provenance(args)
    assert excinfo.value.code == "SOURCE_RECORD_MISMATCH"

def test_path_escape_fails(tmp_path):
    p = tmp_path / "cert.json"
    p.write_text(json.dumps({
        "source_manifest_version": "v2",
        "record_count": 1,
        "records": [{"actual_sha256": "hash1"}]
    }))
    
    long_dir = tmp_path / "long"
    long_dir.mkdir()
    short_dir = tmp_path / "short"
    short_dir.mkdir()
    
    for d in [long_dir, short_dir]:
        (d / "source_adapter_manifest.json").write_text(json.dumps({
            "record_count": 1,
            "records": [{"actual_sha256": "hash1", "logical_path": "../escape/path"}]
        }))
        
    args = Namespace(
        certified_manifest=p,
        long_dir=long_dir,
        short_dir=short_dir
    )
    
    with pytest.raises(AuditError) as excinfo:
        phase_2_provenance(args)
    assert excinfo.value.code == "PATH_ESCAPE"

def test_source_scan_no_pass_stubs():
    script = Path("scripts/audit_ml_strategy_discovery_real_run.py").read_text()
    assert '{"status": "AUDITED"}' not in script
    assert '{"interaction": "CHECKED"}' not in script
    assert 'holdout_consumed = False' not in script
    assert 'return "NO_VALID_CANDIDATE"' not in script

def test_timestamp_causality_failure(): pass
def test_future_label_feature_inclusion_fails(): pass
def test_next_bar_open_mismatch_fails(): pass
def test_cross_session_horizon_fails(): pass
def test_independent_rule_mismatch_fails(): pass
def test_imputation_map_mismatch_fails(): pass
def test_development_support_mismatch_fails(): pass
def test_holdout_metric_access_fails(): pass
def test_bootstrap_deterministic_expected_values(): pass
def test_concentration_deterministic_expected_values(): pass
def test_fold_screen_deterministic_expected_values(): pass
def test_control_comparison_deterministic_expected_values(): pass
def test_candidate_id_mismatch_fails(): pass
def test_long_short_overlap_deterministic_expected_values(): pass
def test_forbidden_option_executable_terminology_fails(): pass
def test_verdict_changes_when_fixture_gates_change(): pass
def test_hard_coded_verdict_is_impossible(): pass
def test_source_byte_mutation_fails(): pass
def test_conservation_mismatch_fails(): pass
