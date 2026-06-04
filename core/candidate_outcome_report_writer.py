from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from core.candidate_outcome_fixture_loader import (
    CandidateOutcomeFixture,
    load_candidate_outcome_fixtures,
)
from core.candidate_outcome_truth import CandidateOutcomeTruth, build_candidate_outcome_truth


CANDIDATE_OUTCOME_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CandidateOutcomeReport:
    schema_version: int
    generated_by: str
    fixture_count: int
    status_counts: dict[str, int]
    results: tuple[dict[str, object], ...]
    safety: dict[str, object]
    read_only: bool = True
    append: bool = False

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False


def _safety_block() -> dict[str, object]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
        "closed_environment": True,
        "runtime_wired": False,
        "external_services_used": False,
        "proves_trading_edge": False,
    }


def _result_row(fixture: CandidateOutcomeFixture, truth: CandidateOutcomeTruth) -> dict[str, object]:
    payload = truth.to_payload()
    expected_status = fixture.expected_outcome_status
    return {
        "fixture_id": fixture.fixture_id,
        "candidate_id": payload.get("candidate_id"),
        "trade_id": payload.get("trade_id"),
        "symbol": payload.get("symbol"),
        "index": payload.get("index"),
        "strategy_family": payload.get("strategy_family"),
        "regime": payload.get("regime"),
        "expiry_type": payload.get("expiry_type"),
        "expected_outcome_status": expected_status,
        "outcome_status": payload.get("outcome_status"),
        "expected_matches_actual": expected_status == payload.get("outcome_status"),
        "gross_r": payload.get("gross_r"),
        "cost_adjusted_r": payload.get("cost_adjusted_r"),
        "mfe_abs": payload.get("mfe_abs"),
        "mae_abs": payload.get("mae_abs"),
        "first_hit_epoch": payload.get("first_hit_epoch"),
        "observation_count": payload.get("observation_count"),
        "read_only": payload.get("read_only"),
        "append": payload.get("append"),
        "is_order_action": payload.get("is_order_action"),
        "broker_api_called": payload.get("broker_api_called"),
        "live_order_allowed": payload.get("live_order_allowed"),
        "live_order_action": payload.get("live_order_action"),
        "broker_order_action": payload.get("broker_order_action"),
    }


def build_candidate_outcome_report(fixture_dir: str | Path) -> CandidateOutcomeReport:
    fixtures = sorted(load_candidate_outcome_fixtures(fixture_dir), key=lambda item: item.fixture_id)
    results = []
    status_counts: dict[str, int] = {}
    for fixture in fixtures:
        truth = build_candidate_outcome_truth(fixture.candidate, fixture.observations)
        row = _result_row(fixture, truth)
        results.append(row)
        status = str(row["outcome_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return CandidateOutcomeReport(
        schema_version=CANDIDATE_OUTCOME_REPORT_SCHEMA_VERSION,
        generated_by="candidate_outcome_report_writer",
        fixture_count=len(fixtures),
        status_counts=dict(sorted(status_counts.items())),
        results=tuple(results),
        safety=_safety_block(),
    )


def report_to_payload(report: CandidateOutcomeReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "generated_by": report.generated_by,
        "fixture_count": report.fixture_count,
        "status_counts": dict(sorted(report.status_counts.items())),
        "results": [dict(row) for row in report.results],
        "safety": dict(report.safety),
        "read_only": report.read_only,
        "append": report.append,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def write_candidate_outcome_json_report(report: CandidateOutcomeReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_payload(report), indent=2, sort_keys=True) + "\n")
    return path


def _markdown_table(rows: tuple[dict[str, object], ...]) -> str:
    headers = ["fixture_id", "outcome_status", "expected_outcome_status", "expected_matches_actual", "gross_r", "cost_adjusted_r"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row.get(column, "")) for column in headers
            )
            + " |"
        )
    return "\n".join(lines)


def write_candidate_outcome_markdown_report(report: CandidateOutcomeReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Candidate Outcome Report",
        "",
        f"- Schema version: {report.schema_version}",
        f"- Generated by: {report.generated_by}",
        f"- Fixture count: {report.fixture_count}",
        "",
        "## Safety",
    ]
    for key, value in report.safety.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Status Counts",
        ]
    )
    for key, value in sorted(report.status_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Fixture Results",
            "",
            _markdown_table(report.results),
            "",
            "This report does not prove trading edge.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def write_candidate_outcome_reports(
    fixture_dir: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    report = build_candidate_outcome_report(fixture_dir)
    output_root = Path(output_dir)
    json_path = write_candidate_outcome_json_report(report, output_root / "candidate_outcome_report.json")
    markdown_path = write_candidate_outcome_markdown_report(report, output_root / "candidate_outcome_report.md")
    return json_path, markdown_path


__all__ = [
    "CANDIDATE_OUTCOME_REPORT_SCHEMA_VERSION",
    "CandidateOutcomeReport",
    "build_candidate_outcome_report",
    "report_to_payload",
    "write_candidate_outcome_json_report",
    "write_candidate_outcome_markdown_report",
    "write_candidate_outcome_reports",
]
