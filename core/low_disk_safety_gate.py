"""Fail-closed, additive low-disk admission gate for read-only observation.

The gate does not delete data or alter feed/risk policy.  Its budget is supplied
by a reviewed, measured contract and is therefore auditable and reproducible.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True)
class DiskBudget:
    baseline_bytes: int
    remaining_session_growth_bytes: int
    peak_transient_bytes: int
    shutdown_reserve_bytes: int
    required_free_bytes: int


@dataclass(frozen=True)
class DiskDecision:
    verdict: str
    path: str
    free_bytes: int | None
    required_free_bytes: int | None
    reason: str
    budget: dict

    def as_dict(self) -> dict:
        return asdict(self)


def derive_budget(*, baseline_bytes: int, observed_bytes_per_second: float,
                  remaining_session_seconds: int, peak_transient_bytes: int,
                  shutdown_reserve_bytes: int) -> DiskBudget:
    values = (baseline_bytes, observed_bytes_per_second, remaining_session_seconds,
              peak_transient_bytes, shutdown_reserve_bytes)
    if any(float(value) < 0 for value in values):
        raise ValueError("DISK_BUDGET_INPUT_NEGATIVE")
    growth = int(observed_bytes_per_second * remaining_session_seconds)
    required = int(baseline_bytes) + growth + int(peak_transient_bytes) + int(shutdown_reserve_bytes)
    return DiskBudget(int(baseline_bytes), growth, int(peak_transient_bytes),
                      int(shutdown_reserve_bytes), required)


def evaluate(path: Path, budget: DiskBudget) -> DiskDecision:
    path = Path(path)
    try:
        free = int(shutil.disk_usage(path).free)
    except (OSError, ValueError) as exc:
        return DiskDecision("UNKNOWN", str(path), None, budget.required_free_bytes,
                            f"DISK_USAGE_UNAVAILABLE:{type(exc).__name__}", asdict(budget))
    verdict = "PASS" if free >= budget.required_free_bytes else "BLOCKED"
    return DiskDecision(verdict, str(path), free, budget.required_free_bytes,
                        "SUFFICIENT_FREE_SPACE" if verdict == "PASS" else "INSUFFICIENT_FREE_SPACE",
                        asdict(budget))


def write_decision(path: Path, decision: DiskDecision) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(decision.as_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_contract(contract: dict) -> tuple[bool, tuple[str, ...]]:
    """Independently validate contract shape and fail-closed invariants."""
    errors: list[str] = []
    required = {"schema_version", "formula", "observed_bytes", "observed_bytes_per_second",
                "remaining_session_seconds", "peak_transient_bytes", "shutdown_reserve_bytes",
                "measurement_status", "fail_closed", "deletion_allowed", "order_authority",
                "broker_write_authority"}
    errors.extend(sorted(f"MISSING:{key}" for key in required if key not in contract))
    if errors:
        return False, tuple(errors)
    for key in ("observed_bytes", "observed_bytes_per_second", "remaining_session_seconds",
                "peak_transient_bytes", "shutdown_reserve_bytes"):
        if not isinstance(contract[key], (int, float)) or contract[key] < 0:
            errors.append(f"INVALID_NONNEGATIVE:{key}")
    if contract.get("fail_closed") is not True:
        errors.append("FAIL_CLOSED_REQUIRED")
    for key in ("deletion_allowed", "order_authority", "broker_write_authority"):
        if contract.get(key) is not False:
            errors.append(f"UNSAFE_FLAG:{key}")
    return not errors, tuple(errors)
