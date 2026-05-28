from __future__ import annotations

from tools.code_excellence.ariadne import cluster_failure_text, map_blast_radius


def test_websocket_fixture_cluster_maps_feed_start_blast_radius():
    text = """
FAILED tests/test_feed_ws.py::test_reconnect
E fixture 'websocket_feed' not found
FAILED tests/test_depth_store.py::test_depth
E fixture 'websocket_feed' not found
"""

    cluster = cluster_failure_text(text).clusters[0]
    radius = map_blast_radius(cluster)

    assert radius.confidence == "CONFIRMED"
    assert "tests/test_feed_ws.py" in radius.related_tests
    assert "core/kite_depth_ws.py" in radius.affected_files
    assert "core/market_data.py" in radius.affected_files
    assert radius.candidate_flow_stage == "market_data"
    assert radius.safety_boundary_relevance == "feed_start_boundary"
    assert "feed_start" in radius.likely_callers


def test_ranking_evidence_cluster_maps_scoring_decision_and_dashboard_reader_paths():
    text = """
FAILED tests/test_ranking_evidence.py::test_score
E KeyError: 'ranking_score'
FAILED tests/test_dashboard_reader.py::test_candidate_rank
E missing field ranking_score
"""

    cluster = cluster_failure_text(text).clusters[0]
    radius = map_blast_radius(cluster)

    assert radius.confidence == "CONFIRMED"
    assert "core/trade_scoring.py" in radius.affected_files
    assert "core/opportunity_engine.py" in radius.affected_files
    assert "core/decision_builder.py" in radius.affected_files
    assert "dashboard/streamlit_app.py" in radius.affected_files
    assert "runtime/analytics" in radius.related_evidence_artifacts
    assert radius.candidate_flow_stage == "ranking"
    assert radius.safety_boundary_relevance == "read_only_dashboard_boundary"


def test_unknown_blast_radius_is_explicit_not_pass():
    text = """
FAILED tests/test_unknown.py::test_unknown
loose output without a stable blast-radius signal
"""

    cluster = cluster_failure_text(text).clusters[0]
    radius = map_blast_radius(cluster)

    assert radius.confidence == "UNKNOWN"
    assert radius.is_unknown is True
    assert "likely_callers_unknown" in radius.unknowns
    assert "candidate_flow_stage_unknown" in radius.unknowns
    assert "safety_boundary_relevance_unknown" in radius.unknowns


def test_daedalus_can_consume_blast_radius_output_later():
    text = """
FAILED tests/test_ranking_evidence.py::test_score
E KeyError: 'ranking_score'
FAILED tests/test_dashboard_reader.py::test_candidate_rank
E missing field ranking_score
"""

    cluster = cluster_failure_text(text).clusters[0]
    radius = map_blast_radius(cluster)

    payload = radius.daedalus_input
    assert payload["cluster_id"] == cluster.cluster_id
    assert payload["cluster_reason"] == cluster.reason
    assert payload["blast_radius_confidence"] == radius.confidence
    assert "core/trade_scoring.py" in payload["affected_files"]
    assert payload["candidate_flow_stage"] == "ranking"
