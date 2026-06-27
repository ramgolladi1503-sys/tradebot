from pathlib import Path
from core.live_drift.drift_models import DriftReport, NotificationRecord
from core.live_drift.audit_log import AuditLog
from core.live_drift.certification_lifecycle import CertificationLifecycle


class ReportGenerator:
    """Generates the 10 Markdown reports for Live Drift observability."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, filename: str, content: str):
        (self.output_dir / filename).write_text(content, encoding="utf-8")

    def generate(self, report: DriftReport, notification: NotificationRecord, lifecycle: CertificationLifecycle, audit_log: AuditLog):
        self._write("01_baseline.md", self._generate_baseline(report))
        self._write("02_current_snapshot.md", self._generate_snapshot(report))
        self._write("03_drift_analysis.md", self._generate_drift_analysis(report))
        self._write("04_regime_drift.md", self._generate_regime_drift(report))
        self._write("05_execution_drift.md", self._generate_execution_drift(report))
        self._write("06_certification_status.md", self._generate_certification_status(report, lifecycle))
        self._write("07_notifications.md", self._generate_notifications(notification))
        self._write("08_audit_log.md", self._generate_audit_log(audit_log))
        self._write("09_limitations.md", self._generate_limitations())
        self._write("10_summary.md", self._generate_summary(report, notification, lifecycle))

    def _generate_baseline(self, report: DriftReport) -> str:
        lines = [
            f"# Certified Baseline for {report.strategy_id}\n",
            f"- **Expected Expectancy**: {report.baseline.expected_expectancy}",
            f"- **Expected Profit Factor**: {report.baseline.expected_profit_factor}",
            f"- **Max Drawdown Limit**: {report.baseline.max_drawdown_limit}",
            f"- **Regime Signature**: {report.baseline.regime_signature}"
        ]
        return "\n".join(lines)

    def _generate_snapshot(self, report: DriftReport) -> str:
        lines = [
            f"# Current Snapshot for {report.strategy_id}\n",
            f"- **Observed Expectancy**: {report.snapshot.observed_expectancy}",
            f"- **Observed Profit Factor**: {report.snapshot.observed_profit_factor}",
            f"- **Current Drawdown**: {report.snapshot.current_drawdown}",
            f"- **Slippage Ratio**: {report.snapshot.slippage_ratio}",
            f"- **Total Observations**: {report.snapshot.total_observations}",
            f"- **Regime Signature**: {report.snapshot.current_regime_signature}"
        ]
        return "\n".join(lines)

    def _generate_drift_analysis(self, report: DriftReport) -> str:
        lines = ["# Drift Analysis\n"]
        for obs in report.observations:
            lines.append(f"- **{obs.drift_type.name}** (Severity: {obs.severity_score}): {obs.description}")
        return "\n".join(lines)

    def _generate_regime_drift(self, report: DriftReport) -> str:
        lines = ["# Regime Drift Analysis\n"]
        for obs in report.observations:
            if "REGIME" in obs.drift_type.name:
                lines.append(f"- {obs.description}")
        return "\n".join(lines)

    def _generate_execution_drift(self, report: DriftReport) -> str:
        lines = ["# Execution Drift Analysis\n"]
        for obs in report.observations:
            if "EXECUTION" in obs.drift_type.name:
                lines.append(f"- {obs.description}")
        return "\n".join(lines)

    def _generate_certification_status(self, report: DriftReport, lifecycle: CertificationLifecycle) -> str:
        state = lifecycle.get_state(report.strategy_id)
        history = lifecycle.get_history(report.strategy_id)
        lines = [
            f"# Certification Status for {report.strategy_id}\n",
            f"**Current State**: {state.name}\n\n",
            "**History**:"
        ]
        for trans in history:
            lines.append(f"- {trans.timestamp.isoformat()}: {trans.from_state.name} -> {trans.to_state.name} ({trans.reason})")
        return "\n".join(lines)

    def _generate_notifications(self, notification: NotificationRecord) -> str:
        lines = [
            f"# Notifications for {notification.strategy_id}\n",
            f"**Recommendation**: {notification.recommendation.name}\n\n",
            "**Reasons**:"
        ]
        for reason in notification.reasons:
            lines.append(f"- {reason}")
        return "\n".join(lines)

    def _generate_audit_log(self, audit_log: AuditLog) -> str:
        lines = ["# Audit Log\n"]
        for entry in audit_log.get_entries():
            lines.append(f"- **{entry.timestamp.isoformat()}** [{entry.event_type}]: {entry.details}")
        return "\n".join(lines)

    def _generate_limitations(self) -> str:
        return "# Limitations\n\n- Observations are limited by feed freshness.\n- Does not recompute any baseline statistics."

    def _generate_summary(self, report: DriftReport, notification: NotificationRecord, lifecycle: CertificationLifecycle) -> str:
        lines = [
            f"# Summary for {report.strategy_id}\n",
            f"- **Primary Drift**: {report.primary_drift.name}",
            f"- **Recommendation**: {notification.recommendation.name}",
            f"- **Lifecycle State**: {lifecycle.get_state(report.strategy_id).name}",
            "\n*The observed evidence currently differs from the certified baseline according to the configured drift policy.*"
        ]
        return "\n".join(lines)
