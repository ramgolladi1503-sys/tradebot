from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.option_analytics import (
    CalculationStatus,
    ModelInputs,
    OptionType,
    PricingModel,
    calculate_greeks,
    price_option,
    solve_implied_volatility,
)

IST = ZoneInfo("Asia/Kolkata")
OUTPUT = Path("research/option_analytics_v1/evidence.json")


def _inputs(model: PricingModel, option_type: OptionType, *, moneyness: float, days: float, volatility: float, rate: float) -> ModelInputs:
    valuation = datetime(2026, 7, 27, 10, 0, tzinfo=IST)
    expiry = valuation + timedelta(days=days)
    strike = 25000.0
    common = dict(
        model=model,
        option_type=option_type,
        valuation_timestamp=valuation,
        expiry_timestamp=expiry,
        strike=strike,
        risk_free_rate=rate,
        volatility=volatility,
    )
    if model is PricingModel.BLACK_SCHOLES_MERTON:
        return ModelInputs(**common, spot=strike * moneyness, dividend_yield=0.012)
    return ModelInputs(**common, forward=strike * moneyness)


def _finite_delta(inputs: ModelInputs) -> float:
    field = "spot" if inputs.model is PricingModel.BLACK_SCHOLES_MERTON else "forward"
    base = getattr(inputs, field)
    assert base is not None
    step = 0.01
    up = price_option(replace(inputs, **{field: base + step})).price
    down = price_option(replace(inputs, **{field: base - step})).price
    assert up is not None and down is not None
    return (up - down) / (2.0 * step)


def run() -> dict:
    rows = []
    for model in PricingModel:
        for option_type in OptionType:
            for moneyness in (0.90, 1.00, 1.10):
                for days in (0.25, 7.0):
                    for volatility in (0.10, 0.35):
                        for rate in (-0.01, 0.06):
                            inputs = _inputs(model, option_type, moneyness=moneyness, days=days, volatility=volatility, rate=rate)
                            pricing = price_option(inputs)
                            greeks = calculate_greeks(inputs)
                            solved = solve_implied_volatility(replace(inputs, volatility=0.20), pricing.price if pricing.price is not None else -1.0)
                            delta_fd = _finite_delta(inputs) if pricing.status is CalculationStatus.OK else None
                            parity_key = f"{model.value}:{moneyness}:{days}:{volatility}:{rate}"
                            rows.append(
                                {
                                    "case_id": f"{parity_key}:{option_type.value}",
                                    "model": model.value,
                                    "option_type": option_type.value,
                                    "moneyness": moneyness,
                                    "days": days,
                                    "volatility": volatility,
                                    "rate": rate,
                                    "price_status": pricing.status.value,
                                    "price": pricing.price,
                                    "lower_bound": pricing.lower_price_bound,
                                    "upper_bound": pricing.upper_price_bound,
                                    "greeks_status": greeks.status.value,
                                    "delta": greeks.delta,
                                    "delta_finite_difference": delta_fd,
                                    "delta_absolute_error": abs(greeks.delta - delta_fd) if greeks.delta is not None and delta_fd is not None else None,
                                    "iv_status": solved.status.value,
                                    "iv": solved.implied_volatility,
                                    "iv_identifiable": bool(pricing.price is not None and pricing.lower_price_bound is not None and pricing.price - pricing.lower_price_bound > 1e-8),
                                    "iv_absolute_error": abs(solved.implied_volatility - volatility) if solved.implied_volatility is not None else None,
                                    "iv_price_error": solved.absolute_price_error,
                                }
                            )

    parity = []
    grouped: dict[tuple, dict[str, dict]] = {}
    for row in rows:
        key = (row["model"], row["moneyness"], row["days"], row["volatility"], row["rate"])
        grouped.setdefault(key, {})[row["option_type"]] = row
    for key, pair in sorted(grouped.items()):
        call = pair[OptionType.CALL.value]
        put = pair[OptionType.PUT.value]
        model, moneyness, days, volatility, rate = key
        inputs = _inputs(PricingModel(model), OptionType.CALL, moneyness=moneyness, days=days, volatility=volatility, rate=rate)
        t = days / 365.0
        if inputs.model is PricingModel.BLACK_SCHOLES_MERTON:
            assert inputs.spot is not None
            expected = inputs.spot * math.exp(-inputs.dividend_yield * t) - inputs.strike * math.exp(-inputs.risk_free_rate * t)
        else:
            assert inputs.forward is not None
            expected = math.exp(-inputs.risk_free_rate * t) * (inputs.forward - inputs.strike)
        residual = (call["price"] - put["price"]) - expected
        parity.append({"key": list(key), "residual": residual})

    failures = []
    for row in rows:
        if row["price_status"] != "OK" or row["greeks_status"] != "OK" or row["iv_status"] != "OK":
            failures.append({"case_id": row["case_id"], "reason": "status"})
        if row["delta_absolute_error"] is None or row["delta_absolute_error"] > 2e-5:
            failures.append({"case_id": row["case_id"], "reason": "delta_error"})
        if row["iv_identifiable"] and (row["iv_absolute_error"] is None or row["iv_absolute_error"] > 2e-8):
            failures.append({"case_id": row["case_id"], "reason": "iv_error"})
    for item in parity:
        if abs(item["residual"]) > 1e-8:
            failures.append({"case_id": str(item["key"]), "reason": "parity"})

    payload = {
        "schema_version": "1.0.0",
        "case_count": len(rows),
        "parity_case_count": len(parity),
        "failure_count": len(failures),
        "iv_identifiable_case_count": sum(1 for row in rows if row["iv_identifiable"]),
        "iv_lower_bound_case_count": sum(1 for row in rows if not row["iv_identifiable"]),
        "verdict": "PASS" if not failures else "FAIL",
        "thresholds": {
            "delta_absolute_error": 2e-5,
            "iv_absolute_error": 2e-8,
            "parity_absolute_residual": 1e-8,
        },
        "rows": rows,
        "parity": parity,
        "failures": failures,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    payload["semantic_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    payload = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("case_count", "parity_case_count", "failure_count", "verdict", "semantic_sha256")}, sort_keys=True))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
