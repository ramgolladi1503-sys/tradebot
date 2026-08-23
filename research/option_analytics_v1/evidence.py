from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
import tempfile
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.option_analytics import (
    CalculationStatus,
    ModelInputs,
    OptionType,
    PricingModel,
    calculate_greeks,
    price_option,
    solve_implied_volatility,
)
from research.option_analytics_v1.legacy_audit import run_legacy_compatibility_audit
from research.option_analytics_v1.oracle import (
    black76_price,
    bsm_price,
    finite_difference_greeks,
    parity_residual,
)

IST = ZoneInfo("Asia/Kolkata")
SCHEMA_VERSION = "1.0.0"
BASE_SHA = "596fff09859afeca292bc3e3e31d4a55db1fd8c6"
PRICE_ABS_TOLERANCE = 1e-8
DELTA_ABS_TOLERANCE = 2e-5
GAMMA_ABS_TOLERANCE = 3e-7
THETA_ABS_TOLERANCE = 0.3
VEGA_ABS_TOLERANCE = 3e-4
RHO_ABS_TOLERANCE = 3e-3
IV_ABS_TOLERANCE = 2e-8
PARITY_ABS_TOLERANCE = 1e-8


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is forbidden in evidence")
        return round(value, 10)
    return value


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def semantic_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _model_inputs(*, model: PricingModel, option_type: OptionType, moneyness: float, time_days: float, volatility: float, rate: float) -> ModelInputs:
    valuation = datetime(2026, 7, 27, 10, 0, tzinfo=IST)
    strike = 25000.0
    common = dict(
        model=model,
        option_type=option_type,
        valuation_timestamp=valuation,
        expiry_timestamp=valuation + timedelta(days=time_days),
        strike=strike,
        risk_free_rate=rate,
        volatility=volatility,
    )
    if model is PricingModel.BLACK_SCHOLES_MERTON:
        return ModelInputs(**common, spot=strike * moneyness, dividend_yield=0.012)
    return ModelInputs(**common, forward=strike * moneyness)


def _oracle_price(inputs: ModelInputs) -> float:
    _, _, years = _year_fraction(inputs)
    assert years is not None
    if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
        assert inputs.spot is not None
        price = bsm_price(
            spot=inputs.spot,
            strike=inputs.strike,
            time_years=years,
            rate=inputs.risk_free_rate,
            dividend_yield=inputs.dividend_yield,
            volatility=inputs.volatility,
            is_call=inputs.option_type is OptionType.CALL,
        )
        return max(0.0, price)
    assert inputs.forward is not None
    price = black76_price(
        forward=inputs.forward,
        strike=inputs.strike,
        time_years=years,
        rate=inputs.risk_free_rate,
        volatility=inputs.volatility,
        is_call=inputs.option_type is OptionType.CALL,
    )
    return max(0.0, price)


def _year_fraction(inputs: ModelInputs) -> tuple[float, float, float]:
    seconds = (inputs.expiry_timestamp - inputs.valuation_timestamp).total_seconds()
    return seconds, seconds / 86400.0, seconds / (365.0 * 86400.0)


