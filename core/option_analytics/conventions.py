from __future__ import annotations

import math
from datetime import datetime

from .contracts import CalculationStatus, DayCountConvention

SECONDS_PER_ACT_365F_YEAR = 365.0 * 24.0 * 60.0 * 60.0


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_aware_datetime(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def year_fraction(
    valuation_timestamp: datetime,
    expiry_timestamp: datetime,
    day_count: DayCountConvention = DayCountConvention.ACT_365F,
) -> tuple[CalculationStatus, float | None, float | None]:
    if not validate_aware_datetime(valuation_timestamp) or not validate_aware_datetime(expiry_timestamp):
        return CalculationStatus.INVALID_INPUT, None, None
    seconds = (expiry_timestamp - valuation_timestamp).total_seconds()
    if seconds < 0:
        return CalculationStatus.INVALID_INPUT, seconds, None
    if day_count is not DayCountConvention.ACT_365F:
        return CalculationStatus.INVALID_INPUT, seconds, None
    return (
        CalculationStatus.EXPIRED if seconds == 0 else CalculationStatus.OK,
        seconds,
        seconds / SECONDS_PER_ACT_365F_YEAR,
    )
