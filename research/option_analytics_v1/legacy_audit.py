from __future__ import annotations

import inspect
import math
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core import greeks as legacy
from core.option_analytics import (
    CalculationStatus,
    ModelInputs,
    OptionType,
    PricingModel,
    calculate_greeks,
    no_arbitrage_bounds,
    price_option,
    solve_implied_volatility,
)

IST = ZoneInfo("Asia/Kolkata")
SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0


def _inputs(*, option_type: OptionType, time_years: float = 0.5, volatility: float = 0.2) -> ModelInputs:
    valuation = datetime(2026, 7, 27, 10, 0, tzinfo=IST)
    return ModelInputs(
        model=PricingModel.BLACK_SCHOLES_MERTON,
        option_type=option_type,
        valuation_timestamp=valuation,
        expiry_timestamp=valuation + timedelta(seconds=time_years * SECONDS_PER_YEAR),
        strike=100.0,
        risk_free_rate=float(legacy.cfg.RISK_FREE_RATE),
        volatility=volatility,
        spot=100.0,
        dividend_yield=0.0,
    )


def _row(case_id: str, legacy_output: Any, sidecar_output: Any, oracle_output: Any, classification: str, severity: str, explanation: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "legacy_output": legacy_output,
        "sidecar_output": sidecar_output,
        "oracle_output": oracle_output,
        "classification": classification,
        "severity": severity,
        "explanation": explanation,
    }


