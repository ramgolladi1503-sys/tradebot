#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.learning_paths import canonical_suggestions_log_path
from core.paths import logs_dir, repo_root


_STATUS_OK = {"OK", "REST_FALLBACK"}


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _read_last_jsonl_rows(path: Path, limit: int) -> list[dict]:
    if limit <= 0 or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict] = []
    for raw in lines[-int(limit) :]:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _as_float(value) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _price_match(left, right, *, tol: float = 0.01) -> bool | None:
    left_val = _as_float(left)
    right_val = _as_float(right)
    if left_val is None or right_val is None:
        return None
    return abs(left_val - right_val) <= float(tol)


def _row_checks(row: dict) -> dict:
    entry_price = _as_float(row.get("entry_price"))
    expected_entry = _as_float(row.get("expected_entry"))
    current_ltp = _as_float(row.get("current_ltp"))
    entry_status = str(row.get("entry_status") or "").strip().upper()
    entry_matches_expected = _price_match(entry_price, expected_entry)
    entry_matches_current_ltp = _price_match(entry_price, current_ltp)
    status_ok = entry_status in _STATUS_OK
    problems: list[str] = []
    if entry_matches_expected is False:
        problems.append("ENTRY_NE_EXPECTED")
    if entry_matches_current_ltp is False:
        problems.append("ENTRY_NE_LTP")
    if not status_ok:
        problems.append(f"STATUS_{entry_status or 'MISSING'}")
    return {
        "entry_matches_expected": entry_matches_expected,
        "entry_matches_current_ltp": entry_matches_current_ltp,
        "status_ok": status_ok,
        "problems": problems,
    }


def build_live_entry_report(
    *,
    root: Path | None = None,
    runtime_logs: Path | None = None,
    suggestions_path: Path | None = None,
    limit: int = 10,
) -> dict:
    repo = Path(root or repo_root())
    runtime_dir = Path(runtime_logs or logs_dir())
    suggestions_status = _read_json(runtime_dir / "suggestions_status.json")
    engine_status = _read_json(runtime_dir / "engine_cycle_status.json")
    suggestions_log = Path(suggestions_path or canonical_suggestions_log_path())
    rows = _read_last_jsonl_rows(suggestions_log, max(1, int(limit)))
    analyzed_rows: list[dict] = []
    for row in rows:
        checks = _row_checks(row)
        analyzed_rows.append(
            {
                "trade_id": row.get("trade_id"),
                "entry_price": _as_float(row.get("entry_price")),
                "expected_entry": _as_float(row.get("expected_entry")),
                "current_ltp": _as_float(row.get("current_ltp")),
                "entry_status": row.get("entry_status"),
                "permission": row.get("permission"),
                "permission_reason": row.get("permission_reason"),
                "volume": _as_float(row.get("volume")),
                "oi": _as_float(row.get("oi")),
                **checks,
            }
        )
    market_mode = str(
        suggestions_status.get("market_mode")
        or engine_status.get("market_mode")
        or ""
    ).strip().upper()
    market_open = bool(
        suggestions_status.get("market_open")
        if "market_open" in suggestions_status
        else engine_status.get("market_open")
    )
    return {
        "repo_root": str(repo),
        "runtime_logs": str(runtime_dir),
        "suggestions_log": str(suggestions_log),
        "market_mode": market_mode,
        "market_open": market_open,
        "row_count": len(analyzed_rows),
        "rows": analyzed_rows,
    }


def render_live_entry_report(report: dict) -> str:
    lines = [
        f"Runtime logs: {report.get('runtime_logs')}",
        f"Suggestions log: {report.get('suggestions_log')}",
        f"Market: mode={report.get('market_mode')} open={report.get('market_open')}",
        f"Latest rows: {report.get('row_count')}",
    ]
    rows = list(report.get("rows") or [])
    if not rows:
        lines.append("No suggestion rows found.")
        return "\n".join(lines)
    for row in rows:
        problems = list(row.get("problems") or [])
        prefix = "BAD" if problems else "OK "
        problem_text = ",".join(problems) if problems else "-"
        lines.append(
            (
                f"{prefix} trade_id={row.get('trade_id')} "
                f"entry_price={row.get('entry_price')} expected_entry={row.get('expected_entry')} "
                f"current_ltp={row.get('current_ltp')} entry_status={row.get('entry_status')} "
                f"permission={row.get('permission')} permission_reason={row.get('permission_reason')} "
                f"volume={row.get('volume')} oi={row.get('oi')} "
                f"entry_matches_expected={row.get('entry_matches_expected')} "
                f"entry_matches_current_ltp={row.get('entry_matches_current_ltp')} "
                f"status_ok={row.get('status_ok')} problems={problem_text}"
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check recent live suggestion entry correctness.")
    parser.add_argument("--limit", type=int, default=10, help="Number of latest suggestion rows to inspect.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    parser.add_argument(
        "--fail-on-bad-live",
        action="store_true",
        help="Exit nonzero if any inspected row is bad while market mode is LIVE.",
    )
    args = parser.parse_args()

    report = build_live_entry_report(limit=max(1, int(args.limit)))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_live_entry_report(report))

    if bool(args.fail_on_bad_live) and str(report.get("market_mode") or "").upper() == "LIVE":
        for row in list(report.get("rows") or []):
            if list(row.get("problems") or []):
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
