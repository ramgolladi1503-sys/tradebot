from pathlib import Path
import hashlib
import pytest
from research.governance.autonomous_loop.freshness import prove_freshness, validate_freshness_record

ROOT=Path(__file__).resolve().parents[1]
OLD='6e295bee9771fccefff2f3d7b9a4769b8b9f0372'; NEW='0d3f314154413150ea5065d5b91fb5968404618f'

def test_unrelated_changes_do_not_stale_scope():
    record=prove_freshness(task_candidate_sha=OLD,current_program_sha=NEW,owned_paths=['research/mros_certification/evaluation.py'],evidence_path=ROOT/'research/governance/autonomous_loop/evidence/T24_T26_concrete_6e295bee9.yaml')
    assert record.freshness_status == 'PASS'

def test_changed_scope_stales_evidence():
    record=prove_freshness(task_candidate_sha=OLD,current_program_sha=NEW,owned_paths=['research/governance/autonomous_loop/supervisor.py'],evidence_path=ROOT/'research/governance/autonomous_loop/evidence/T24_T26_concrete_6e295bee9.yaml')
    assert record.task_diff_status == 'CHANGED' and record.freshness_status == 'FAIL'

def test_tamper_and_missing_proof_rejected():
    with pytest.raises(ValueError): validate_freshness_record({'freshness_status':'PASS'})
    record=prove_freshness(task_candidate_sha=OLD,current_program_sha=NEW,owned_paths=[],evidence_path=ROOT/'research/governance/autonomous_loop/evidence/T24_T26_concrete_6e295bee9.yaml',evidence_sha256='0'*64)
    assert record.historical_evidence_integrity == 'FAIL'