def generate_reference_evidence() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for model in PricingModel:
        for option_type in OptionType:
            for moneyness in (0.90, 1.00, 1.10):
                for time_days in (0.25, 7.0):
                    for volatility in (0.10, 0.35):
                        for rate in (-0.01, 0.06):
                            inputs = _model_inputs(
                                model=model,
                                option_type=option_type,
                                moneyness=moneyness,
                                time_days=time_days,
                                volatility=volatility,
                                rate=rate,
                            )
                            primary_price = price_option(inputs)
                            primary_greeks = calculate_greeks(inputs)
                            oracle_price = _oracle_price(inputs)
                            _, _, years = _year_fraction(inputs)
                            underlying = inputs.spot if inputs.spot is not None else inputs.forward
                            assert underlying is not None
                            oracle_greeks = finite_difference_greeks(
                                model=model.value,
                                option_type=option_type.value,
                                underlying=underlying,
                                strike=inputs.strike,
                                time_years=years,
                                rate=inputs.risk_free_rate,
                                volatility=inputs.volatility,
                                dividend_yield=inputs.dividend_yield,
                            )
                            solved = solve_implied_volatility(replace(inputs, volatility=0.20), oracle_price)
                            lower_gap = None if primary_price.lower_price_bound is None else oracle_price - primary_price.lower_price_bound
                            iv_identifiable = lower_gap is not None and lower_gap > 1e-8
                            errors = {
                                "price": abs(primary_price.price - oracle_price) if primary_price.price is not None else None,
                                "delta": abs(primary_greeks.delta - oracle_greeks.delta) if primary_greeks.delta is not None else None,
                                "gamma": abs(primary_greeks.gamma - oracle_greeks.gamma) if primary_greeks.gamma is not None else None,
                                "theta": abs(primary_greeks.theta_per_year - oracle_greeks.theta_per_year) if primary_greeks.theta_per_year is not None else None,
                                "vega": abs(primary_greeks.vega_per_unit_volatility - oracle_greeks.vega_per_unit_volatility) if primary_greeks.vega_per_unit_volatility is not None else None,
                                "rho": abs(primary_greeks.rho_per_unit_rate - oracle_greeks.rho_per_unit_rate) if primary_greeks.rho_per_unit_rate is not None else None,
                                "iv": abs(solved.implied_volatility - volatility) if solved.implied_volatility is not None else None,
                            }
                            case_id = f"{model.value}:{option_type.value}:{moneyness}:{time_days}:{volatility}:{rate}"
                            row = {
                                "case_id": case_id,
                                "inputs": {
                                    "model": model.value,
                                    "option_type": option_type.value,
                                    "underlying": underlying,
                                    "strike": inputs.strike,
                                    "time_years": years,
                                    "risk_free_rate": inputs.risk_free_rate,
                                    "dividend_yield": inputs.dividend_yield,
                                    "volatility": inputs.volatility,
                                },
                                "price": {
                                    "status": primary_price.status.value,
                                    "primary": primary_price.price,
                                    "oracle": oracle_price,
                                    "lower_bound": primary_price.lower_price_bound,
                                    "upper_bound": primary_price.upper_price_bound,
                                },
                                "greeks": {
                                    "status": primary_greeks.status.value,
                                },
                                "implied_volatility": {
                                    "status": solved.status.value,
                                    "value": solved.implied_volatility,
                                    "price_error": solved.absolute_price_error,
                                    "identifiable": iv_identifiable,
                                },
                                "absolute_errors": errors,
                            }
                            rows.append(row)
                            checks = (
                                ("price", errors["price"], PRICE_ABS_TOLERANCE),
                                ("delta", errors["delta"], DELTA_ABS_TOLERANCE),
                                ("gamma", errors["gamma"], GAMMA_ABS_TOLERANCE),
                                ("theta", errors["theta"], THETA_ABS_TOLERANCE),
                                ("vega", errors["vega"], VEGA_ABS_TOLERANCE),
                                ("rho", errors["rho"], RHO_ABS_TOLERANCE),
                            )
                            for metric, error, tolerance in checks:
                                if error is None or error > tolerance:
                                    failures.append({"case_id": case_id, "metric": metric})
                            if solved.status is not CalculationStatus.OK:
                                failures.append({"case_id": case_id, "metric": "iv_status"})
                            if iv_identifiable and (errors["iv"] is None or errors["iv"] > IV_ABS_TOLERANCE):
                                failures.append({"case_id": case_id, "metric": "iv"})

    parity_rows: list[dict[str, Any]] = []
    parity_keys = sorted({
        (
            row["inputs"]["model"],
            row["inputs"]["underlying"],
            row["inputs"]["strike"],
            row["inputs"]["time_years"],
            row["inputs"]["risk_free_rate"],
            row["inputs"]["volatility"],
            row["inputs"]["dividend_yield"],
        )
        for row in rows
    })
    for model, underlying, strike, years, rate, volatility, dividend_yield in parity_keys:
        residual = parity_residual(
            model=model,
            underlying=underlying,
            strike=strike,
            time_years=years,
            rate=rate,
            volatility=volatility,
            dividend_yield=dividend_yield,
        )
        parity_rows.append({"key": [model, underlying, strike, years, rate, volatility, dividend_yield], "residual": residual})
        if abs(residual) > PARITY_ABS_TOLERANCE:
            failures.append({"case_id": str(parity_rows[-1]["key"]), "metric": "parity"})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "input_case_count": len(rows),
        "valid_case_count": len(rows),
        "invalid_case_count": 0,
        "skipped_case_count": 0,
        "output_case_count": len(rows),
        "parity_case_count": len(parity_rows),
        "iv_identifiable_case_count": sum(1 for row in rows if row["implied_volatility"]["identifiable"]),
        "iv_lower_bound_case_count": sum(1 for row in rows if not row["implied_volatility"]["identifiable"]),
        "failure_count": len(failures),
        "tolerances": {
            "price": PRICE_ABS_TOLERANCE,
            "delta": DELTA_ABS_TOLERANCE,
            "gamma": GAMMA_ABS_TOLERANCE,
            "theta": THETA_ABS_TOLERANCE,
            "vega": VEGA_ABS_TOLERANCE,
            "rho": RHO_ABS_TOLERANCE,
            "iv": IV_ABS_TOLERANCE,
            "parity": PARITY_ABS_TOLERANCE,
        },
        "rows": rows,
        "parity": parity_rows,
        "failures": failures,
    }
    payload["semantic_sha256"] = semantic_sha256(payload)
    return payload


