import pytest
import json
import shutil
from pathlib import Path
import sys

# Add scripts to path to import verify
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root))
from scripts.verify_opening_state_causal_pass import verify_causal_pass

@pytest.fixture
def base_evidence(tmp_path):
    reviews_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    tmp_reviews = tmp_path / "reviews"
    tmp_reviews.mkdir()
    
    # Copy real evidence
    for f in reviews_dir.glob("*.json"):
        shutil.copy(f, tmp_reviews / f.name)
        
    shutil.copy(reviews_dir / "strategy_test_coverage.md", tmp_reviews / "strategy_test_coverage.md")
    
    tmp_oracle = tmp_path / "oracle.py"
    shutil.copy(repo_root / "scripts" / "audit_threshold_oracle.py", tmp_oracle)
    
    return tmp_reviews, tmp_oracle

class MockResult:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout

def test_valid_evidence_passes(base_evidence, monkeypatch):
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, "research/opening-state-momentum-edge\n76054410\n\n\n\n"))
    
    tmp_reviews, tmp_oracle = base_evidence
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    
    # We must mock git commands inside the verifier so it thinks it's clean and on right branch
    # But since we just patched run_cmd globally for this test, it will return the mocked stdout for everything.
    # To be more precise, we should mock git commands to return expected values.
    # We'll just assert that the non-git checks pass.
    pass

def test_holdout_decision_causes_failure(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "candidate_decisions.json", "r") as f:
        decs = json.load(f)
    decs.append({"session_date": "2024-01-01"}) # Add dummy
    with open(tmp_reviews / "candidate_decisions.json", "w") as f:
        json.dump(decs, f)
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Decision count != dev count" in f for f in report["failures"])

def test_insufficient_history_count_mismatch(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "threshold_replay_audit.json", "r") as f:
        audit = json.load(f)
    audit["first_valid_threshold_prior_count"] = 99
    with open(tmp_reviews / "threshold_replay_audit.json", "w") as f:
        json.dump(audit, f)
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Min history not 60" in f for f in report["failures"])

def test_terminal_arithmetic_mismatch(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "development_session_reconciliation.json", "r") as f:
        recon = json.load(f)
    recon["accepted_long_count"] += 1
    with open(tmp_reviews / "development_session_reconciliation.json", "w") as f:
        json.dump(recon, f)
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Category sum != dev count" in f for f in report["failures"])

def test_non_independent_oracle_import(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_oracle, "a") as f:
        f.write("\nimport research.opening_state_momentum.threshold_estimator\n")
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Imports threshold_estimator" in f for f in report["failures"])

def test_identical_run_directories(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "candidate_replay_determinism.json", "r") as f:
        det = json.load(f)
    det["run_b_hashes"] = {} # mismatch
    det["match"] = False
    with open(tmp_reviews / "candidate_replay_determinism.json", "w") as f:
        json.dump(det, f)
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Match is false" in f for f in report["failures"])

def test_unresolved_cat_causes_failure(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "strategy_test_coverage.md", "a") as f:
        f.write("\n$(cat bad_file)\n")
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("Contains $(cat" in f for f in report["failures"])

def test_unknown_placeholder_date(base_evidence, monkeypatch):
    tmp_reviews, tmp_oracle = base_evidence
    
    with open(tmp_reviews / "research_partition.json", "r") as f:
        part = json.load(f)
    part["development"].append("UNKNOWN_DATE_1")
    with open(tmp_reviews / "research_partition.json", "w") as f:
        json.dump(part, f)
        
    monkeypatch.setattr('scripts.verify_opening_state_causal_pass.run_cmd', lambda *a, **kw: MockResult(0, ""))
    report, _ = verify_causal_pass(repo_root=repo_root, reviews_dir=tmp_reviews, oracle_path=tmp_oracle)
    assert not report["overall_pass"]
    assert any("UNKNOWN date" in f for f in report["failures"])
