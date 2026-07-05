import pytest
from pathlib import Path
import json
import yaml

def test_batch_summary_status_mapping(tmp_path, monkeypatch):
    import scripts.run_batch_strategy_certification as batch_mod
    
    runtime_dir = tmp_path / "runtime" / "strategy_validation"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    # Create fake registry
    class FakeEntry:
        def __init__(self):
            self.strategy_kind = "candidate_generator_strategy"
            self.certification_track = "candidate_generator_contract_only"
            self.module_path = "dummy"
            self.callable_name = "dummy"
            self.strategy_id = "TEST_REPLAY"
    
    registry = {"TEST_REPLAY": FakeEntry()}
    monkeypatch.setattr(batch_mod, "load_strategy_registry", lambda: registry)
    
    # Mock audit success
    monkeypatch.setattr(batch_mod, "run_cmd", lambda cmd: True)
    
    # Mock runtime_dir
    monkeypatch.setattr(batch_mod, "Path", lambda path_str: runtime_dir if path_str == "runtime/strategy_validation" else Path(path_str))
    
    # Create fake replay report
    (runtime_dir / "TEST_REPLAY").mkdir(parents=True, exist_ok=True)
    report = {
        "lifecycle_state": "DATA_FETCH_PENDING",
        "data_fetch_status": "DATA_FETCH_NOT_REQUESTED",
        "adapter_approved_for_replay": False,
        "certifiable_data": False,
        "certification_blockers": ["DATA_BLOCKED_REAL_OPTION_LTP_MISSING"]
    }
    with open(runtime_dir / "TEST_REPLAY" / "candidate_replay_report.json", "w") as f:
        json.dump(report, f)
        
    class Args:
        include_candidate_replay = True
    
    batch_mod.main(args=["--include-candidate-replay"])
    
    with open(runtime_dir / "candidate_replay_batch_summary.json") as f:
        summary = json.load(f)
        
    assert len(summary) == 1
    assert summary[0]["contract_audit_status"] == "CANDIDATE_GENERATOR_CONTRACT_PASSED"
    assert summary[0]["lifecycle_state"] == "DATA_FETCH_PENDING"
    assert summary[0]["candidate_replay_status"] == "CANDIDATE_REPLAY_DATA_BLOCKED"
    assert summary[0]["data_fetch_status"] == "DATA_FETCH_NOT_REQUESTED"

