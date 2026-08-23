from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict

from .contracts import CalculationStatus, SurfaceDiagnostic, SurfaceObservation


def diagnose_surface(
    observations: list[SurfaceObservation],
    *,
    neighbours_each_side: int = 2,
    minimum_neighbours: int = 2,
) -> tuple[SurfaceDiagnostic, ...]:
    if neighbours_each_side < 1 or minimum_neighbours < 1:
        raise ValueError("neighbour controls must be positive")

    groups: dict[tuple[object, ...], list[SurfaceObservation]] = defaultdict(list)
    for obs in observations:
        key = (
            obs.underlying_symbol,
            obs.valuation_timestamp,
            obs.expiry_timestamp,
            obs.option_type,
            obs.model,
        )
        groups[key].append(obs)

    output: dict[str, SurfaceDiagnostic] = {}
    observation_id_counts = Counter(obs.observation_id for obs in observations)
    for group in groups.values():
        strike_counts = Counter(obs.strike for obs in group)
        valid = [
            obs
            for obs in group
            if obs.implied_volatility is not None
            and math.isfinite(obs.implied_volatility)
            and obs.implied_volatility >= 0
            and obs.forward > 0
            and obs.strike > 0
            and obs.solver_status is CalculationStatus.OK
            and obs.quote_status is CalculationStatus.OK
            and strike_counts[obs.strike] == 1
        ]
        valid.sort(key=lambda obs: (obs.strike, obs.observation_id))
        positions = {obs.observation_id: index for index, obs in enumerate(valid)}

        for obs in group:
            if observation_id_counts[obs.observation_id] > 1:
                output[obs.observation_id] = SurfaceDiagnostic(
                    observation_id=obs.observation_id,
                    status=CalculationStatus.DUPLICATE_OBSERVATION_ID,
                    log_moneyness=_log_moneyness(obs),
                    neighbour_count=0,
                    local_median_iv=None,
                    absolute_iv_residual=None,
                    relative_iv_residual=None,
                    robust_scale=None,
                    robust_z_score=None,
                    warnings=("duplicate observation_id in input",),
                )
                continue
            if strike_counts[obs.strike] > 1:
                output[obs.observation_id] = SurfaceDiagnostic(
                    observation_id=obs.observation_id,
                    status=CalculationStatus.DUPLICATE_STRIKE,
                    log_moneyness=_log_moneyness(obs),
                    neighbour_count=0,
                    local_median_iv=None,
                    absolute_iv_residual=None,
                    relative_iv_residual=None,
                    robust_scale=None,
                    robust_z_score=None,
                    warnings=("duplicate strike in surface partition",),
                )
                continue
            if obs.observation_id not in positions:
                invalid_status = (
                    obs.solver_status
                    if obs.solver_status is not CalculationStatus.OK
                    else obs.quote_status
                    if obs.quote_status is not CalculationStatus.OK
                    else CalculationStatus.INVALID_INPUT
                )
                output[obs.observation_id] = SurfaceDiagnostic(
                    observation_id=obs.observation_id,
                    status=invalid_status,
                    log_moneyness=_log_moneyness(obs),
                    neighbour_count=0,
                    local_median_iv=None,
                    absolute_iv_residual=None,
                    relative_iv_residual=None,
                    robust_scale=None,
                    robust_z_score=None,
                    warnings=("observation excluded because quote or IV is invalid",),
                )
                continue
            index = positions[obs.observation_id]
            left = valid[max(0, index - neighbours_each_side):index]
            right = valid[index + 1:index + 1 + neighbours_each_side]
            neighbours = left + right
            if len(neighbours) < minimum_neighbours:
                output[obs.observation_id] = SurfaceDiagnostic(
                    observation_id=obs.observation_id,
                    status=CalculationStatus.INSUFFICIENT_SURFACE_NEIGHBOURS,
                    log_moneyness=_log_moneyness(obs),
                    neighbour_count=len(neighbours),
                    local_median_iv=None,
                    absolute_iv_residual=None,
                    relative_iv_residual=None,
                    robust_scale=None,
                    robust_z_score=None,
                    warnings=("not enough valid same-expiry same-option-type neighbours",),
                )
                continue
            neighbour_ivs = [float(item.implied_volatility) for item in neighbours if item.implied_volatility is not None]
            median_iv = statistics.median(neighbour_ivs)
            assert obs.implied_volatility is not None
            residual = obs.implied_volatility - median_iv
            deviations = [abs(value - median_iv) for value in neighbour_ivs]
            mad = statistics.median(deviations)
            robust_scale = 1.4826 * mad
            robust_z = residual / robust_scale if robust_scale > 0 else None
            output[obs.observation_id] = SurfaceDiagnostic(
                observation_id=obs.observation_id,
                status=CalculationStatus.OK,
                log_moneyness=_log_moneyness(obs),
                neighbour_count=len(neighbours),
                local_median_iv=median_iv,
                absolute_iv_residual=residual,
                relative_iv_residual=residual / median_iv if median_iv > 0 else None,
                robust_scale=robust_scale,
                robust_z_score=robust_z,
                warnings=("robust z-score unavailable because neighbour MAD is zero",) if robust_scale == 0 else (),
            )

    return tuple(output[obs.observation_id] for obs in observations)


def _log_moneyness(obs: SurfaceObservation) -> float | None:
    if obs.forward <= 0 or obs.strike <= 0:
        return None
    value = math.log(obs.strike / obs.forward)
    return value if math.isfinite(value) else None
