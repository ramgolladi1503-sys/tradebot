import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

from core.outcome_evidence.evidence_models import (
    OutcomeEvidenceRecord, MfeMaeEvidence, CostBreakdown, CostComponent,
    RegimeContextEvidence, ExecutionSimulation
)
from core.outcome_evidence.evidence_types import (
    EvidenceQuality, OutcomeStatus, ExitReason, CostModelStatus
)
from core.statistical_validation.validation_engine import ValidationEngine
from core.statistical_validation.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


def _parse_enum(enum_class, value: str):
    if value is None or value == "":
        raise ValueError(f"Missing required {enum_class.__name__} value")
    try:
        return enum_class(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {enum_class.__name__} value: {value!r}") from exc


def load_evidence_records(file_path: Path) -> List[OutcomeEvidenceRecord]:
    records: List[OutcomeEvidenceRecord] = []
    if not file_path.exists():
        raise FileNotFoundError(f"Evidence file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed evidence JSON at line {line_number}: {exc}") from exc

            mfe_mae_data = data.get("mfe_mae")
            mfe_mae = None
            if mfe_mae_data:
                mfe_mae = MfeMaeEvidence(
                    mfe_points=mfe_mae_data.get("mfe_points", 0.0),
                    mae_points=mfe_mae_data.get("mae_points", 0.0),
                    mfe_r=mfe_mae_data.get("mfe_r", 0.0),
                    mae_r=mfe_mae_data.get("mae_r", 0.0),
                    realized_r=mfe_mae_data.get("realized_r", 0.0),
                    max_drawdown=mfe_mae_data.get("max_drawdown", 0.0),
                    time_to_mfe=mfe_mae_data.get("time_to_mfe", 0.0),
                    time_to_mae=mfe_mae_data.get("time_to_mae", 0.0),
                    hold_duration=mfe_mae_data.get("hold_duration", 0.0),
                )

            cb_data = data.get("cost_breakdown", {})
            components = [
                CostComponent(
                    name=c_data.get("name", "unknown"),
                    value=c_data.get("value", 0.0),
                    source_origin=c_data.get("source_origin", ""),
                    is_estimated=c_data.get("is_estimated", True),
                    bid_ask_available=c_data.get("bid_ask_available", False),
                )
                for c_data in cb_data.get("components", [])
            ]
            cost_breakdown = CostBreakdown(
                components=components,
                total_cost=cb_data.get("total_cost", 0.0),
                lot_size=cb_data.get("lot_size", 1),
                status=_parse_enum(CostModelStatus, cb_data.get("status")),
            )

            rc_data = data.get("regime_context", {})
            regime_context = RegimeContextEvidence(
                trend=rc_data.get("trend"),
                range_status=rc_data.get("range_status"),
                entropy=rc_data.get("entropy"),
                volatility=rc_data.get("volatility"),
                iv_bucket=rc_data.get("iv_bucket"),
                session_bucket=rc_data.get("session_bucket"),
                is_expiry_day=rc_data.get("is_expiry_day"),
                liquidity_bucket=rc_data.get("liquidity_bucket"),
                spread_bucket=rc_data.get("spread_bucket"),
                mip_event_context=rc_data.get("mip_event_context"),
            )

            sim_data = data.get("simulation", {})
            simulation = ExecutionSimulation(
                entry_fill=sim_data.get("entry_fill", 0.0),
                exit_fill=sim_data.get("exit_fill", 0.0),
                spread_impact=sim_data.get("spread_impact", 0.0),
                slippage_impact=sim_data.get("slippage_impact", 0.0),
                delayed_entry=sim_data.get("delayed_entry", False),
                delayed_exit=sim_data.get("delayed_exit", False),
                is_hypothetical_rejected=sim_data.get("is_hypothetical_rejected", False),
            )

            records.append(OutcomeEvidenceRecord(
                run_id=data.get("run_id", "unknown"),
                candidate_id=data.get("candidate_id", "unknown"),
                strategy_id=data.get("strategy_id", "unknown"),
                input_source=data.get("input_source", "unknown"),
                evidence_quality=_parse_enum(EvidenceQuality, data.get("evidence_quality")),
                outcome_status=_parse_enum(OutcomeStatus, data.get("outcome_status")),
                exit_reason=_parse_enum(ExitReason, data.get("exit_reason")),
                mfe_mae=mfe_mae,
                cost_breakdown=cost_breakdown,
                gross_pnl=data.get("gross_pnl", 0.0),
                net_pnl=data.get("net_pnl", 0.0),
                regime_context=regime_context,
                simulation=simulation,
                warnings=data.get("warnings", []),
                created_timestamp=data.get("created_timestamp", 0.0),
            ))

    if not records:
        raise ValueError("Evidence file contains zero records")
    return records


def main():
    parser = argparse.ArgumentParser(description="Statistical Validation Engine")
    parser.add_argument("--evidence-file", type=str, required=True, help="Path to outcome_evidence.jsonl")
    parser.add_argument("--output-dir", type=str, default="docs/statistical_validation", help="Output directory for reports")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    try:
        records = load_evidence_records(Path(args.evidence_file))
        report = ValidationEngine().validate(records)
        ReportGenerator(output_dir=args.output_dir).generate(report)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("STATISTICAL_VALIDATION_INPUT_INVALID: %s", exc)
        return 1

    logger.info("Validation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
