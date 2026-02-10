from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import config as cfg


def load_latest_ablation_metrics(
    path: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    report_path = Path(path or getattr(cfg, "ABLATION_LATEST_PATH", "reports/ablation/ablation_latest.json"))
    if not report_path.exists():
        return None, "ablation_report_missing"
    try:
        payload = json.loads(report_path.read_text())
    except Exception as exc:
        return None, f"ablation_report_invalid:{type(exc).__name__}"
    return payload, None


def evaluate_ablation_sanity(report: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if not report:
        return False, ["ablation_report_missing"]
    baseline = report.get("baseline") or {}
    ablations = report.get("ablations") or report.get("rows") or []
    if not isinstance(ablations, list) or not ablations:
        return False, ["ablation_rows_missing"]

    base_ret = float(baseline.get("return") or 0.0)
    base_dd = float(baseline.get("max_drawdown") or 0.0)
    suspicious_ret = float(getattr(cfg, "ML_ABLATION_CHEAT_RETURN_DELTA", 0.05))
    suspicious_dd = float(getattr(cfg, "ML_ABLATION_CHEAT_DRAWDOWN_IMPROVE", 0.03))
    reasons: list[str] = []

    for row in ablations:
        try:
            name = str(row.get("name") or row.get("toggle") or "unknown")
            ret = float(row.get("return") or 0.0)
            dd = float(row.get("max_drawdown") or 0.0)
        except Exception:
            reasons.append("ablation_row_invalid")
            continue
        # If disabling a component improves both return and drawdown materially, treat as suspicious.
        if (ret - base_ret) > suspicious_ret and (dd - base_dd) > suspicious_dd:
            reasons.append(f"ablation_suspicious_gain:{name}")

    if reasons:
        return False, reasons
    return True, []

