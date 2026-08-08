#!/usr/bin/env python3
"""Shared helpers for the Strategy Certification Kernel.

This module is intentionally research-only. It helps downstream scripts create
auditable reports and passports without granting runtime authority or broker
permissions.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

SAFE_RUNTIME_AUTHORITY = "NONE"
SAFE_BROKER_ACTIONS_ALLOWED = False
SAFE_CERTIFICATION = "NOT_CERTIFIED"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    keys = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str) and value.upper() == "INF":
            return float("inf")
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def canonical_filters(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        if not text:
            items = []
        else:
            try:
                parsed = ast.literal_eval(text)
                items = parsed if isinstance(parsed, list) else [text]
            except (SyntaxError, ValueError):
                items = [part.strip() for part in text.replace("[", "").replace("]", "").replace("'", "").split(",")]
    return sorted(str(item).strip() for item in items if str(item).strip())


def shape_key(row: dict[str, Any]) -> str:
    filters = ",".join(canonical_filters(row.get("filters")))
    fields = [
        str(row.get("instrument", "")).upper(),
        str(row.get("family", "")).lower(),
        str(row.get("direction", "")).upper(),
        str(row.get("window_minutes", "")),
        filters,
        str(row.get("exit_profile", row.get("exit", ""))).lower(),
    ]
    return "|".join(fields)


def candidate_rejection_reasons(
    row: dict[str, Any],
    *,
    min_trades: int,
    min_net_expectancy_bps: float,
    min_profit_factor: float,
    max_drawdown_bps_abs: float,
    duplicate_shape: bool,
) -> list[str]:
    reasons: list[str] = []
    trades = to_int(row.get("trades"))
    net = to_float(row.get("net_expectancy_bps"))
    pf = to_float(row.get("profit_factor"))
    drawdown = abs(to_float(row.get("max_drawdown_bps")))
    fallback_used = to_bool(row.get("fallback_execution_data_used"))
    broker_allowed = to_bool(row.get("broker_actions_allowed"))
    runtime = str(row.get("runtime_authority", "")).upper()

    if duplicate_shape:
        reasons.append("duplicate_shape")
    if trades < min_trades:
        reasons.append("trades_below_threshold")
    if net < min_net_expectancy_bps:
        reasons.append("net_expectancy_below_threshold")
    if pf < min_profit_factor:
        reasons.append("profit_factor_below_threshold")
    if drawdown > max_drawdown_bps_abs:
        reasons.append("drawdown_too_high")
    if fallback_used:
        reasons.append("fallback_data_used")
    if broker_allowed:
        reasons.append("broker_actions_allowed_not_false")
    if runtime != SAFE_RUNTIME_AUTHORITY:
        reasons.append("runtime_authority_not_none")

    return reasons


def annotate_candidates(
    rows: Iterable[dict[str, Any]],
    *,
    min_trades: int,
    min_net_expectancy_bps: float,
    min_profit_factor: float,
    max_drawdown_bps_abs: float,
) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    best_by_shape: dict[str, tuple[int, float]] = {}
    for index, row in enumerate(rows):
        item = dict(row)
        key = shape_key(item)
        item["candidate_shape_key"] = key
        score = to_float(item.get("score"), default=-1.0)
        indexed.append(item)
        current = best_by_shape.get(key)
        if current is None or score > current[1]:
            best_by_shape[key] = (index, score)

    annotated: list[dict[str, Any]] = []
    for index, row in enumerate(indexed):
        key = row["candidate_shape_key"]
        duplicate = best_by_shape[key][0] != index
        reasons = candidate_rejection_reasons(
            row,
            min_trades=min_trades,
            min_net_expectancy_bps=min_net_expectancy_bps,
            min_profit_factor=min_profit_factor,
            max_drawdown_bps_abs=max_drawdown_bps_abs,
            duplicate_shape=duplicate,
        )
        out = dict(row)
        out["duplicate_shape"] = duplicate
        out["rejection_reasons"] = reasons
        out["eligible_for_robustness"] = not reasons
        if out["eligible_for_robustness"]:
            out["certification_path_state"] = "ROBUSTNESS_REQUIRED"
        elif "duplicate_shape" in reasons:
            out["certification_path_state"] = "DUPLICATE_SHAPE"
        else:
            out["certification_path_state"] = "REJECTED"
        out["runtime_authority"] = SAFE_RUNTIME_AUTHORITY
        out["broker_actions_allowed"] = SAFE_BROKER_ACTIONS_ALLOWED
        out["certification"] = SAFE_CERTIFICATION
        annotated.append(out)
    return annotated


def summarize_annotations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for row in rows:
        for reason in row.get("rejection_reasons", []):
            reasons[reason] = reasons.get(reason, 0) + 1
    unique_shapes = len({row.get("candidate_shape_key") for row in rows})
    return {
        "candidates": len(rows),
        "unique_shapes": unique_shapes,
        "duplicates": sum(1 for row in rows if row.get("duplicate_shape")),
        "eligible_for_robustness": sum(1 for row in rows if row.get("eligible_for_robustness")),
        "rejection_reason_counts": dict(sorted(reasons.items())),
        "runtime_authority": SAFE_RUNTIME_AUTHORITY,
        "broker_actions_allowed": SAFE_BROKER_ACTIONS_ALLOWED,
    }


def write_markdown_report(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [f"# {title}", ""]
    payload.extend(lines)
    path.write_text("\n".join(payload) + "\n", encoding="utf-8")


def evidence_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): sha256_file(path) for path in paths if path.exists() and path.is_file()}
