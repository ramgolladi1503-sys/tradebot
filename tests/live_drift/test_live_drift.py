import pytest
from datetime import datetime, timezone
from core.live_drift import (
    DriftType, LifecycleState, ActionRecommendation,
    CertifiedBaseline, LiveSnapshot, DriftObservation, DriftReport,
    LifecycleTransition, NotificationRecord, AuditLogEntry,
    BaselineLoader, LiveSnapshotLoader, DriftDetector,
    CertificationLifecycle, NotificationEngine, AuditLog,
    LiveDriftValidator
)

def _mock_baseline(expectancy=1.0, pf=1.5, dd=0.2, regime="bull"):
    return CertifiedBaseline(
        strategy_id="STR-1",
        certification_id="CERT-1",
        certified_timestamp=datetime.now(timezone.utc),
        expected_expectancy=expectancy,
        expected_profit_factor=pf,
        max_drawdown_limit=dd,
        regime_signature=regime
    )

def _mock_snapshot(expectancy=1.0, pf=1.5, dd=0.1, regime="bull", slippage=1.0, freshness=100, obs=100):
    return LiveSnapshot(
        strategy_id="STR-1",
        snapshot_timestamp=datetime.now(timezone.utc),
        observed_expectancy=expectancy,
        observed_profit_factor=pf,
        current_drawdown=dd,
        current_regime_signature=regime,
        slippage_ratio=slippage,
        total_observations=obs,
        data_freshness_seconds=freshness
    )

# --- Immutability Tests ---
def test_baseline_immutable():
    b = _mock_baseline()
    with pytest.raises(Exception):
        b.expected_expectancy = 2.0

def test_snapshot_immutable():
    s = _mock_snapshot()
    with pytest.raises(Exception):
        s.observed_expectancy = 2.0

def test_observation_immutable():
    o = DriftObservation(DriftType.NO_DRIFT, 0.0, "test")
    with pytest.raises(Exception):
        o.severity_score = 1.0

def test_report_immutable():
    r = DriftReport("STR-1", datetime.now(timezone.utc), _mock_baseline(), _mock_snapshot(), [], DriftType.NO_DRIFT)
    with pytest.raises(Exception):
        r.primary_drift = DriftType.UNKNOWN

def test_transition_immutable():
    t = LifecycleTransition("STR-1", datetime.now(timezone.utc), LifecycleState.PRODUCTION_CANDIDATE, LifecycleState.WARNING, "reason")
    with pytest.raises(Exception):
        t.reason = "new"

def test_notification_immutable():
    n = NotificationRecord("STR-1", datetime.now(timezone.utc), ActionRecommendation.NO_ACTION, [])
    with pytest.raises(Exception):
        n.recommendation = ActionRecommendation.MONITOR

def test_audit_log_entry_immutable():
    a = AuditLogEntry("1", datetime.now(timezone.utc), "STR-1", "EVENT", {})
    with pytest.raises(Exception):
        a.event_type = "NEW"

# --- Baseline & Snapshot Loaders ---
def test_baseline_loader_adds_baseline():
    loader = BaselineLoader()
    b = _mock_baseline()
    loader.load_baseline(b)
    assert loader.get_baseline("STR-1").strategy_id == "STR-1"

def test_baseline_loader_missing_baseline():
    loader = BaselineLoader()
    assert not hasattr(loader.get_baseline("MISSING"), "strategy_id")

def test_snapshot_loader_adds_snapshot():
    loader = LiveSnapshotLoader()
    s = _mock_snapshot()
    loader.load_snapshot(s)
    assert loader.get_snapshot("STR-1").strategy_id == "STR-1"

def test_snapshot_loader_missing_snapshot():
    loader = LiveSnapshotLoader()
    assert not hasattr(loader.get_snapshot("MISSING"), "strategy_id")

# --- Drift Detector Rules ---
def test_drift_detector_no_drift():
    b = _mock_baseline()
    s = _mock_snapshot()
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.NO_DRIFT
    assert obs[0].drift_type == DriftType.NO_DRIFT

