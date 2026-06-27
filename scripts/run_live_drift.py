#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
import uuid
import logging

from core.live_drift import (
    DriftDetector, CertificationLifecycle, NotificationEngine, 
    AuditLog, AuditLogEntry, ReportGenerator, LifecycleState, 
    ActionRecommendation, LiveDriftValidator,
    DiskLiveDriftLoader, LiveDriftInputMissingError,
    InvalidBaselineError, InvalidSnapshotError
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Run Live Drift Detection")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy ID to evaluate drift for")
    parser.add_argument("--dry-run", action="store_true", help="Run with mock data (disabled, must use real data)")
    args = parser.parse_args()

    logging.info(f"Running Live Drift detection for {args.strategy}")
    loader = DiskLiveDriftLoader()
    
    try:
        baseline = loader.load_baseline(args.strategy)
        snapshot = loader.load_snapshot(args.strategy)
    except (LiveDriftInputMissingError, InvalidBaselineError, InvalidSnapshotError) as e:
        logging.error(f"LIVE_DRIFT_BLOCKED: {e}")
        return 1
    
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
    
    logging.info("Live Drift reports generated in docs/live_drift/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
