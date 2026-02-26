"""Migration note:
Hard gate for LIVE enablement using schema, SLO, and rolling acceptance audits.
Non-strict modes emit DEGRADED instead of failing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.acceptance_gate import evaluate_acceptance_gate
from core.market_context import derive_market_context
from core.readiness_gate import check_trade_identity_schema
from core.slo_guard import evaluate_slo_status
from core.time_utils import now_ist, now_utc_epoch


def _audit_paths(day: str) -> tuple[Path, Path]:
    root = Path(getattr(cfg, "LIVE_ENABLEMENT_AUDIT_PATH", "logs/live_enablement_audit_latest.json"))
    if root.name.endswith(".json") and "latest" in root.name:
        day_path = root.with_name(f"live_enablement_audit_{day}.json")
        return day_path, root
    latest = root if root.suffix == ".json" else (root / "live_enablement_audit_latest.json")
    day_path = latest.with_name(f"live_enablement_audit_{day}.json")
    return day_path, latest


def run_gate(*, strict: bool = False, strict_if_live: bool = True, enforce_failover: bool = False) -> dict:
    ctx = derive_market_context(
        {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        }
    )
    strict_mode = bool(
        strict
        or bool(getattr(cfg, "LIVE_ENABLEMENT_STRICT", False))
        or (strict_if_live and (ctx.mode == "LIVE"))
    )

    schema_ok, schema_reason = check_trade_identity_schema()
    slo = evaluate_slo_status(enforce_failover=bool(enforce_failover and strict_mode))
    acceptance = evaluate_acceptance_gate(strict=strict_mode)
    statistical_gate_enabled = bool(getattr(cfg, "LIVE_ENABLEMENT_REQUIRE_STATISTICAL_PASS", True))

    blockers: list[str] = []
    warnings: list[str] = []
    if not schema_ok:
        blockers.append(f"schema:{schema_reason}")

    slo_reason = ",".join(list(slo.get("reasons") or []))
    if not bool(slo.get("ok", False)):
        code = f"slo:{slo_reason or 'breach'}"
        if strict_mode:
            blockers.append(code)
        else:
            warnings.append(code)
    for warning in list(slo.get("warnings") or []):
        warnings.append(f"slo_warn:{warning}")

    acc_status = str(acceptance.get("status") or "DEGRADED").upper()
    if acc_status == "FAIL":
        blockers.extend([f"acceptance:{reason}" for reason in list(acceptance.get("blockers") or ["failed"])])
    elif acc_status == "DEGRADED":
        rows = [f"acceptance:{reason}" for reason in list(acceptance.get("blockers") or ["degraded"])]
        if strict_mode:
            blockers.extend(rows)
        else:
            warnings.extend(rows)

    statistical_gate_pass = bool(acc_status == "PASS")
    statistical_gate_blockers = [
        f"stat_gate:{reason}"
        for reason in list(acceptance.get("blockers") or ["acceptance_not_pass"])
    ]
    if statistical_gate_enabled and ctx.mode == "LIVE" and (not statistical_gate_pass):
        blockers.extend(statistical_gate_blockers)

    status = "PASS"
    if blockers:
        status = "FAIL"
    elif warnings:
        status = "DEGRADED"

    payload = {
        "status": status,
        "strict_mode": bool(strict_mode),
        "mode": ctx.mode,
        "market_open": bool(ctx.is_market_open),
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "checks": {
            "schema": {"ok": bool(schema_ok), "reason": schema_reason},
            "slo": slo,
            "acceptance": acceptance,
            "statistical_gate": {
                "enabled": bool(statistical_gate_enabled),
                "passed": bool(statistical_gate_pass),
                "mode": ctx.mode,
                "blockers": statistical_gate_blockers if (ctx.mode == "LIVE") else [],
            },
        },
    }
    day = now_ist().date().isoformat()
    day_path, latest_path = _audit_paths(day)
    body = json.dumps(payload, indent=2, default=str)
    day_path.parent.mkdir(parents=True, exist_ok=True)
    day_path.write_text(body, encoding="utf-8")
    latest_path.write_text(body, encoding="utf-8")
    payload["audit_path"] = str(latest_path)
    payload["audit_day_path"] = str(day_path)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LIVE enablement hard-gate checks.")
    parser.add_argument("--strict", action="store_true", help="Always fail non-PASS status.")
    parser.add_argument(
        "--strict-if-live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Treat DEGRADED as FAIL when EXECUTION_MODE resolves to LIVE.",
    )
    parser.add_argument("--audit-only", action="store_true", help="Always return exit code 0.")
    parser.add_argument(
        "--enforce-failover",
        action="store_true",
        help="Allow SLO guard to trigger failover action when strict is active.",
    )
    args = parser.parse_args()

    payload = run_gate(
        strict=bool(args.strict),
        strict_if_live=bool(args.strict_if_live),
        enforce_failover=bool(args.enforce_failover),
    )
    print(json.dumps(payload, indent=2, default=str))
    if args.audit_only:
        return 0
    return 1 if str(payload.get("status")) == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
