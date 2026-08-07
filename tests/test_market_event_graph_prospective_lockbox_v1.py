from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from core.market_event_graph_breadth_producer import (
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_market_event_graph_prospective_lockbox_v1.py"
    spec = importlib.util.spec_from_file_location("meg_prospective_lockbox_v1_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


L = _load_module()


def _returns(negative: int = 0, positive: int = 0) -> list[float]:
    zeros = 40 - negative - positive
    return [-0.001] * negative + [0.001] * positive + [0.0] * zeros


def _metadata(session_date: str) -> dict:
    base = frozen_threshold_metadata()
    base["market_event_graph_runtime_state"] = initial_market_event_graph_runtime_state(session_date)
    base["completed_constituent_bars"] = [
        {
            "session_date": session_date,
            "ts_epoch": 1000.0,
            "source_bar_end_epoch": 1000.0,
            "completed": True,
            "index_ret1": 0.0,
            "constituent_ret1": _returns(negative=20, positive=20),
        },
        {
            "session_date": session_date,
            "ts_epoch": 1060.0,
            "source_bar_end_epoch": 1060.0,
            "completed": True,
            "index_ret1": -0.001,
            "constituent_ret1": _returns(),
        },
        {
            "session_date": session_date,
            "ts_epoch": 1120.0,
            "source_bar_end_epoch": 1120.0,
            "completed": True,
            "index_ret1": 0.0,
            "constituent_ret1": _returns(positive=40),
        },
        {
            "session_date": session_date,
            "ts_epoch": 1180.0,
            "source_bar_end_epoch": 1180.0,
            "completed": True,
            "index_ret1": 0.0,
            "constituent_ret1": _returns(),
        },
    ]
    return base


def test_rejects_consumed_or_older_sessions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="session_not_fresh"):
        L.seal_session(_metadata("2026-07-22"), tmp_path)


def test_seals_post_cas_session_outcome_blind(tmp_path: Path) -> None:
    metadata = _metadata("2026-08-04")
    metadata["future_return_15"] = 999999.0
    metadata["candidate_profit"] = "must_not_be_copied"

    manifest = L.seal_session(metadata, tmp_path)
    record = json.loads((tmp_path / "sessions" / "2026-08-04.json").read_text())

    assert manifest["total_sealed_sessions"] == 1
    assert manifest["lanes"]["POST_CAS"]["session_count"] == 1
    assert manifest["lanes"]["PRE_CAS_FRESH"]["session_count"] == 0
    assert manifest["policy"] == {
        "outcome_blind": True,
        "pre_post_cas_pooled": False,
        "certification_requires_separate_evaluation": True,
        "minimum_sessions_before_certification_evaluation": 45,
        "independent_edge_certified": False,
        "options_edge_certified": False,
        "shadow_authorized": False,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authorized": False,
    }
    assert set(record["causal_source"]) == {"completed_constituent_bars"}
    assert record["policy"]["outcomes_opened"] is False
    assert record["policy"]["performance_metrics_computed"] is False
    assert record["observer"]["broker_api_called"] is False
    assert record["observer"]["is_order_action"] is False
    assert record["observer"]["allowed_for_live_execution"] is False


def test_pre_and_post_cas_are_sealed_into_separate_lanes(tmp_path: Path) -> None:
    L.seal_session(_metadata("2026-07-23"), tmp_path)
    manifest = L.seal_session(_metadata("2026-08-04"), tmp_path)

    assert manifest["total_sealed_sessions"] == 2
    assert manifest["lanes"]["PRE_CAS_FRESH"]["session_count"] == 1
    assert manifest["lanes"]["POST_CAS"]["session_count"] == 1
    assert manifest["policy"]["pre_post_cas_pooled"] is False
    assert manifest["lanes"]["PRE_CAS_FRESH"]["first_session"] == "2026-07-23"
    assert manifest["lanes"]["POST_CAS"]["first_session"] == "2026-08-04"


def test_exact_reseal_is_idempotent_but_changed_session_conflicts(tmp_path: Path) -> None:
    metadata = _metadata("2026-08-04")
    first = L.seal_session(metadata, tmp_path)
    second = L.seal_session(metadata, tmp_path)
    assert second["semantic_sha256"] == first["semantic_sha256"]

    changed = _metadata("2026-08-04")
    changed["completed_constituent_bars"][3]["index_ret1"] = 0.002
    with pytest.raises(ValueError, match="immutable_session_conflict"):
        L.seal_session(changed, tmp_path)


def test_frozen_contract_drift_fails_closed(tmp_path: Path) -> None:
    metadata = _metadata("2026-08-04")
    metadata["market_event_graph_thresholds"] = dict(metadata["market_event_graph_thresholds"])
    metadata["market_event_graph_thresholds"]["breadth_high"] += 0.01

    with pytest.raises(ValueError, match="frozen_contract_mismatch"):
        L.seal_session(metadata, tmp_path)


def test_milestones_never_equal_certification(tmp_path: Path) -> None:
    assert L.milestone_for_count(4) == "OBSERVATIONAL_ONLY"
    assert L.milestone_for_count(5) == "OBSERVATIONAL_MILESTONE"
    assert L.milestone_for_count(10) == "EARLY_PROSPECTIVE_EVIDENCE"
    assert L.milestone_for_count(20) == "PRELIMINARY_STABILITY_REVIEW_ELIGIBLE"
    assert L.milestone_for_count(45) == "INDEPENDENT_CERTIFICATION_ELIGIBLE"

    manifest = L.seal_session(_metadata("2026-08-04"), tmp_path)
    assert manifest["policy"]["independent_edge_certified"] is False
    assert manifest["policy"]["shadow_authorized"] is False
    assert manifest["policy"]["live_authorized"] is False


def test_tampered_sealed_record_is_rejected(tmp_path: Path) -> None:
    L.seal_session(_metadata("2026-08-04"), tmp_path)
    target = tmp_path / "sessions" / "2026-08-04.json"
    record = json.loads(target.read_text())
    record["policy"]["live_authorized"] = True
    target.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="sealed_record_semantic_hash_mismatch"):
        L.rebuild_manifest(tmp_path)
