from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from config import config as cfg
from core.cost_gate import run_cost_gate
from core.events import append_event, events_path, read_events, write_json_atomic
from core.health_scenarios import run_golden_path
from core.paths import logs_dir
from core.reconciliation_project_from_events import build_recon, recon_path
from core.time_utils import utc_now
from dashboard.loader_adapters import (
    load_depth_status,
    load_execution_analytics,
    load_reconciliation_summary,
)


_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

_LOG_SEG = "logs"
_DATA_SEG = "data"
_FORBIDDEN_PATTERNS = (
    f'Path("{_LOG_SEG}/',
    f"Path('{_LOG_SEG}/",
    f'pathlib.Path("{_LOG_SEG}/',
    f"pathlib.Path('{_LOG_SEG}/",
    f'Path("{_DATA_SEG}/',
    f"Path('{_DATA_SEG}/",
    f'pathlib.Path("{_DATA_SEG}/',
    f"pathlib.Path('{_DATA_SEG}/",
)

_ALLOWED_HINTS = (
    "logs_dir(",
    "cfg.TRADE_DB_PATH",
    "resolve_trade_log_path(",
    "ensure_trade_log_file(",
    "core.paths.",
    "# ALLOW_HARDCODE_PATH",
)


def _issue(code: str, priority: str, message: str, evidence: dict[str, Any], fix_hint: str) -> dict[str, Any]:
    return {
        "code": code,
        "priority": priority,
        "message": message,
        "evidence": evidence,
        "fix_hint": fix_hint,
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_target_files() -> list[Path]:
    root = _project_root()
    files: list[Path] = []
    files.extend(sorted((root / "dashboard").rglob("*.py")))
    files.extend(
        [
            root / "scripts" / "arm_trade.py",
            root / "scripts" / "reconcile_fills.py",
            root / "scripts" / "run_execution_analytics.py",
            root / "core" / "events.py",
            root / "core" / "health_scenarios.py",
            root / "core" / "feed" / "sim_feed.py",
            root / "core" / "broker" / "mock_broker.py",
            root / "core" / "reconciliation_project_from_events.py",
        ]
    )
    return [p for p in files if p.exists()]


def _next_doc_state(line: str, in_doc: bool, delim: str | None) -> tuple[bool, str | None]:
    quote_patterns = ("'''", '"""')
    if in_doc and delim is not None:
        if delim in line and line.count(delim) % 2 == 1:
            return False, None
        return True, delim
    for candidate in quote_patterns:
        if candidate not in line:
            continue
        if line.count(candidate) % 2 == 1:
            return True, candidate
    return False, None


def _path_contract_violations() -> list[dict[str, Any]]:
    root = _project_root()
    violations: list[dict[str, Any]] = []
    for file_path in _iter_target_files():
        in_doc = False
        delim: str | None = None
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            next_in_doc, next_delim = _next_doc_state(line, in_doc, delim)

            if not in_doc and stripped.startswith("#"):
                in_doc, delim = next_in_doc, next_delim
                continue
            if in_doc:
                in_doc, delim = next_in_doc, next_delim
                continue
            if any(hint in line for hint in _ALLOWED_HINTS):
                in_doc, delim = next_in_doc, next_delim
                continue
            if any(pattern in line for pattern in _FORBIDDEN_PATTERNS):
                violations.append(
                    {
                        "file": str(file_path.relative_to(root)),
                        "line": line_no,
                        "text": stripped[:200],
                    }
                )
            in_doc, delim = next_in_doc, next_delim
    return violations


def _write_execution_analytics_stub(run_id: str, recon: dict[str, Any]) -> Path:
    path = logs_dir() / "execution_analytics.json"
    payload = {
        "status": "ok" if recon.get("trade_count", 0) > 0 else "empty",
        "run_id": run_id,
        "trade_count": int(recon.get("trade_count") or 0),
        "symbols": list(recon.get("symbols") or []),
        "generated_ts": utc_now().isoformat().replace("+00:00", "Z"),
    }
    write_json_atomic(path, payload)
    return path


def _render_report_md(report: dict[str, Any]) -> str:
    lines = [
        "# Health Gate Report",
        "",
        f"- desk: {report.get('desk')}",
        f"- strict: {report.get('strict')}",
        f"- run_id: {report.get('run_id')}",
        f"- pass: {report.get('pass')}",
        f"- exit_code: {report.get('exit_code')}",
        "",
        "## Checks",
    ]
    for check in report.get("checks", []):
        lines.append(f"- {check}")
    lines.append("")
    lines.append("## Issues")
    issues = report.get("issues", [])
    if not issues:
        lines.append("- none")
    else:
        for item in issues:
            lines.append(
                f"- [{item.get('priority')}] {item.get('code')}: {item.get('message')}"
            )
            lines.append(f"  - evidence: {json.dumps(item.get('evidence', {}), ensure_ascii=True)}")
            lines.append(f"  - fix_hint: {item.get('fix_hint')}")
    lines.append("")
    lines.append(f"Artifacts: {report.get('artifacts')}")
    return "\n".join(lines) + "\n"


def _write_text_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path


def run_health_gate(
    *,
    desk: str,
    strict: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    issue_list: list[dict[str, Any]] = []
    checks: list[str] = []

    active_run_id = str(
        run_id
        or f"health_gate_{str(desk or 'DEFAULT').upper()}_{utc_now().strftime('%Y%m%dT%H%M%S')}"
    )

    violations = _path_contract_violations()
    if violations:
        issue_list.append(
            _issue(
                "PATH_CONTRACT_P0",
                "P0",
                "Hardcoded repo-relative logs/data paths detected in critical files.",
                {"violations": violations[:50]},
                "Replace hardcoded paths with logs_dir(), cfg.TRADE_DB_PATH, or trade_log path helpers.",
            )
        )
    checks.append("path_contract")

    scenario = run_golden_path(str(desk or "DEFAULT"), run_id=active_run_id)
    if not bool(scenario.get("ok")):
        issue_list.append(
            _issue(
                "GOLDEN_PATH_P0",
                "P0",
                "Golden-path deterministic trade failed.",
                {"scenario": scenario},
                "Fix synthetic feed/mock broker wiring and ensure deterministic fill price resolution.",
            )
        )
    checks.append("golden_path_trade")

    events = read_events(run_id=active_run_id)
    intent_count = sum(1 for row in events if row.get("type") == "trade_intent_created")
    submit_count = sum(1 for row in events if row.get("type") == "order_submitted")
    fill_count = sum(1 for row in events if row.get("type") == "fill")
    if intent_count != 1 or submit_count != 1 or fill_count != 1:
        issue_list.append(
            _issue(
                "EVENT_INTEGRITY_P0",
                "P0",
                "Event stream integrity failed for health-gate run.",
                {
                    "run_id": active_run_id,
                    "intent_count": intent_count,
                    "submit_count": submit_count,
                    "fill_count": fill_count,
                    "events_path": str(events_path()),
                },
                "Ensure a single deterministic trade emits exactly one intent, one submission, and one fill event.",
            )
        )
    checks.append("event_integrity")

    recon = build_recon(events)
    write_json_atomic(recon_path(), recon)
    if int(recon.get("trade_count") or 0) != 1:
        issue_list.append(
            _issue(
                "RECON_PROJECTION_P0",
                "P0",
                "Reconciliation projection did not produce exactly one trade.",
                {"run_id": active_run_id, "recon": recon},
                "Fix event-to-reconciliation projection for fill events.",
            )
        )
    checks.append("recon_projection")

    _write_execution_analytics_stub(active_run_id, recon)
    try:
        ea = load_execution_analytics()
        rc = load_reconciliation_summary()
        depth = load_depth_status(db_path=getattr(cfg, "TRADE_DB_PATH", None))
        if str(depth.get("status") or "") == "empty" and "db_path" not in depth:
            issue_list.append(
                _issue(
                    "DASHBOARD_DEPTH_P1",
                    "P1",
                    "Depth loader returned empty state without DB path evidence.",
                    {"depth": depth},
                    "Include db_path in empty depth responses for operator diagnostics.",
                )
            )
        if str(rc.get("status") or "") == "missing":
            issue_list.append(
                _issue(
                    "DASHBOARD_RECON_P0",
                    "P0",
                    "Dashboard reconciliation loader cannot find canonical recon artifact.",
                    {"recon_loader": rc},
                    "Ensure recon.json is written under logs_dir() and loader points to that path.",
                )
            )
        if str(ea.get("status") or "") == "missing":
            issue_list.append(
                _issue(
                    "DASHBOARD_EXEC_ANALYTICS_P0",
                    "P0",
                    "Dashboard execution analytics loader cannot find canonical artifact.",
                    {"execution_loader": ea},
                    "Ensure execution_analytics.json is generated under logs_dir().",
                )
            )
    except Exception as exc:
        issue_list.append(
            _issue(
                "DASHBOARD_READ_P0",
                "P0",
                "Dashboard loader adapter validation failed.",
                {"error": str(exc)},
                "Fix parsing and canonical-path wiring in dashboard loader adapters.",
            )
        )
    checks.append("dashboard_read")

    cost_gate_enabled = bool(getattr(cfg, "COST_GATE_ENABLED", False))
    env_cost_gate = os.getenv("COST_GATE_ENABLED")
    if env_cost_gate is not None:
        cost_gate_enabled = str(env_cost_gate).strip().lower() in {"1", "true", "yes", "on"}

    if cost_gate_enabled:
        try:
            cost_status, cost_details = run_cost_gate(str(desk or "DEFAULT"))
            if str(cost_status).upper() != "PASS":
                issue_list.append(
                    _issue(
                        "COST_GATE_P0" if strict else "COST_GATE_P1",
                        "P0" if strict else "P1",
                        "Edge-after-cost readiness gate failed.",
                        {
                            "status": cost_status,
                            "breaches": list(cost_details.get("breaches") or []),
                            "totals": dict(cost_details.get("totals") or {}),
                            "report_json_path": cost_details.get("report_json_path"),
                            "report_md_path": cost_details.get("report_md_path"),
                        },
                        "Reduce spread/slippage/reject drivers before enabling strict execution readiness.",
                    )
                )
        except Exception as exc:
            issue_list.append(
                _issue(
                    "COST_GATE_ERROR_P0" if strict else "COST_GATE_ERROR_P1",
                    "P0" if strict else "P1",
                    "Cost gate check failed with exception.",
                    {"error": str(exc)},
                    "Fix cost sensitivity pipeline and rerun health gate.",
                )
            )
        checks.append("cost_gate")

    issue_list.sort(key=lambda row: (_PRIORITY_RANK.get(str(row.get("priority")), 99), str(row.get("code"))))

    has_p0 = any(str(item.get("priority")) == "P0" for item in issue_list)
    if has_p0:
        exit_code = 2
    elif issue_list and strict:
        exit_code = 1
    else:
        exit_code = 0

    report = {
        "desk": str(desk or "DEFAULT"),
        "strict": bool(strict),
        "run_id": active_run_id,
        "pass": exit_code == 0,
        "exit_code": exit_code,
        "checks": checks,
        "issues": issue_list,
        "artifacts": {
            "events": str(events_path()),
            "recon": str(recon_path()),
            "execution_analytics": str(logs_dir() / "execution_analytics.json"),
            "cost_kpis_json": str(logs_dir() / "cost_kpis.json"),
            "cost_kpis_md": str(logs_dir() / "cost_kpis.md"),
        },
    }

    report_json = logs_dir() / "health_gate_report.json"
    report_md = logs_dir() / "health_gate_report.md"
    write_json_atomic(report_json, report)
    _write_text_atomic(report_md, _render_report_md(report))
    report["report_json_path"] = str(report_json)
    report["report_md_path"] = str(report_md)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic offline health gate")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    report = run_health_gate(desk=str(args.desk), strict=bool(args.strict))
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"health_gate wrote: {report.get('report_json_path')} {report.get('report_md_path')}")
    return int(report.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
