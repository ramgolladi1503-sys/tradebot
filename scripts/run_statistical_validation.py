from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_pipeline_mode(args: argparse.Namespace) -> int:
    from core.strategy_pipeline.adapter_runtime import (
        AdapterRuntimeError,
        PipelineAdapterRuntime,
    )
    from core.strategy_pipeline.pipeline_models import EngineType
    from core.strategy_pipeline.statistics_stage_adapter import (
        StatisticsStageError,
        run_statistics_stage,
    )

    try:
        runtime = PipelineAdapterRuntime.from_environment(
            EngineType.STATISTICS,
            repo_root=REPO_ROOT,
        )
    except AdapterRuntimeError as exc:
        print(f"STATISTICS_ADAPTER_RUNTIME_INVALID:{exc}", file=sys.stderr)
        return 2

    if not args.validation_config:
        result = runtime.write_blocked(
            verdict="STATISTICS_STAGE_BLOCKED",
            blockers=["validation_config_required_in_pipeline_mode"],
        )
    else:
        try:
            result = run_statistics_stage(
                runtime,
                validation_config_file=args.validation_config,
            )
        except (StatisticsStageError, ValueError) as exc:
            result = runtime.write_blocked(
                verdict="STATISTICS_STAGE_BLOCKED",
                blockers=[str(exc)],
            )

    print(
        json.dumps(
            {
                "engine": result.engine.value,
                "state": result.state.value,
                "strategy_id": result.strategy_id,
                "run_id": result.run_id,
                "verdict": result.verdict,
                "result_manifest": result.manifest_path,
                "blockers": result.blockers,
            },
            sort_keys=True,
        )
    )
    return 0


def _parse_enum(enum_class, value: str):
    if not value:
        raise ValueError(f"missing enum value for {enum_class.__name__}")
    return enum_class(value)


def load_evidence_records(file_path: Path) -> List[object]:
    from core.outcome_evidence.evidence_models import (
        CostBreakdown,
        CostComponent,
        ExecutionSimulation,
        MfeMaeEvidence,
        OutcomeEvidenceRecord,
        RegimeContextEvidence,
    )
    from core.outcome_evidence.evidence_types import (
        CostModelStatus,
        EvidenceQuality,
        ExitReason,
        OutcomeStatus,
    )

    records: List[OutcomeEvidenceRecord] = []
    if not file_path.exists():
        return records
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            data = json.loads(line)
            mfe_data = data.get("mfe_mae")
            mfe_mae = None
            if mfe_data:
                mfe_mae = MfeMaeEvidence(
                    mfe_points=mfe_data.get("mfe_points", 0.0),
                    mae_points=mfe_data.get("mae_points", 0.0),
                    mfe_r=mfe_data.get("mfe_r", 0.0),
                    mae_r=mfe_data.get("mae_r", 0.0),
                    realized_r=mfe_data.get("realized_r", 0.0),
                    max_drawdown=mfe_data.get("max_drawdown", 0.0),
                    time_to_mfe=mfe_data.get("time_to_mfe", 0.0),
                    time_to_mae=mfe_data.get("time_to_mae", 0.0),
                    hold_duration=mfe_data.get("hold_duration", 0.0),
                )
            cost_data = data.get("cost_breakdown", {})
            components = [
                CostComponent(
                    name=item.get("name", "unknown"),
                    value=item.get("value", 0.0),
                    source_origin=item.get("source_origin", ""),
                    is_estimated=item.get("is_estimated", True),
                    bid_ask_available=item.get("bid_ask_available", False),
                )
                for item in cost_data.get("components", [])
            ]
            cost_breakdown = CostBreakdown(
                components=components,
                total_cost=cost_data.get("total_cost", 0.0),
                lot_size=cost_data.get("lot_size", 1),
                status=_parse_enum(
                    CostModelStatus,
                    cost_data.get("status", "INCOMPLETE"),
                ),
            )
            regime_data = data.get("regime_context", {})
            regime_context = RegimeContextEvidence(
                trend=regime_data.get("trend"),
                range_status=regime_data.get("range_status"),
                entropy=regime_data.get("entropy"),
                volatility=regime_data.get("volatility"),
                iv_bucket=regime_data.get("iv_bucket"),
                session_bucket=regime_data.get("session_bucket"),
                is_expiry_day=regime_data.get("is_expiry_day"),
                liquidity_bucket=regime_data.get("liquidity_bucket"),
                spread_bucket=regime_data.get("spread_bucket"),
                mip_event_context=regime_data.get("mip_event_context"),
            )
            simulation_data = data.get("simulation", {})
            simulation = ExecutionSimulation(
                entry_fill=simulation_data.get("entry_fill", 0.0),
                exit_fill=simulation_data.get("exit_fill", 0.0),
                spread_impact=simulation_data.get("spread_impact", 0.0),
                slippage_impact=simulation_data.get("slippage_impact", 0.0),
                delayed_entry=simulation_data.get("delayed_entry", False),
                delayed_exit=simulation_data.get("delayed_exit", False),
                is_hypothetical_rejected=simulation_data.get(
                    "is_hypothetical_rejected",
                    False,
                ),
            )
            records.append(
                OutcomeEvidenceRecord(
                    run_id=data.get("run_id", "unknown"),
                    candidate_id=data.get("candidate_id", "unknown"),
                    strategy_id=data.get("strategy_id", "unknown"),
                    input_source=data.get("input_source", "unknown"),
                    evidence_quality=_parse_enum(
                        EvidenceQuality,
                        data.get("evidence_quality", "UNUSABLE"),
                    ),
                    outcome_status=_parse_enum(
                        OutcomeStatus,
                        data.get("outcome_status", "PENDING"),
                    ),
                    exit_reason=_parse_enum(
                        ExitReason,
                        data.get("exit_reason", "UNKNOWN"),
                    ),
                    mfe_mae=mfe_mae,
                    cost_breakdown=cost_breakdown,
                    gross_pnl=data.get("gross_pnl", 0.0),
                    net_pnl=data.get("net_pnl", 0.0),
                    regime_context=regime_context,
                    simulation=simulation,
                    warnings=data.get("warnings", []),
                    created_timestamp=data.get("created_timestamp", 0.0),
                )
            )
    return records


def _run_legacy_mode(args: argparse.Namespace) -> int:
    from core.statistical_validation.report_generator import ReportGenerator
    from core.statistical_validation.validation_engine import ValidationEngine

    if not args.evidence_file:
        print("Evidence file is required outside pipeline mode", file=sys.stderr)
        return 2
    file_path = Path(args.evidence_file)
    if not file_path.exists():
        logging.error("Evidence file not found: %s", file_path)
        return 1
    records = load_evidence_records(file_path)
    report = ValidationEngine().validate(records)
    ReportGenerator(output_dir=args.output_dir).generate(report)
    logging.info("Validation complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Statistical Validation Engine")
    parser.add_argument("--evidence-file")
    parser.add_argument("--validation-config")
    parser.add_argument(
        "--output-dir",
        default="docs/statistical_validation",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if os.environ.get("TRADEBOT_PIPELINE_RESULT_MANIFEST"):
        return _run_pipeline_mode(args)
    return _run_legacy_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
