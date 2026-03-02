from __future__ import annotations

import argparse
import importlib
import json
import os
import warnings
from pathlib import Path
from typing import Any

from config import config as cfg
from core.cost_gate import run_cost_gate
from core.events import append_event, read_events, write_json_atomic
from core.freshness_sla import get_freshness_status
from core.health_gate import run_health_gate
from core.paths import logs_dir
from core.reconciliation_project_from_events import build_recon
from core.runtime_lifecycle import lifecycle
from core.time_utils import utc_now


_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_LOG_SEG = "logs"
_DATA_SEG = "data"
_RUNTIME_SEG = "runtime"
_FORBIDDEN_PATTERNS = (
    f'Path("{_LOG_SEG}"',
    f"Path('{_LOG_SEG}'",
    f'Path("{_DATA_SEG}"',
    f"Path('{_DATA_SEG}'",
    f'"{_LOG_SEG}/',
    f"'{_LOG_SEG}/",
    f'"{_DATA_SEG}/',
    f"'{_DATA_SEG}/",
    f'".{_RUNTIME_SEG}/{_LOG_SEG}',
    f"'.{_RUNTIME_SEG}/{_LOG_SEG}",
    f'"{_RUNTIME_SEG}/{_LOG_SEG}',
    f"'{_RUNTIME_SEG}/{_LOG_SEG}",
)
_ALLOW_HINTS = (
    "logs_dir(",
    "cfg.TRADE_DB_PATH",
    "resolve_trade_log_path(",
    "ensure_trade_log_file(",
    "core.paths.",
    "# ALLOW_HARDCODE_PATH",
)
_SCAN_DIRS = ("core", "dashboard", "scripts", "runtime", "tools", "strategies")


def _issue(code: str, severity: str, message: str, evidence: dict[str, Any], fix_hint: str) -> dict[str, Any]:
    return {
        "code": str(code),
        "severity": str(severity),
        "message": str(message),
        "evidence": dict(evidence or {}),
        "fix_hint": str(fix_hint),
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_python_files() -> list[Path]:
    root = _project_root()
    out: list[Path] = []
    for folder in _SCAN_DIRS:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in {"tests", "docs"} for part in path.parts):
                continue
            out.append(path)
    return sorted(out)


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


def scan_canonical_path_violations() -> list[dict[str, Any]]:
    root = _project_root()
    violations: list[dict[str, Any]] = []
    for file_path in _iter_python_files():
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
            if any(hint in line for hint in _ALLOW_HINTS):
                in_doc, delim = next_in_doc, next_delim
                continue
            if any(pattern in line for pattern in _FORBIDDEN_PATTERNS):
                violations.append(
                    {
                        "file": str(file_path.relative_to(root)),
                        "line": int(line_no),
                        "text": stripped[:220],
                    }
                )
            in_doc, delim = next_in_doc, next_delim
    return violations


def scan_open_incidents() -> dict[str, Any]:
    import core.incidents as incidents

    incidents_path = Path(getattr(incidents, "INCIDENTS_PATH", logs_dir() / "incidents.jsonl"))
    open_incidents: dict[str, dict[str, Any]] = {}
    closed_ids: set[str] = set()
    if incidents_path.exists():
        for line in incidents_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            incident_id = str(row.get("incident_id") or "").strip()
            if not incident_id:
                continue
            if row.get("resolution") is not None:
                closed_ids.add(incident_id)
                open_incidents.pop(incident_id, None)
                continue
            if row.get("code") is not None or row.get("sev") is not None:
                open_incidents[incident_id] = {
                    "incident_id": incident_id,
                    "sev": row.get("sev"),
                    "code": row.get("code"),
                }
    for closed_id in closed_ids:
        open_incidents.pop(closed_id, None)
    return {
        "path": str(incidents_path),
        "open_incidents": list(open_incidents.values()),
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Go-Live Scorecard",
        "",
        f"- desk: {report.get('desk_id')}",
        f"- status: {report.get('status')}",
        f"- generated_ts: {report.get('generated_ts')}",
        "",
        "## Failures (P0)",
    ]
    failures = list(report.get("failures") or [])
    if not failures:
        lines.append("- none")
    else:
        for item in failures:
            lines.append(f"- [{item.get('severity')}] {item.get('code')}: {item.get('message')}")
            lines.append(f"  - evidence: {json.dumps(item.get('evidence', {}), ensure_ascii=True)}")
            lines.append(f"  - fix_hint: {item.get('fix_hint')}")
    lines.append("")
    lines.append("## Warnings (P1)")
    warnings_rows = list(report.get("warnings") or [])
    if not warnings_rows:
        lines.append("- none")
    else:
        for item in warnings_rows:
            lines.append(f"- [{item.get('severity')}] {item.get('code')}: {item.get('message')}")
            lines.append(f"  - evidence: {json.dumps(item.get('evidence', {}), ensure_ascii=True)}")
            lines.append(f"  - fix_hint: {item.get('fix_hint')}")
    lines.append("")
    lines.append(f"Artifacts: {json.dumps(report.get('artifacts', {}), ensure_ascii=True)}")
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