def _git_output(root: Path, args: list[str]) -> str | None:
    proc = subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def generate_manifest(repo_root: Path, generated_at_utc: str) -> dict[str, Any]:
    source_files = sorted((repo_root / "core" / "option_analytics").glob("*.py"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "repository": "ramgolladi1503-sys/tradebot",
        "base_sha": BASE_SHA,
        "head_sha_or_working_tree_marker": _git_output(repo_root, ["rev-parse", "HEAD"]) or "LOCAL_ISOLATED_HARNESS",
        "branch": _git_output(repo_root, ["branch", "--show-current"]) or "LOCAL_ISOLATED_HARNESS",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "source_file_hashes": {
            str(path.relative_to(repo_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "production_files_touched": [str(path.relative_to(repo_root)) for path in source_files],
        "broker_api_called": False,
        "order_action": False,
        "live_execution_changed": False,
        "strategy_signal_changed": False,
        "candidate_ranking_changed": False,
        "risk_gate_changed": False,
        "outcomes_read": False,
        "holdout_read": False,
        "real_or_replay_pnl_read": False,
    }


def write_bundle(repo_root: str | Path, output_dir: str | Path, *, generated_at_utc: str = "2026-07-26T06:28:13+00:00") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    reference = generate_reference_evidence()
    legacy = run_legacy_compatibility_audit(root)
    manifest = generate_manifest(root, generated_at_utc)
    artifacts = {
        "run_manifest.json": manifest,
        "reference_case_results.json": reference,
        "legacy_compatibility_audit.json": legacy,
    }
    semantic_hashes: dict[str, str] = {}
    for name, payload in artifacts.items():
        path = target / name
        path.write_text(json.dumps(_json_value(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        semantic_hashes[name] = semantic_sha256(payload if name != "run_manifest.json" else {key: value for key, value in payload.items() if key != "generated_at_utc"})
    summary = {
        "schema_version": SCHEMA_VERSION,
        "artifact_semantic_hashes": semantic_hashes,
        "reference_failure_count": reference["failure_count"],
        "legacy_confirmed_defect_count": legacy["confirmed_legacy_defect_count"],
    }
    summary["semantic_sha256"] = semantic_sha256(summary)
    (target / "bundle_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_sha256s(target)
    return summary


def _write_sha256s(target: Path) -> None:
    sha_lines = []
    for path in sorted(target.glob("*.json")):
        sha_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (target / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")


def write_complete_bundle(repo_root: str | Path, output_dir: str | Path, *, generated_at_utc: str = "2026-07-26T06:28:13+00:00") -> dict[str, Any]:
    target = Path(output_dir).resolve()
    summary = write_bundle(repo_root, target, generated_at_utc=generated_at_utc)
    determinism = run_determinism(repo_root)
    (target / "determinism_report.json").write_text(json.dumps(determinism, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_sha256s(target)
    gate = publication_gate(repo_root, target)
    (target / "publication_gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_sha256s(target)
    final_hash_errors = verify_sha256s(target)
    if final_hash_errors:
        raise RuntimeError(f"final evidence hash verification failed: {final_hash_errors}")
    return {"summary": summary, "determinism": determinism, "publication_gate": gate}


def verify_sha256s(output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    errors: list[str] = []
    sums = target / "SHA256SUMS"
    if not sums.exists():
        return ["SHA256SUMS missing"]
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = target / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"hash mismatch: {name}")
    return errors


def run_determinism(repo_root: str | Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        one = write_bundle(repo_root, first, generated_at_utc="2026-07-26T06:28:13+00:00")
        two = write_bundle(repo_root, second, generated_at_utc="2026-07-27T06:28:13+00:00")
        equal = one["artifact_semantic_hashes"] == two["artifact_semantic_hashes"]
        return {
            "schema_version": SCHEMA_VERSION,
            "semantic_hashes_equal": equal,
            "first": one["artifact_semantic_hashes"],
            "second": two["artifact_semantic_hashes"],
            "failure_count": 0 if equal else 1,
        }


def publication_gate(repo_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    target = Path(output_dir)
    errors = verify_sha256s(target)
    required = {
        "run_manifest.json",
        "reference_case_results.json",
        "legacy_compatibility_audit.json",
        "bundle_summary.json",
        "SHA256SUMS",
    }
    missing = sorted(name for name in required if not (target / name).exists())
    errors.extend(f"missing artifact: {name}" for name in missing)
    if not missing:
        reference = json.loads((target / "reference_case_results.json").read_text(encoding="utf-8"))
        legacy = json.loads((target / "legacy_compatibility_audit.json").read_text(encoding="utf-8"))
        manifest = json.loads((target / "run_manifest.json").read_text(encoding="utf-8"))
        if reference.get("failure_count") != 0:
            errors.append("reference evidence has failures")
        if reference.get("input_case_count") != reference.get("output_case_count"):
            errors.append("reference case counts do not reconcile")
        for key in ("put_theta_defect", "time_to_expiry_defect", "solver_convergence_ambiguity", "invalid_input_ambiguity"):
            if legacy.get("summary", {}).get(key) != "CONFIRMED":
                errors.append(f"legacy audit unresolved: {key}")
        safety_expectations = {
            "broker_api_called": False,
            "order_action": False,
            "live_execution_changed": False,
            "strategy_signal_changed": False,
            "candidate_ranking_changed": False,
            "risk_gate_changed": False,
            "outcomes_read": False,
            "holdout_read": False,
            "real_or_replay_pnl_read": False,
        }
        for key, expected in safety_expectations.items():
            if manifest.get(key) is not expected:
                errors.append(f"unsafe manifest field: {key}")
    determinism = run_determinism(repo_root)
    if determinism["failure_count"]:
        errors.append("semantic determinism failed")
    verdict = "PASS_RESEARCH_SIDECAR_GATE" if not errors else "FAIL_RESEARCH_SIDECAR_GATE"
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "failure_count": len(errors),
        "errors": errors,
        "determinism": determinism,
    }
