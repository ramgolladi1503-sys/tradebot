import pytest
import time
from typing import Dict, Any

from core.intelligence.config import config
from core.intelligence.fetchers.base import BaseFetcher, FetchFailureReason
from core.intelligence.extractors.hardened_base import HardenedBaseExtractor, ExtractionError
from core.intelligence.storage.sqlite_store import MIPSQLiteStore
from core.intelligence.calibration.factors import Factor, CalibrationStatus, FactorOrigin
from core.intelligence.replay.intelligence_replay import IntelligenceReplayEngine
from core.intelligence.robots_gate import RobotsGate

class MockFetcher(BaseFetcher):
    def __init__(self, source_id: str, mock_payload: Dict[str, Any], fail_attempts: int = 0):
        super().__init__(source_id)
        self.mock_payload = mock_payload
        self.fail_attempts = fail_attempts
        self.attempts = 0

    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        self.attempts += 1
        if self.attempts <= self.fail_attempts:
            raise Exception("Mock network error")
        return self.mock_payload

def test_circuit_breaker_opens(monkeypatch):
    monkeypatch.setattr(RobotsGate, "can_fetch", lambda self, url: True)
    fetcher = MockFetcher("test_source", {}, fail_attempts=10)

    # Override config for fast testing
    object.__setattr__(config.fetcher, 'CIRCUIT_BREAKER_FAILURE_THRESHOLD', 2)
    object.__setattr__(config.fetcher, 'MAX_RETRIES', 1)

    payload, status, lat = fetcher.fetch("http://test.com")
    assert status == FetchFailureReason.HTTP_ERROR
    payload, status, lat = fetcher.fetch("http://test.com")
    assert status == FetchFailureReason.HTTP_ERROR

    # 3rd attempt should immediately fail circuit breaker
    payload, status, lat = fetcher.fetch("http://test.com")
    assert "CircuitBreakerOpen" in status or status == FetchFailureReason.CIRCUIT_BREAKER_OPEN

def test_response_size_cap(monkeypatch):
    monkeypatch.setattr(RobotsGate, "can_fetch", lambda self, url: True)
    large_payload = {
        "raw_content": "A" * (config.fetcher.MAX_RESPONSE_SIZE_BYTES + 100),
        "size_bytes": config.fetcher.MAX_RESPONSE_SIZE_BYTES + 100,
        "content_type": "text/html"
    }
    fetcher = MockFetcher("test_source", large_payload)
    payload, status, lat = fetcher.fetch("http://test.com")
    assert status == FetchFailureReason.SIZE_EXCEEDED

def test_content_type_rejection(monkeypatch):
    monkeypatch.setattr(RobotsGate, "can_fetch", lambda self, url: True)
    bad_payload = {
        "raw_content": "binarydata",
        "size_bytes": 100,
        "content_type": "application/pdf"
    }
    fetcher = MockFetcher("test_source", bad_payload)
    payload, status, lat = fetcher.fetch("http://test.com")
    assert status == FetchFailureReason.INVALID_CONTENT_TYPE

class MockExtractor(HardenedBaseExtractor):
    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        if "FAIL" in normalized_text:
            raise ExtractionError("Mock extraction failed")
        return {"title": "Test", "published_timestamp": 12345}

def test_extraction_partial_failure():
    extractor = MockExtractor("test.com")
    res = extractor.safe_extract("<html><body>FAIL</body></html>", "http://test.com")
    assert res["status"] == "partial_failure"
    assert res["title"] is None
    assert res["market_impact"] is None

def test_persistence_insert_read(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    store = MIPSQLiteStore(db_path=db_path)

    # Insert source manually
    with store._get_connection() as conn:
        conn.execute("INSERT INTO intelligence_sources (source_id, url) VALUES (?, ?)", ("TEST", "http://test.com"))

    run_id = store.insert_fetch_run("TEST", "http://test.com", time.time(), "success", 0.5)
    assert run_id > 0

    with store._get_connection() as conn:
        row = conn.execute("SELECT status FROM intelligence_fetch_runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row["status"] == "success"

def test_replay_insufficient_evidence():
    engine = IntelligenceReplayEngine(min_sample_size=30)
    # Give it 5 events, it should fail
    events = [{"published_timestamp": 123} for _ in range(5)]
    res = engine.measure_volatility_impact(events, "NIFTY", (0, 0))
    assert res["calibration_status"] == CalibrationStatus.INSUFFICIENT_EVIDENCE.value

def test_factor_computation_evidence():
    factor = Factor(
        name="source_health",
        value="good",
        unit="status",
        origin=FactorOrigin.INFERRED,
        evidence_pointer="http://test.com",
        reason="test",
        measurement_method="test",
        calibration_status=CalibrationStatus.UNCALIBRATED,
        stale_status=False,
        execution_influence_allowed=True, # Will be crushed
        ranking_influence_allowed=True
    )
    assert factor.execution_influence_allowed is False

    with pytest.raises(ValueError):
        Factor("invalid_name", 1, "u", FactorOrigin.INFERRED, "e", "r", "m", CalibrationStatus.UNCALIBRATED, False, False, False)
