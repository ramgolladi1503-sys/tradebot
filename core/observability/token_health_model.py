"""Role-Aware, Coverage-Aware Token Health and Strategy Dependency Graph.

Replaces the simplistic "one stale token => whole system degraded" interpretation
with role-aware classification, dependency mapping, and evidence-based health.
Read-only. Preserves order_authority=false, broker_write_authority=false.
"""

from __future__ import annotations

import collections
import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class TokenRole(str, enum.Enum):
    CRITICAL_UNDERLYING = "CRITICAL_UNDERLYING"
    CRITICAL_STRATEGY_INPUT = "CRITICAL_STRATEGY_INPUT"
    REQUIRED_OPTION_UNIVERSE = "REQUIRED_OPTION_UNIVERSE"
    OPTIONAL_OPTION_UNIVERSE = "OPTIONAL_OPTION_UNIVERSE"
    DEPTH_REQUIRED = "DEPTH_REQUIRED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    UNKNOWN_ROLE = "UNKNOWN_ROLE"


class SystemHealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    PARTIAL_HEALTHY = "PARTIAL_HEALTHY"
    DEGRADED_NONFATAL = "DEGRADED_NONFATAL"
    STRATEGY_SPECIFIC_BLOCK = "STRATEGY_SPECIFIC_BLOCK"
    SYSTEM_CRITICAL_BLOCK = "SYSTEM_CRITICAL_BLOCK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TokenObservation:
    """Observation status for an individual token."""

    token: int
    symbol: str
    role: TokenRole
    requested: bool
    acknowledged: bool
    with_ticks: bool
    is_fresh: bool
    last_tick_age_sec: float
    is_missing: bool = False
    dependent_strategies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleMetrics:
    """Metrics aggregated per token role."""

    role: str
    requested: int
    acknowledged: int
    with_ticks: int
    fresh: int
    stale: int
    missing: int
    coverage_ratio: float
    freshness_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoleAwareHealthReport:
    """Evaluated role-aware health state and strategy impact."""

    overall_health: str
    reason_code: str
    critical_underlying_healthy: bool
    role_metrics: dict[str, dict[str, Any]]
    affected_strategies: tuple[str, ...]
    unaffected_strategies: tuple[str, ...]
    system_critical: bool
    diagnostic_details: Mapping[str, Any]
    is_order_action: bool = False
    broker_write_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["affected_strategies"] = list(self.affected_strategies)
        data["unaffected_strategies"] = list(self.unaffected_strategies)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


