from __future__ import annotations

from dataclasses import replace

from aixion_trade_intelligence.session import SessionAnalyzer
from tests.test_aixion_trade_intelligence_v1 import complete_session


def test_partial_quality_fails_closed() -> None:
    rows = complete_session()
    rows[1] = replace(rows[1], data_quality_state="PARTIAL")
    analysis = SessionAnalyzer().analyze(rows)
    assert analysis.manifest["valid"] is False
    assert analysis.manifest["verdict"] == "PARTIAL_DATA_QUALITY"
    assert analysis.manifest["partial_quality_event_count"] == 1
    assert analysis.outcome_readiness["ready_for_strategy_diagnosis"] is False
