from __future__ import annotations

import math

_SQRT_TWO = math.sqrt(2.0)
_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT_TWO))


def normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_TWO_PI
