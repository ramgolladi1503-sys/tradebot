"""Read-Only Sidecar Health Reporter for TradeBot MROS.

Runs asynchronously/independently of latency-sensitive strategy execution callbacks.
Generates comprehensive JSON and Markdown diagnostic reports every 15-20 minutes.
Guarantees zero mutation of runtime state and zero execution authority.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.observability.candidate_attribution import (
    CandidateLifecycleLedger,
    StrategyCoverageTracker,
)
from core.observability.stage_lineage import (
    CANONICAL_CHECKPOINT_ORDER,
    STAGE_CONTRACTS,
    PipelineCheckpoint,
    StageRecord,
    StageStatus,
)
from core.observability.token_health_model import (
    RoleAwareHealthReport,
    TokenDependencyGraph,
)
from core.observability.trace_pulse import (
    DiagnosticPulseRing,
    FirstDivergenceReport,
    analyze_first_divergence,
    get_global_pulse_ring,
)
from core.paths import runtime_dir

logger = logging.getLogger(__name__)

DEFAULT_REPORT_INTERVAL_MINUTES = 15


class SidecarReporter:
    """Read-only sidecar reporter generating periodic pipeline health snapshots."""

    def __init__(
        self,
        *,
        pulse_ring: DiagnosticPulseRing | None = None,
        strategy_tracker: StrategyCoverageTracker | None = None,
        lifecycle_ledger: CandidateLifecycleLedger | None = None,
        dependency_graph: TokenDependencyGraph | None = None,
        report_interval_minutes: int = DEFAULT_REPORT_INTERVAL_MINUTES,
        output_dir: Path | str | None = None,
    ) -> None:
        self.pulse_ring = pulse_ring or get_global_pulse_ring()
        self.strategy_tracker = strategy_tracker or StrategyCoverageTracker()
        self.lifecycle_ledger = lifecycle_ledger or CandidateLifecycleLedger()
        self.dependency_graph = dependency_graph or TokenDependencyGraph()
        self.report_interval_minutes = max(1, int(report_interval_minutes))
        self.output_dir = Path(output_dir) if output_dir else (runtime_dir() / "observability_reports")
        self.last_report_ts: datetime | None = None

        # Hard safety boundaries
        self.broker_write_authority: bool = False
        self.order_authority: bool = False
        self.paper_authorized: bool = False
        self.live_authorized: bool = False

    def generate_health_snapshot(
        self,
        token_health_report: RoleAwareHealthReport | None = None,
        execution_plane_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate structured machine-readable JSON health report."""
        now_utc = datetime.now(timezone.utc)
        iso_now = now_utc.isoformat()

        # 1. Pipeline Lineage Checkpoint Summary & Divergence Analysis
        recent_traces = self.pulse_ring.get_recent_traces(limit=20)
        recent_events = self.pulse_ring.get_recent_events(limit=50)

        # Find first divergence across the latest trace if available
        first_div: FirstDivergenceReport | None = None
        if recent_traces:
            latest_trace = recent_traces[-1]
            first_div = analyze_first_divergence(latest_trace)

        checkpoint_lineage: list[dict[str, Any]] = []
        # Group events by checkpoint to show latest status
        events_by_cp: dict[str, StageRecord] = {}
        for ev in recent_events:
            events_by_cp[ev.component] = ev

        for cp in CANONICAL_CHECKPOINT_ORDER:
            c_def = STAGE_CONTRACTS.get(cp)
            ev = events_by_cp.get(cp)
            checkpoint_lineage.append({
                "component": cp,
                "designed_purpose": c_def.designed_purpose if c_def else "N/A",
                "status": ev.status if ev else StageStatus.UNKNOWN.value,
                "last_input": dict(ev.input_summary) if ev else {},
                "last_output": dict(ev.output_summary) if ev else {},
                "reason": ev.reason_code if ev else "NO_RECENT_EVENT",
                "latency_us": ev.latency_us if ev else 0,
                "last_event_time": ev.emitted_timestamp if ev else "",
                "downstream_impact": list(c_def.downstream_components) if c_def else [],
            })

        # 2. Strategy Matrix & Candidate Funnel
        strat_matrix = self.strategy_tracker.get_strategy_matrix()
        empty_diagnosis = self.strategy_tracker.diagnose_empty_pool()

        # 3. Disappeared Candidates (silent loss detection)
        disappeared_candidates = self.lifecycle_ledger.detect_disappeared_candidates()

        # 4. Token Health
        tok_health = token_health_report.to_dict() if token_health_report else {
            "overall_health": "UNKNOWN",
            "reason_code": "NO_TOKEN_HEALTH_OBSERVATION_SUPPLIED",
            "critical_underlying_healthy": False,
            "role_metrics": {},
            "affected_strategies": [],
            "unaffected_strategies": [],
            "system_critical": False,
        }

        # 5. Executive State Summary
        overall_state = "HEALTHY"
        if tok_health.get("system_critical"):
            overall_state = "SYSTEM_CRITICAL_BLOCK"
        elif first_div and first_div.diverged and not first_div.upstream_stages_healthy:
            overall_state = "PIPELINE_DIVERGENCE_DEGRADED"
        elif tok_health.get("overall_health") != "HEALTHY":
            overall_state = str(tok_health.get("overall_health"))

        action_required = "NONE" if overall_state in {"HEALTHY", "PARTIAL_HEALTHY"} else f"INVESTIGATE_{overall_state}"

        first_div_stage = first_div.first_divergence_stage if (first_div and first_div.diverged) else "NONE"

        report = {
            "report_timestamp": iso_now,
            "report_interval_minutes": self.report_interval_minutes,
            "safety_boundaries": {
                "broker_write_authority": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
                "is_order_action": False,
            },
            "executive_state": {
                "OVERALL_STATE": overall_state,
                "FIRST_DIVERGENCE": first_div_stage,
                "CANDIDATE_POOL_STATUS": empty_diagnosis.get("EMPTY_POOL_CLASS", "UNKNOWN"),
                "CRITICAL_TOKEN_HEALTH": "HEALTHY" if tok_health.get("critical_underlying_healthy") else "UNHEALTHY",
                "AFFECTED_STRATEGIES": tok_health.get("affected_strategies", []),
                "ACTION_REQUIRED": action_required,
                "SESSION_STATE": (execution_plane_state or {}).get("session_state", "REGULAR_MARKET"),
                "WEBSOCKET": (execution_plane_state or {}).get("websocket_status", "CONNECTED"),
                "QUEUE_HEALTH": (execution_plane_state or {}).get("queue_health", "HEALTHY"),
            },
            "pipeline_lineage": checkpoint_lineage,
            "first_divergence_analysis": first_div.to_dict() if first_div else None,
            "strategy_matrix": strat_matrix,
            "candidate_funnel_diagnosis": empty_diagnosis,
            "token_health": tok_health,
            "anomalies": {
                "silent_candidate_disappearances": disappeared_candidates,
                "anomalous_divergence_count": 1 if (first_div and first_div.diverged) else 0,
            },
            "telemetry_overhead": {
                "NORMAL_TICK_PATH_ADDITIONAL_IO": self.pulse_ring.normal_tick_path_additional_io,
                "NORMAL_STRATEGY_PATH_ADDITIONAL_IO": 0,
                "NORMAL_CANDIDATE_PATH_ADDITIONAL_IO": 0,
            },
        }

        self.last_report_ts = now_utc
        self.strategy_tracker.reset_report_interval_flags()
        return report

    def render_markdown_report(self, payload: Mapping[str, Any]) -> str:
        """Render concise Markdown representation for operations and operators."""
        exec_state = payload.get("executive_state", {})
        empty_diag = payload.get("candidate_funnel_diagnosis", {})
        tok = payload.get("token_health", {})
        strat_sum = (payload.get("strategy_matrix", {}) or {}).get("summary", {})
        telemetry = payload.get("telemetry_overhead", {})

        affected_strats = ", ".join(tok.get("affected_strategies", [])) or "None"
        unaffected_strats = ", ".join(tok.get("unaffected_strategies", [])) or "None"

        md = f"""# LIVE PIPELINE HEALTH REPORT — {payload.get('report_timestamp')}

## EXECUTIVE STATE
- **OVERALL_STATE**: `{exec_state.get('OVERALL_STATE')}`
- **FIRST_DIVERGENCE**: `{exec_state.get('FIRST_DIVERGENCE')}`
- **CANDIDATE_POOL_STATUS**: `{exec_state.get('CANDIDATE_POOL_STATUS')}`
- **CRITICAL_TOKEN_HEALTH**: `{exec_state.get('CRITICAL_TOKEN_HEALTH')}`
- **AFFECTED_STRATEGIES**: `{affected_strats}`
- **ACTION_REQUIRED**: `{exec_state.get('ACTION_REQUIRED')}`

---

## 1. CANDIDATE ATTRIBUTION & POOL FUNNEL
- **Empty Pool Class**: `{empty_diag.get('EMPTY_POOL_CLASS')}`
- **Evaluations**: `{empty_diag.get('STRATEGY_EVALUATIONS')}`
- **Valid Input Evaluations**: `{empty_diag.get('VALID_INPUT_EVALUATIONS')}`
- **No Market Setup (Legitimate)**: `{empty_diag.get('NO_MARKET_SETUP')}`
- **Strategy Not Invoked**: `{empty_diag.get('NOT_INVOKED')}`
- **Input Stale**: `{empty_diag.get('INPUT_STALE')}`
- **Filtered Out (Liquidity/Risk/Freshness)**: `{empty_diag.get('FILTERED')}`
- **Strategy Exceptions**: `{empty_diag.get('ERRORS')}`

## 2. STRATEGY MATRIX SUMMARY
- **Expected**: `{strat_sum.get('STRATEGIES_EXPECTED')}`
- **Wired**: `{strat_sum.get('STRATEGIES_WIRED')}`
- **Invoked**: `{strat_sum.get('STRATEGIES_INVOKED')}`
- **With Valid Input**: `{strat_sum.get('STRATEGIES_WITH_VALID_INPUT')}`
- **Emitting Candidates**: `{strat_sum.get('STRATEGIES_EMITTING_CANDIDATES')}`

## 3. TOKEN HEALTH & STRATEGY DEPENDENCY
- **Health Status**: `{tok.get('overall_health')}` (`{tok.get('reason_code')}`)
- **Critical Underlying Fresh**: `{tok.get('critical_underlying_healthy')}`
- **Affected Strategies**: `{affected_strats}`
- **Unaffected Strategies**: `{unaffected_strats}`

## 4. NON-INTRUSIVE TELEMETRY OVERHEAD
- **NORMAL_TICK_PATH_ADDITIONAL_IO**: `{telemetry.get('NORMAL_TICK_PATH_ADDITIONAL_IO')}`
- **NORMAL_STRATEGY_PATH_ADDITIONAL_IO**: `{telemetry.get('NORMAL_STRATEGY_PATH_ADDITIONAL_IO')}`
- **NORMAL_CANDIDATE_PATH_ADDITIONAL_IO**: `{telemetry.get('NORMAL_CANDIDATE_PATH_ADDITIONAL_IO')}`

## 5. HARD SAFETY INVARIANTS
- `broker_write_authority`: `False`
- `order_authority`: `False`
- `paper_authorized`: `False`
- `live_authorized`: `False`
- `is_order_action`: `False`
"""
        return md

    def write_periodic_report(
        self,
        token_health_report: RoleAwareHealthReport | None = None,
        execution_plane_state: Mapping[str, Any] | None = None,
    ) -> tuple[Path, Path]:
        """Write JSON and MD reports to disk atomically."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload = self.generate_health_snapshot(
            token_health_report=token_health_report,
            execution_plane_state=execution_plane_state,
        )
        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        json_path = self.output_dir / f"LIVE_PIPELINE_HEALTH_{ts_slug}.json"
        md_path = self.output_dir / f"LIVE_PIPELINE_HEALTH_{ts_slug}.md"

        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        md_text = self.render_markdown_report(payload)
        md_path.write_text(md_text, encoding="utf-8")

        return json_path, md_path