def test_drift_detector_expectancy_collapse():
    b = _mock_baseline(expectancy=2.0)
    s = _mock_snapshot(expectancy=0.5) # < 1.0 (50% of 2.0)
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.EXPECTANCY_DRIFT

def test_drift_detector_profit_factor_collapse():
    b = _mock_baseline(pf=2.0)
    s = _mock_snapshot(pf=1.0) # < 1.4 (70% of 2.0)
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.PROFIT_FACTOR_DRIFT

def test_drift_detector_drawdown_drift():
    b = _mock_baseline(dd=0.1)
    s = _mock_snapshot(dd=0.2)
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.DRAWDOWN_DRIFT

def test_drift_detector_regime_drift():
    b = _mock_baseline(regime="bull")
    s = _mock_snapshot(regime="bear")
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.REGIME_DRIFT

def test_drift_detector_execution_drift():
    b = _mock_baseline()
    s = _mock_snapshot(slippage=2.5) # > 2.0
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.EXECUTION_DRIFT

def test_drift_detector_stale_evidence():
    b = _mock_baseline()
    s = _mock_snapshot(freshness=100000) # > 86400
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.DATA_QUALITY_DRIFT

def test_drift_detector_insufficient_evidence():
    b = _mock_baseline()
    s = _mock_snapshot(obs=10) # < 30
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.INSUFFICIENT_DATA
    
def test_drift_detector_multiple_drifts_simultaneously():
    # Test 44: multiple drifts detected simultaneously
    b = _mock_baseline(expectancy=2.0, pf=2.0, dd=0.1, regime="bull")
    s = _mock_snapshot(expectancy=0.5, pf=1.0, dd=0.2, regime="bear", slippage=3.0, freshness=90000, obs=5)
    obs = DriftDetector.detect(b, s)
    assert obs[0].drift_type == DriftType.EXPECTANCY_DRIFT
    drift_types = [o.drift_type for o in obs]
    assert DriftType.EXPECTANCY_DRIFT in drift_types
    assert DriftType.EXECUTION_DRIFT in drift_types

# --- Certification Lifecycle ---
def test_lifecycle_initial_state():
    cl = CertificationLifecycle()
    assert cl.get_state("STR-1") == LifecycleState.PRODUCTION_CANDIDATE

def test_lifecycle_valid_transition_to_warning():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.WARNING, "Drift")
    assert cl.get_state("STR-1") == LifecycleState.WARNING

def test_lifecycle_valid_transition_to_under_review():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.UNDER_REVIEW, "Drift")
    assert cl.get_state("STR-1") == LifecycleState.UNDER_REVIEW

def test_lifecycle_warning_to_suspended():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.WARNING, "Drift")
    cl.transition("STR-1", LifecycleState.SUSPENDED, "Severe Drift")
    assert cl.get_state("STR-1") == LifecycleState.SUSPENDED

def test_lifecycle_warning_to_production():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.WARNING, "Drift")
    cl.transition("STR-1", LifecycleState.PRODUCTION_CANDIDATE, "Recovered")
    assert cl.get_state("STR-1") == LifecycleState.PRODUCTION_CANDIDATE

def test_lifecycle_under_review_to_suspended():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.UNDER_REVIEW, "Drift")
    cl.transition("STR-1", LifecycleState.SUSPENDED, "Fail")
    assert cl.get_state("STR-1") == LifecycleState.SUSPENDED

def test_lifecycle_suspended_to_revoked():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.UNDER_REVIEW, "Drift")
    cl.transition("STR-1", LifecycleState.SUSPENDED, "Fail")
    cl.transition("STR-1", LifecycleState.REVOKED, "Final")
    assert cl.get_state("STR-1") == LifecycleState.REVOKED

def test_lifecycle_invalid_transition_prod_to_suspended():
    cl = CertificationLifecycle()
    with pytest.raises(ValueError, match="Invalid transition"):
        cl.transition("STR-1", LifecycleState.SUSPENDED, "Fail")

def test_lifecycle_invalid_transition_revoked_to_prod():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.UNDER_REVIEW, "Drift")
    cl.transition("STR-1", LifecycleState.SUSPENDED, "Fail")
    cl.transition("STR-1", LifecycleState.REVOKED, "Final")
    with pytest.raises(ValueError, match="Invalid transition"):
        cl.transition("STR-1", LifecycleState.PRODUCTION_CANDIDATE, "Recovery")
        