class GoLiveScorecard:
    def run(self, desk_id: str) -> dict[str, Any]:
        desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
        probe_run_id = f"go_live_score_{desk}_{utc_now().strftime('%Y%m%dT%H%M%S')}"
        failures: list[dict[str, Any]] = []
        warnings_rows: list[dict[str, Any]] = []

        # P0: health gate strict must pass.
        health = run_health_gate(desk=desk, strict=True)
        if int(health.get("exit_code") or 0) != 0:
            failures.append(
                _issue(
                    "HEALTH_GATE_STRICT_P0",
                    "P0",
                    "core.health_gate strict check failed.",
                    {
                        "exit_code": int(health.get("exit_code") or 0),
                        "report_json_path": health.get("report_json_path"),
                        "report_md_path": health.get("report_md_path"),
                    },
                    "Fix all health gate issues before arming LIVE execution.",
                )
            )

        # P0: lifecycle must not have active managed threads before arming.
        active_threads = list(lifecycle.active_thread_names())
        if active_threads:
            failures.append(
                _issue(
                    "LIFECYCLE_ACTIVE_THREADS_P0",
                    "P0",
                    "Managed runtime threads are still active.",
                    {"active_threads": active_threads},
                    "Stop active daemons and rerun go-live checks.",
                )
            )

        # P0: canonical path hardening check.
        path_violations = scan_canonical_path_violations()
        if path_violations:
            failures.append(
                _issue(
                    "CANONICAL_PATHS_P0",
                    "P0",
                    "Hardcoded logs/data path usage detected.",
                    {"violations": path_violations[:50]},
                    "Replace hardcoded paths with core.paths and trade_log path helpers.",
                )
            )

        # P0: events stream write/read.
        try:
            append_event("go_live_scorecard_probe", {"run_id": probe_run_id, "desk_id": desk})
            probe_rows = read_events(event_type="go_live_scorecard_probe", run_id=probe_run_id)
            if not probe_rows:
                failures.append(
                    _issue(
                        "EVENT_STREAM_RW_P0",
                        "P0",
                        "Events stream probe write/read failed.",
                        {"run_id": probe_run_id, "events_count": 0},
                        "Fix events.jsonl write/read permissions and schema handling.",
                    )
                )
        except Exception as exc:
            failures.append(
                _issue(
                    "EVENT_STREAM_RW_P0",
                    "P0",
                    "Events stream probe write/read failed with exception.",
                    {"run_id": probe_run_id, "error": str(exc)},
                    "Fix events stream I/O before arming LIVE execution.",
                )
            )

        # P0: reconciliation projection from events.
        try:
            append_event(
                "fill",
                {
                    "order_id": f"GLS-{probe_run_id}",
                    "trade_id": f"GLS-TRADE-{probe_run_id}",
                    "symbol": "NIFTY",
                    "side": "BUY",
                    "qty": 1,
                    "price": 100.0,
                    "run_id": probe_run_id,
                    "desk_id": desk,
                    "mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                },
            )
            probe_events = read_events(run_id=probe_run_id)
            recon = build_recon(probe_events)
            if int(recon.get("trade_count") or 0) <= 0:
                failures.append(
                    _issue(
                        "RECON_PROJECTION_P0",
                        "P0",
                        "Reconciliation projection did not produce trades.",
                        {"run_id": probe_run_id, "recon": recon},
                        "Fix event-to-reconciliation projection for fill events.",
                    )
                )
        except Exception as exc:
            failures.append(
                _issue(
                    "RECON_PROJECTION_P0",
                    "P0",
                    "Reconciliation projection failed with exception.",
                    {"run_id": probe_run_id, "error": str(exc)},
                    "Fix reconciliation projection pipeline before arming LIVE execution.",
                )
            )

        # P0: feed freshness should be OK during market-open windows.
        try:
            freshness = get_freshness_status(force=False)
            if bool(freshness.get("market_open")) and not bool(freshness.get("ok")):
                failures.append(
                    _issue(
                        "FEED_FRESHNESS_P0",
                        "P0",
                        "Feed freshness is not OK during market open.",
                        {
                            "state": freshness.get("state"),
                            "reasons": freshness.get("reasons"),
                            "ltp_age_sec": (freshness.get("ltp") or {}).get("age_sec"),
                            "depth_age_sec": (freshness.get("depth") or {}).get("age_sec"),
                        },
                        "Fix feed freshness and depth staleness before LIVE arming.",
                    )
                )
        except Exception as exc:
            failures.append(
                _issue(
                    "FEED_FRESHNESS_P0",
                    "P0",
                    "Feed freshness check failed with exception.",
                    {"error": str(exc)},
                    "Fix freshness SLA path to guarantee deterministic health checks.",
                )
            )

        # P0: open incidents should block go-live.
        try:
            incident_scan = scan_open_incidents()
            open_incidents = list(incident_scan.get("open_incidents") or [])
            if open_incidents:
                failures.append(
                    _issue(
                        "OPEN_INCIDENTS_P0",
                        "P0",
                        "Open incidents detected in incidents log.",
                        {
                            "path": str(incident_scan.get("path") or ""),
                            "open_incidents": open_incidents[:20],
                        },
                        "Resolve or explicitly close incidents before LIVE arming.",
                    )
                )
        except Exception as exc:
            failures.append(
                _issue(
                    "OPEN_INCIDENTS_P0",
                    "P0",
                    "Incident scan failed with exception.",
                    {"error": str(exc)},
                    "Fix incident log integrity before LIVE arming.",
                )
            )

        # Cost gate: warning in non-live contexts, fail-closed for live arming.
        if bool(getattr(cfg, "COST_GATE_ENABLED", False)):
            try:
                cost_status, cost_details = run_cost_gate(desk)
                mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
                if str(cost_status).upper() != "PASS":
                    issue = _issue(
                        "COST_GATE_P0" if mode == "LIVE" else "COST_GATE_P1",
                        "P0" if mode == "LIVE" else "P1",
                        "Edge-after-cost gate failed.",
                        {
                            "mode": mode,
                            "status": cost_status,
                            "breaches": list(cost_details.get("breaches") or []),
                            "totals": dict(cost_details.get("totals") or {}),
                            "report_json_path": cost_details.get("report_json_path"),
                            "report_md_path": cost_details.get("report_md_path"),
                        },
                        "Address spread/slippage/reject inefficiencies before go-live.",
                    )
                    if mode == "LIVE":
                        failures.append(issue)
                    else:
                        warnings_rows.append(issue)
            except Exception as exc:
                issue = _issue(
                    "COST_GATE_ERROR_P0",
                    "P0",
                    "Cost gate execution failed with exception.",
                    {"error": str(exc)},
                    "Fix cost KPI pipeline before live arming.",
                )
                failures.append(issue)

        # P1: deprecation warnings in critical modules.
        try:
            critical_modules = [
                "core.health_gate",
                "core.health_scenarios",
                "core.events",
                "core.reconciliation_project_from_events",
                "core.gpt_advisor",
                "core.option_token_resolver",
            ]
            repo_root = str(_project_root())
            own_warnings: list[dict[str, Any]] = []
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", DeprecationWarning)
                for module_name in critical_modules:
                    importlib.import_module(module_name)
            for item in captured:
                filename = str(getattr(item, "filename", ""))
                if repo_root not in filename:
                    continue
                own_warnings.append(
                    {
                        "module_file": filename,
                        "message": str(item.message),
                    }
                )
            if own_warnings:
                warnings_rows.append(
                    _issue(
                        "DEPRECATION_WARNINGS_P1",
                        "P1",
                        "DeprecationWarning emitted by critical modules.",
                        {"warnings": own_warnings[:20]},
                        "Remove deprecated APIs in critical runtime modules.",
                    )
                )
        except Exception as exc:
            warnings_rows.append(
                _issue(
                    "DEPRECATION_WARNINGS_P1",
                    "P1",
                    "Deprecation warning check failed with exception.",
                    {"error": str(exc)},
                    "Review warning policy check and critical module imports.",
                )
            )

        # P1: dashboard loaders parse artifacts.
        try:
            from dashboard.loaders import (
                load_depth_snapshot,
                load_execution_analytics,
                load_feed_state,
                load_health_gate_report,
                load_reconciliation,
            )

            vm_rows = [
                load_health_gate_report(desk),
                load_execution_analytics(desk),
                load_reconciliation(desk),
                load_feed_state(desk),
                load_depth_snapshot(desk),
            ]
            broken = []
            for vm in vm_rows:
                status = str(getattr(vm, "status", "") or "").lower()
                if status == "error":
                    broken.append(
                        {
                            "vm": vm.__class__.__name__,
                            "status": status,
                            "path": str(getattr(vm, "path", "") or getattr(vm, "db_path", "")),
                            "message": getattr(vm, "message", None),
                        }
                    )
            if broken:
                warnings_rows.append(
                    _issue(
                        "DASHBOARD_LOADERS_P1",
                        "P1",
                        "One or more dashboard loaders returned error state.",
                        {"loaders": broken},
                        "Fix artifact schema/path parsing used by dashboard loaders.",
                    )
                )
        except Exception as exc:
            warnings_rows.append(
                _issue(
                    "DASHBOARD_LOADERS_P1",
                    "P1",
                    "Dashboard loader validation failed with exception.",
                    {"error": str(exc)},
                    "Fix dashboard loader imports and artifact compatibility.",
                )
            )

        # P1: execution analytics artifact should exist.
        execution_analytics_path = logs_dir() / "execution_analytics.json"
        if not execution_analytics_path.exists():
            warnings_rows.append(
                _issue(
                    "EXEC_ANALYTICS_MISSING_P1",
                    "P1",
                    "Execution analytics artifact is missing.",
                    {"path": str(execution_analytics_path)},
                    "Generate execution analytics before final go-live review.",
                )
            )

        failures.sort(key=lambda row: (_SEVERITY_RANK.get(str(row.get("severity")), 99), str(row.get("code"))))
        warnings_rows.sort(key=lambda row: (_SEVERITY_RANK.get(str(row.get("severity")), 99), str(row.get("code"))))

        status = "FAIL" if failures else "PASS"
        report = {
            "desk_id": desk,
            "status": status,
            "generated_ts": utc_now().isoformat().replace("+00:00", "Z"),
            "failures": failures,
            "warnings": warnings_rows,
            "artifacts": {
                "health_gate_json": str(logs_dir() / "health_gate_report.json"),
                "health_gate_md": str(logs_dir() / "health_gate_report.md"),
                "events": str(logs_dir() / "events.jsonl"),
                "execution_analytics": str(execution_analytics_path),
                "cost_kpis_json": str(logs_dir() / "cost_kpis.json"),
                "cost_kpis_md": str(logs_dir() / "cost_kpis.md"),
            },
        }

        report_json_path = logs_dir() / "go_live_scorecard.json"
        report_md_path = logs_dir() / "go_live_scorecard.md"
        write_json_atomic(report_json_path, report)
        _write_text_atomic(report_md_path, _render_md(report))
        report["report_json_path"] = str(report_json_path)
        report["report_md_path"] = str(report_md_path)
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Go-live scorecard gate for ARM_LIVE.")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    args = parser.parse_args(argv)

    report = GoLiveScorecard().run(str(args.desk))
    print(f"GO_LIVE_SCORECARD: {report.get('status')}")
    print(f"report_json: {report.get('report_json_path')}")
    print(f"report_md: {report.get('report_md_path')}")
    if report.get("status") == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