class TokenDependencyGraph:
    """Maps tokens and data roles to dependent strategies and evaluates role-aware health."""

    def __init__(
        self,
        required_option_quorum: float = 0.80,
        max_freshness_age_sec: float = 3.0,
        registered_strategies: Sequence[str] | None = None,
    ) -> None:
        self.required_option_quorum = max(0.1, min(1.0, float(required_option_quorum)))
        self.max_freshness_age_sec = max(0.5, float(max_freshness_age_sec))
        # token -> set of strategy_ids
        self._token_dependencies: dict[int, set[str]] = collections.defaultdict(set)
        # token -> TokenRole
        self._token_roles: dict[int, TokenRole] = {}
        # token -> symbol
        self._token_symbols: dict[int, str] = {}
        # strategy -> set of required tokens
        self._strategy_tokens: dict[str, set[int]] = collections.defaultdict(set)
        # registered strategies
        self._registered_strategies: set[str] = set(str(s).strip() for s in registered_strategies) if registered_strategies else set()

    def register_token(
        self,
        token: int,
        symbol: str,
        role: TokenRole | str,
        dependent_strategies: Sequence[str] | None = None,
    ) -> None:
        tok = int(token)
        r = role if isinstance(role, TokenRole) else TokenRole(str(role))
        self._token_roles[tok] = r
        self._token_symbols[tok] = str(symbol).upper()

        if dependent_strategies:
            for s_id in dependent_strategies:
                s_norm = str(s_id).strip()
                self._token_dependencies[tok].add(s_norm)
                self._strategy_tokens[s_norm].add(tok)
                self._registered_strategies.add(s_norm)

    def register_strategy(self, strategy_id: str, required_tokens: Sequence[int] | None = None) -> None:
        s_norm = str(strategy_id).strip()
        self._registered_strategies.add(s_norm)
        if required_tokens:
            for tok in required_tokens:
                self._strategy_tokens[s_norm].add(int(tok))
                self._token_dependencies[int(tok)].add(s_norm)

    def evaluate_health(self, observations: Sequence[TokenObservation]) -> RoleAwareHealthReport:
        """Role-aware health evaluation according to governed rules:

        - Missing/stale OPTIONAL token => do NOT degrade whole system.
        - Missing/stale token required only by Strategy X => block/degrade Strategy X only.
        - Missing/stale critical NIFTY underlying token => system-critical block.
        - Partial option-universe coverage above policy quorum => PARTIAL_HEALTHY or DEGRADED_NONFATAL.
        - Coverage below strategy-required quorum => STRATEGY_SPECIFIC_BLOCK.
        """
        # Bucket observations by role
        by_role: dict[TokenRole, list[TokenObservation]] = collections.defaultdict(list)
        obs_map: dict[int, TokenObservation] = {}

        for obs in observations:
            by_role[obs.role].append(obs)
            obs_map[obs.token] = obs

        # Compute role metrics
        role_metrics: dict[str, dict[str, Any]] = {}
        for r in TokenRole:
            obs_list = by_role.get(r, [])
            requested = sum(1 for o in obs_list if o.requested)
            acknowledged = sum(1 for o in obs_list if o.acknowledged)
            with_ticks = sum(1 for o in obs_list if o.with_ticks)
            fresh = sum(1 for o in obs_list if o.is_fresh)
            stale = sum(1 for o in obs_list if (o.with_ticks and not o.is_fresh))
            missing = sum(1 for o in obs_list if o.is_missing or not o.with_ticks)

            cov_ratio = (with_ticks / requested) if requested > 0 else (1.0 if not obs_list else 0.0)
            fresh_ratio = (fresh / with_ticks) if with_ticks > 0 else (1.0 if not obs_list else 0.0)

            metric = RoleMetrics(
                role=r.value,
                requested=requested,
                acknowledged=acknowledged,
                with_ticks=with_ticks,
                fresh=fresh,
                stale=stale,
                missing=missing,
                coverage_ratio=cov_ratio,
                freshness_ratio=fresh_ratio,
            )
            role_metrics[r.value] = metric.to_dict()

        # Check CRITICAL_UNDERLYING
        crit_underlying_obs = by_role.get(TokenRole.CRITICAL_UNDERLYING, [])
        crit_healthy = True
        crit_issues: list[str] = []
        if crit_underlying_obs:
            for o in crit_underlying_obs:
                if not o.is_fresh or not o.with_ticks or o.is_missing:
                    crit_healthy = False
                    crit_issues.append(f"{o.symbol} (token {o.token}) stale/missing age={o.last_tick_age_sec:.2f}s")
        else:
            # If no underlying observation present, cannot prove healthy
            crit_healthy = False
            crit_issues.append("no_underlying_token_observations_present")

        # Check strategy-level impact
        affected_strategies: set[str] = set()
        for tok, s_set in self._token_dependencies.items():
            obs = obs_map.get(tok)
            # If token is stale or missing, all dependent strategies are affected
            if obs is None or not obs.is_fresh or not obs.with_ticks or obs.is_missing:
                affected_strategies.update(s_set)

        all_strategies = set(self._registered_strategies)
        unaffected_strategies = all_strategies - affected_strategies

        # Evaluate overall health status
        req_opt_metrics = role_metrics.get(TokenRole.REQUIRED_OPTION_UNIVERSE.value, {})
        req_opt_cov = req_opt_metrics.get("coverage_ratio", 1.0)
        req_opt_stale = req_opt_metrics.get("stale", 0)

        opt_universe_metrics = role_metrics.get(TokenRole.OPTIONAL_OPTION_UNIVERSE.value, {})
        opt_stale = opt_universe_metrics.get("stale", 0)

        if not crit_healthy:
            overall_status = SystemHealthStatus.SYSTEM_CRITICAL_BLOCK.value
            reason_code = "CRITICAL_UNDERLYING_STALE_OR_MISSING"
            system_critical = True
        elif req_opt_cov < self.required_option_quorum:
            overall_status = SystemHealthStatus.STRATEGY_SPECIFIC_BLOCK.value
            reason_code = f"REQUIRED_OPTION_COVERAGE_BELOW_QUORUM: {req_opt_cov:.2f} < {self.required_option_quorum:.2f}"
            system_critical = False
        elif req_opt_stale > 0 or affected_strategies:
            overall_status = SystemHealthStatus.DEGRADED_NONFATAL.value
            reason_code = f"PARTIAL_STALENESS_AFFECTING_{len(affected_strategies)}_STRATEGIES"
            system_critical = False
        elif opt_stale > 0:
            # Stale optional tokens only
            overall_status = SystemHealthStatus.PARTIAL_HEALTHY.value
            reason_code = f"OPTIONAL_TOKENS_STALE_COUNT_{opt_stale}_NONFATAL"
            system_critical = False
        else:
            overall_status = SystemHealthStatus.HEALTHY.value
            reason_code = "ALL_TOKENS_HEALTHY_AND_FRESH"
            system_critical = False

        return RoleAwareHealthReport(
            overall_health=overall_status,
            reason_code=reason_code,
            critical_underlying_healthy=crit_healthy,
            role_metrics=role_metrics,
            affected_strategies=tuple(sorted(affected_strategies)),
            unaffected_strategies=tuple(sorted(unaffected_strategies)),
            system_critical=system_critical,
            diagnostic_details={
                "critical_issues": crit_issues,
                "required_option_quorum": self.required_option_quorum,
                "max_freshness_age_sec": self.max_freshness_age_sec,
            },
            is_order_action=False,
            broker_write_authority=False,
        )
