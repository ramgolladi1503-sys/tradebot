import pytest
import json
from datetime import datetime, timezone
from core.live_drift.disk_loader import DiskLiveDriftLoader
from core.live_drift.drift_errors import LiveDriftInputMissingError, InvalidBaselineError, InvalidSnapshotError

@pytest.fixture
def drift_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    baselines_dir = data_dir / "live_drift" / "baselines"
    snapshots_dir = data_dir / "live_drift" / "snapshots"
    baselines_dir.mkdir(parents=True)
    snapshots_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return baselines_dir, snapshots_dir

def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def _write_raw(path, raw_string):
    with open(path, "w") as f:
        f.write(raw_string)

def _valid_baseline(strategy_id="STR-TEST"):
    return {
        "schema_version": "1.0",
        "strategy_id": strategy_id,
        "certification_id": "CERT-1",
        "certified_timestamp": datetime.now(timezone.utc).isoformat(),
        "expected_expectancy": 1.5,
        "expected_profit_factor": 2.0,
        "max_drawdown_limit": 0.1,
        "regime_signature": "bull"
    }

def _valid_snapshot(strategy_id="STR-TEST"):
    return {
        "schema_version": "1.0",
        "strategy_id": strategy_id,
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "observed_expectancy": 1.2,
        "observed_profit_factor": 1.8,
        "current_drawdown": 0.05,
        "current_regime_signature": "bull",
        "slippage_ratio": 1.0,
        "total_observations": 150,
        "data_freshness_seconds": 60
    }

# --- Missing file tests ---
def test_missing_baseline(drift_dirs):
    loader = DiskLiveDriftLoader()
    with pytest.raises(LiveDriftInputMissingError, match="Missing certification baseline"):
        loader.load_baseline("MISSING-STR")

def test_missing_snapshot(drift_dirs):
    loader = DiskLiveDriftLoader()
    with pytest.raises(LiveDriftInputMissingError, match="Missing live snapshot"):
        loader.load_snapshot("MISSING-STR")

# --- Malformed JSON tests ---
def test_malformed_json_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    _write_raw(b_dir / "STR-TEST.json", "{ malformed_json: ")
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Malformed JSON"):
        loader.load_baseline("STR-TEST")

def test_malformed_json_snapshot(drift_dirs):
    _, s_dir = drift_dirs
    _write_raw(s_dir / "STR-TEST.json", "{ malformed_json: ")
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidSnapshotError, match="Malformed JSON"):
        loader.load_snapshot("STR-TEST")

# --- Mismatched Strategy ID tests ---
def test_mismatched_strategy_id_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    data = _valid_baseline(strategy_id="STR-OTHER")
    _write_json(b_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="strategy_id mismatch: expected STR-TEST, got STR-OTHER"):
        loader.load_baseline("STR-TEST")

def test_mismatched_strategy_id_snapshot(drift_dirs):
    _, s_dir = drift_dirs
    data = _valid_snapshot(strategy_id="STR-OTHER")
    _write_json(s_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidSnapshotError, match="strategy_id mismatch: expected STR-TEST, got STR-OTHER"):
        loader.load_snapshot("STR-TEST")

# --- Schema tests ---
def test_missing_schema_version_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    data = _valid_baseline()
    del data["schema_version"]
    _write_json(b_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Missing schema_version"):
        loader.load_baseline("STR-TEST")

def test_unsupported_schema_version_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    data = _valid_baseline()
    data["schema_version"] = "9.9"
    _write_json(b_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Unsupported schema version: 9.9"):
        loader.load_baseline("STR-TEST")

# --- Timestamp tests ---
def test_invalid_timestamp_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    data = _valid_baseline()
    data["certified_timestamp"] = "not-a-timestamp"
    _write_json(b_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Invalid timestamp: not-a-timestamp"):
        loader.load_baseline("STR-TEST")

def test_invalid_timestamp_snapshot(drift_dirs):
    _, s_dir = drift_dirs
    data = _valid_snapshot()
    data["snapshot_timestamp"] = "not-a-timestamp"
    _write_json(s_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidSnapshotError, match="Invalid timestamp: not-a-timestamp"):
        loader.load_snapshot("STR-TEST")

# --- Missing field tests ---
def test_missing_field_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    data = _valid_baseline()
    del data["expected_expectancy"]
    _write_json(b_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Missing required field: expected_expectancy"):
        loader.load_baseline("STR-TEST")

def test_missing_field_snapshot(drift_dirs):
    _, s_dir = drift_dirs
    data = _valid_snapshot()
    del data["observed_profit_factor"]
    _write_json(s_dir / "STR-TEST.json", data)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidSnapshotError, match="Missing required field: observed_profit_factor"):
        loader.load_snapshot("STR-TEST")

# --- Duplicate key tests ---
def test_duplicate_keys_baseline(drift_dirs):
    b_dir, _ = drift_dirs
    raw_json = '{"schema_version": "1.0", "strategy_id": "STR-TEST", "certification_id": "CERT-1", "certification_id": "CERT-2", "certified_timestamp": "2026-06-27T00:00:00Z", "expected_expectancy": 1.5, "expected_profit_factor": 2.0, "max_drawdown_limit": 0.1, "regime_signature": "bull"}'
    _write_raw(b_dir / "STR-TEST.json", raw_json)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidBaselineError, match="Duplicate key: certification_id"):
        loader.load_baseline("STR-TEST")

def test_duplicate_keys_snapshot(drift_dirs):
    _, s_dir = drift_dirs
    raw_json = '{"schema_version": "1.0", "strategy_id": "STR-TEST", "snapshot_timestamp": "2026-06-27T00:00:00Z", "observed_expectancy": 1.2, "observed_expectancy": 1.5, "observed_profit_factor": 1.8, "current_drawdown": 0.05, "current_regime_signature": "bull", "slippage_ratio": 1.0, "total_observations": 150, "data_freshness_seconds": 60}'
    _write_raw(s_dir / "STR-TEST.json", raw_json)
    loader = DiskLiveDriftLoader()
    with pytest.raises(InvalidSnapshotError, match="Duplicate key: observed_expectancy"):
        loader.load_snapshot("STR-TEST")

# --- Success tests ---
def test_successful_load(drift_dirs):
    b_dir, s_dir = drift_dirs
    _write_json(b_dir / "STR-TEST.json", _valid_baseline())
    _write_json(s_dir / "STR-TEST.json", _valid_snapshot())
    
    loader = DiskLiveDriftLoader()
    baseline = loader.load_baseline("STR-TEST")
    snapshot = loader.load_snapshot("STR-TEST")
    
    assert baseline.strategy_id == "STR-TEST"
    assert snapshot.strategy_id == "STR-TEST"
    assert baseline.expected_expectancy == 1.5
    assert snapshot.observed_profit_factor == 1.8
    assert snapshot.total_observations == 150