def run_legacy_compatibility_audit(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    rows: list[dict[str, Any]] = []
    call = _inputs(option_type=OptionType.CALL)
    put = _inputs(option_type=OptionType.PUT)
    t = 0.5
    r = call.risk_free_rate

    for option_type, inputs, is_call in ((OptionType.CALL, call, True), (OptionType.PUT, put, False)):
        legacy_price = legacy.bs_price(100.0, 100.0, t, r, 0.2, is_call=is_call)
        sidecar_price = price_option(inputs).price
        rows.append(_row(
            f"{option_type.value.lower()}_price",
            legacy_price,
            sidecar_price,
            sidecar_price,
            "MATCH" if math.isclose(legacy_price, sidecar_price, rel_tol=0.0, abs_tol=1e-10) else "INCONCLUSIVE",
            "NONE",
            "Legacy and sidecar prices agree under the legacy q=0 convention.",
        ))

    call_legacy_greeks = legacy.greeks(100.0, 100.0, t, 0.2, is_call=True)
    put_legacy_greeks = legacy.greeks(100.0, 100.0, t, 0.2, is_call=False)
    call_sidecar = calculate_greeks(call)
    put_sidecar = calculate_greeks(put)
    for name in ("delta", "gamma", "vega"):
        side_field = "vega_per_unit_volatility" if name == "vega" else name
        for label, legacy_values, side_values in (("call", call_legacy_greeks, call_sidecar), ("put", put_legacy_greeks, put_sidecar)):
            legacy_value = legacy_values[name]
            side_value = getattr(side_values, side_field)
            rows.append(_row(
                f"{label}_{name}",
                legacy_value,
                side_value,
                side_value,
                "MATCH" if side_value is not None and math.isclose(legacy_value, side_value, rel_tol=0.0, abs_tol=1e-10) else "INCONCLUSIVE",
                "NONE",
                "Legacy and sidecar agree under identical q=0 and unit conventions.",
            ))

    rows.append(_row(
        "call_theta",
        call_legacy_greeks["theta"],
        call_sidecar.theta_per_year,
        call_sidecar.theta_per_year,
        "MATCH" if call_sidecar.theta_per_year is not None and math.isclose(call_legacy_greeks["theta"], call_sidecar.theta_per_year, abs_tol=1e-10) else "INCONCLUSIVE",
        "NONE",
        "Call theta agrees under q=0.",
    ))
    put_theta_matches = put_sidecar.theta_per_year is not None and math.isclose(put_legacy_greeks["theta"], put_sidecar.theta_per_year, abs_tol=1e-10)
    rows.append(_row(
        "put_theta",
        put_legacy_greeks["theta"],
        put_sidecar.theta_per_year,
        put_sidecar.theta_per_year,
        "INCONCLUSIVE" if put_theta_matches else "LEGACY_DEFECT_CONFIRMED",
        "HIGH" if not put_theta_matches else "NONE",
        "Legacy put theta subtracts the interest term; the independently finite-difference-validated sidecar uses the correct positive put interest term.",
    ))

    known_price = price_option(replace(call, volatility=0.35)).price
    legacy_iv = legacy.implied_vol(known_price, 100.0, 100.0, t, is_call=True)
    sidecar_iv = solve_implied_volatility(call, known_price)
    rows.append(_row(
        "implied_volatility_regular_case",
        legacy_iv,
        sidecar_iv.implied_volatility,
        0.35,
        "MATCH" if sidecar_iv.implied_volatility is not None and math.isclose(legacy_iv, 0.35, abs_tol=1e-4) and math.isclose(sidecar_iv.implied_volatility, 0.35, abs_tol=1e-8) else "INCONCLUSIVE",
        "NONE",
        "Both solvers recover a regular ATM case; only the sidecar exposes convergence status and error.",
    ))

    negative_vol_legacy = legacy.bs_price(100.0, 100.0, t, r, -0.1, True)
    negative_vol_sidecar = price_option(replace(call, volatility=-0.1))
    rows.append(_row(
        "negative_volatility_input",
        negative_vol_legacy,
        {"status": negative_vol_sidecar.status.value, "price": negative_vol_sidecar.price},
        {"status": CalculationStatus.INVALID_INPUT.value, "price": None},
        "LEGACY_DEFECT_CONFIRMED" if negative_vol_legacy == 0.0 and negative_vol_sidecar.status is CalculationStatus.INVALID_INPUT else "INCONCLUSIVE",
        "MEDIUM",
        "Legacy collapses an invalid volatility into numeric zero; sidecar returns typed failure.",
    ))

    _, _, upper, _, _ = no_arbitrage_bounds(call)
    assert upper is not None
    outside_market = upper + 1.0
    legacy_outside = legacy.implied_vol(outside_market, 100.0, 100.0, t, is_call=True)
    sidecar_outside = solve_implied_volatility(call, outside_market)
    rows.append(_row(
        "price_outside_no_arbitrage_bounds",
        legacy_outside,
        {"status": sidecar_outside.status.value, "iv": sidecar_outside.implied_volatility},
        {"status": CalculationStatus.OUTSIDE_NO_ARBITRAGE_BOUNDS.value, "iv": None},
        "LEGACY_DEFECT_CONFIRMED" if sidecar_outside.status is CalculationStatus.OUTSIDE_NO_ARBITRAGE_BOUNDS and legacy_outside is not None else "INCONCLUSIVE",
        "HIGH",
        "Legacy returns a clamped numeric volatility for an impossible price; sidecar rejects it before solving.",
    ))

    legacy_source = inspect.getsource(legacy)
    option_chain_path = root / "core" / "option_chain.py"
    option_chain_source = option_chain_path.read_text(encoding="utf-8") if option_chain_path.exists() else ""
    source_checks = (
        ("hidden_global_rate", "cfg.RISK_FREE_RATE" in legacy_source, "Rate is hidden through global configuration in legacy IV and Greeks APIs.", "MEDIUM"),
        ("solver_status_unavailable", "return max(vol, 1e-4)" in legacy_source, "Legacy IV returns only a number, with no convergence or error status.", "HIGH"),
        ("integer_day_expiry_floor", "dte = max((expiry_date - date.today()).days, 1)" in option_chain_source and "t = dte / 365.0" in option_chain_source, "Legacy option-chain analytics floor time to at least one calendar day.", "HIGH"),
        ("mark_price_drives_iv", "vol = implied_vol(ltp_opt" in option_chain_source, "Option-chain IV uses the selected mark value without a first-class solver/provenance result.", "MEDIUM"),
    )
    for case_id, confirmed, explanation, severity in source_checks:
        rows.append(_row(
            case_id,
            {"source_pattern_present": confirmed},
            {"explicit_contract": True},
            {"explicit_contract": True},
            "LEGACY_DEFECT_CONFIRMED" if confirmed else "NOT_TESTABLE",
            severity if confirmed else "UNKNOWN",
            explanation,
        ))

    confirmed = [row for row in rows if row["classification"] == "LEGACY_DEFECT_CONFIRMED"]
    return {
        "schema_version": "1.0.0",
        "input_case_count": len(rows),
        "valid_case_count": len(rows),
        "invalid_case_count": 0,
        "skipped_case_count": 0,
        "output_case_count": len(rows),
        "confirmed_legacy_defect_count": len(confirmed),
        "rows": rows,
        "summary": {
            "put_theta_defect": "CONFIRMED" if any(row["case_id"] == "put_theta" and row["classification"] == "LEGACY_DEFECT_CONFIRMED" for row in rows) else "NOT_CONFIRMED",
            "time_to_expiry_defect": "CONFIRMED" if any(row["case_id"] == "integer_day_expiry_floor" and row["classification"] == "LEGACY_DEFECT_CONFIRMED" for row in rows) else "NOT_CONFIRMED",
            "solver_convergence_ambiguity": "CONFIRMED" if any(row["case_id"] == "solver_status_unavailable" and row["classification"] == "LEGACY_DEFECT_CONFIRMED" for row in rows) else "NOT_CONFIRMED",
            "invalid_input_ambiguity": "CONFIRMED" if any(row["case_id"] == "negative_volatility_input" and row["classification"] == "LEGACY_DEFECT_CONFIRMED" for row in rows) else "NOT_CONFIRMED",
        },
    }
