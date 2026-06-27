#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid
from core.live_drift import (
    CertifiedBaseline, LiveSnapshot, DriftDetector,
    CertificationLifecycle, NotificationEngine, AuditLog, AuditLogEntry,
    ReportGenerator, LifecycleState, ActionRecommendation,
    LiveDriftValidator
)

def build_mock_data():
    now = datetime.now(timezone.utc)
    
    baseline = CertifiedBaseline(
        strategy_id="STR-ALPHA",
        certification_id="CERT-999",
        certified_timestamp=now,
        expected_expectancy=1.5,
        expected_profit_factor=2.0,
        max_drawdown_limit=0.15,
        regime_signature="high_vol_bear"
    )

    snapshot = LiveSnapshot(
        strategy_id="STR-ALPHA",
        snapshot_timestamp=now,
        observed_expectancy=0.6,
        observed_profit_factor=1.2,
        current_drawdown=0.18,
        current_regime_signature="low_vol_bull",
        slippage_ratio=2.5,
        total_observations=120,
        data_freshness_seconds=3600
    )

    return baseline, snapshot

def main():
    baseline, snapshot = build_mock_data()
    
    LiveDriftValidator.assert_no_strategy_mutation(baseline, snapshot)
    LiveDriftValidator.assert_no_broker_apis_called()
    
    observations = DriftDetector.detect(baseline, snapshot)
    notification = NotificationEngine.evaluate(baseline.strategy_id, observations)
    
    lifecycle = CertificationLifecycle()
    if notification.recommendation in [ActionRecommendation.SUSPEND_RECOMMENDED, ActionRecommendation.MANUAL_REVIEW]:
        lifecycle.transition(baseline.strategy_id, LifecycleState.UNDER_REVIEW, "Drift thresholds exceeded")
        
    audit_log = AuditLog()
    audit_log.append(AuditLogEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        strategy_id=baseline.strategy_id,
        event_type="DRIFT_CHECK",
        details={"recommendation": notification.recommendation.name}
    ))
    
    from core.live_drift import DriftReport
    report = DriftReport(
        strategy_id=baseline.strategy_id,
        report_timestamp=datetime.now(timezone.utc),
        baseline=baseline,
        snapshot=snapshot,
        observations=observations,
        primary_drift=observations[0].drift_type if observations else None
    )
    
    out_dir = Path("docs/live_drift")
    generator = ReportGenerator(out_dir)
    generator.generate(report, notification, lifecycle, audit_log)
    
    print("Live Drift reports generated in docs/live_drift/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