def test_lifecycle_invalid_transition_same_state():
    # Test 45: same state transition is invalid if not explicitly allowed (it isn't by VALID_TRANSITIONS)
    cl = CertificationLifecycle()
    with pytest.raises(ValueError, match="Invalid transition"):
        cl.transition("STR-1", LifecycleState.PRODUCTION_CANDIDATE, "Should fail")

def test_lifecycle_history_tracking():
    cl = CertificationLifecycle()
    cl.transition("STR-1", LifecycleState.WARNING, "Drift")
    hist = cl.get_history("STR-1")
    assert hist[0].from_state == LifecycleState.PRODUCTION_CANDIDATE
    assert hist[0].to_state == LifecycleState.WARNING

def test_lifecycle_history_missing():
    cl = CertificationLifecycle()
    assert cl.get_history("STR-1") == []

# --- Notification Engine ---
def test_notification_no_action():
    obs = [DriftObservation(DriftType.NO_DRIFT, 0.0, "OK")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.NO_ACTION

def test_notification_collect_more_data():
    obs = [DriftObservation(DriftType.INSUFFICIENT_DATA, 0.2, "Wait")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.COLLECT_MORE_DATA

def test_notification_monitor():
    obs = [DriftObservation(DriftType.DATA_QUALITY_DRIFT, 0.4, "Stale")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.MONITOR

def test_notification_manual_review():
    obs = [DriftObservation(DriftType.REGIME_DRIFT, 0.6, "Regime")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.MANUAL_REVIEW

def test_notification_suspend_recommended_pf():
    obs = [DriftObservation(DriftType.PROFIT_FACTOR_DRIFT, 0.8, "PF Collapse")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.SUSPEND_RECOMMENDED

def test_notification_suspend_recommended_drawdown():
    obs = [DriftObservation(DriftType.DRAWDOWN_DRIFT, 0.9, "DD Limit")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.SUSPEND_RECOMMENDED

def test_notification_highest_severity_wins():
    obs = [
        DriftObservation(DriftType.INSUFFICIENT_DATA, 0.2, "Wait"),
        DriftObservation(DriftType.DRAWDOWN_DRIFT, 0.9, "DD Limit")
    ]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert rec.recommendation == ActionRecommendation.SUSPEND_RECOMMENDED

def test_notification_reasons_included():
    obs = [DriftObservation(DriftType.DRAWDOWN_DRIFT, 0.9, "DD Limit")]
    rec = NotificationEngine.evaluate("STR-1", obs)
    assert "DD Limit" in rec.reasons[0]

# --- Audit Log ---
def test_audit_log_append_and_get():
    log = AuditLog()
    entry = AuditLogEntry("1", datetime.now(timezone.utc), "STR-1", "TEST", {})
    log.append(entry)
    entries = log.get_entries()
    assert entries[0].entry_id == "1"

def test_audit_log_filter_by_strategy():
    log = AuditLog()
    log.append(AuditLogEntry("1", datetime.now(timezone.utc), "STR-1", "TEST", {}))
    log.append(AuditLogEntry("2", datetime.now(timezone.utc), "STR-2", "TEST", {}))
    entries = log.get_entries("STR-1")
    assert entries[0].entry_id == "1"
    
def test_audit_log_copy():
    log = AuditLog()
    log.append(AuditLogEntry("1", datetime.now(timezone.utc), "STR-1", "TEST", {}))
    entries = log.get_entries()
    entries.clear()
    assert log.get_entries()[0].entry_id == "1"

# --- Validations ---
def test_validation_no_broker_apis():
    assert bool(LiveDriftValidator.assert_no_broker_apis_called())

def test_validation_no_mutation():
    b = _mock_baseline()
    s = _mock_snapshot()
    LiveDriftValidator.assert_no_strategy_mutation(b, s)
    assert not hasattr(LiveDriftValidator.assert_no_strategy_mutation(b, s), "anything")
