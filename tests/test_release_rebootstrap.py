import json
from pathlib import Path
import pytest

from core.certified_release_store import ReleaseStore, ReleaseStoreError, digest
from core.release_certification import SYNTHETIC_INVALIDATED_SHAS
from core.release_rebootstrap import REBOOTSTRAP_GATES, promote_rebootstrap, rebootstrap_binding
from core.release_certification import digest as cert_digest

Q = next(iter(SYNTHETIC_INVALIDATED_SHAS))
C = "d" * 40


def bootstrap_quarantined(root: Path):
    return ReleaseStore(root).record_verified_selection(candidate_sha=Q, evidence_sha256="a"*64, expected_event=None)


def pass_result(event):
    evaluations=[{"gate":g,"primitive_sha256":("%064x"%(i+1)),"recomputed_result":"PASS","status":"PASS"} for i,g in enumerate(REBOOTSTRAP_GATES)]
    r={"schema_version":1,"certification_type":"GOVERNED_REBOOTSTRAP","trust_boundary":"post_pr907_primitive_v1","candidate_sha":C,"quarantined_predecessor_sha":Q,"quarantined_predecessor_event":event["event_sha256"],"fallback_sha":None,"rollback_status":"NO_TRUSTED_FALLBACK","dependency_graph_sha256":"b"*64,"required_gates":REBOOTSTRAP_GATES,"gate_evaluations":evaluations,"passed_gates":REBOOTSTRAP_GATES,"failed_gates":[],"reason":"recover quarantined synthetic head","verdict":"PASS"}
    r["certification_sha256"]=cert_digest(r); return r


def attestation(r):
    a={"verdict":"PASS","verifier":"verify_release_rebootstrap_v1","binding_sha256":cert_digest(rebootstrap_binding(r))}
    return {"independent_release_verifier_pass":True,"attestation":a}


def test_rebootstrap_preserves_history_and_has_no_synthetic_fallback(tmp_path):
    store=ReleaseStore(tmp_path); old=bootstrap_quarantined(tmp_path); old_bytes=(store.history/(old["event_sha256"]+".json")).read_bytes()
    r=pass_result(old); event=promote_rebootstrap(r,store,attestation(r))
    assert event["event_type"]=="GOVERNED_REBOOTSTRAP"
    assert event["fallback_live_sha"] is None
    assert event["rollback_status"]=="NO_TRUSTED_FALLBACK"
    assert event["previous_event"]==old["event_sha256"]
    assert (store.history/(old["event_sha256"]+".json")).read_bytes()==old_bytes
    assert store.read()["certified_live_sha"]==C


def test_rebootstrap_from_healthy_head_rejected(tmp_path):
    store=ReleaseStore(tmp_path); old=store.record_verified_selection(candidate_sha="a"*40,evidence_sha256="b"*64,expected_event=None)
    with pytest.raises(ReleaseStoreError,match="rebootstrap_requires_quarantined_head"):
        promote_rebootstrap(pass_result({"event_sha256":old["event_sha256"]}),store,{})

@pytest.mark.parametrize("mutation",["candidate","predecessor_sha","predecessor_event","fallback","failed_gate","cert_hash","attestation","verifier"])
def test_rebootstrap_binding_mutations_fail_closed(tmp_path,mutation):
    store=ReleaseStore(tmp_path); old=bootstrap_quarantined(tmp_path); r=pass_result(old); att=attestation(r)
    if mutation=="candidate": r["candidate_sha"]="c"*40
    elif mutation=="predecessor_sha": r["quarantined_predecessor_sha"]="c"*40
    elif mutation=="predecessor_event": r["quarantined_predecessor_event"]="0"*64
    elif mutation=="fallback": r["fallback_sha"]=Q
    elif mutation=="failed_gate": r["failed_gates"]=[REBOOTSTRAP_GATES[0]]
    elif mutation=="cert_hash": r["certification_sha256"]="0"*64
    elif mutation=="attestation": att["attestation"]["binding_sha256"]="0"*64
    elif mutation=="verifier": att["attestation"]["verifier"]="wrong"
    with pytest.raises(ReleaseStoreError): promote_rebootstrap(r,store,att)


def test_second_rebootstrap_cannot_use_healthy_recovered_head(tmp_path):
    store=ReleaseStore(tmp_path); old=bootstrap_quarantined(tmp_path); r=pass_result(old); promote_rebootstrap(r,store,attestation(r))
    with pytest.raises(ReleaseStoreError,match="rebootstrap_requires_quarantined_head"):
        promote_rebootstrap(r,store,attestation(r))


def test_store_rejects_rebootstrap_with_quarantined_fallback(tmp_path):
    store=ReleaseStore(tmp_path); old=bootstrap_quarantined(tmp_path)
    with pytest.raises(ReleaseStoreError):
        store.record_governed_rebootstrap(candidate_sha=C,expected_event=old["event_sha256"],quarantined_predecessor_sha=Q,dependency_graph_sha256="b"*64,certification_sha256="c"*64,verifier_attestation_sha256="d"*64,reason="")
