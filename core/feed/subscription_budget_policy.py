"""Pure subscription budget helpers for feed token selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

_DEFAULT_RANK: tuple[float, int, float, int, int] = (float("inf"), 1, float("inf"), 2, 0)


@dataclass(frozen=True)
class SubscriptionBudgetDecision:
    """Decision-only budget result with no websocket or broker side effects."""

    tokens: tuple[int, ...]
    budget_applied: bool
    budget: int
    dropped_tokens: tuple[int, ...]
    preserved_tokens: tuple[int, ...]
    preserve_exceeded: bool = False

    @property
    def dropped_count(self) -> int:
        return len(self.dropped_tokens)

    @property
    def preserved_count(self) -> int:
        return len(self.preserved_tokens)

    def to_payload(self) -> dict[str, Any]:
        return {
            "budget": int(self.budget),
            "budget_applied": bool(self.budget_applied),
            "dropped_count": int(self.dropped_count),
            "dropped_tokens": list(self.dropped_tokens),
            "preserved_count": int(self.preserved_count),
            "preserved_tokens": list(self.preserved_tokens),
            "preserve_exceeded": bool(self.preserve_exceeded),
            "kept_count": len(self.tokens),
            "kept_tokens": list(self.tokens),
        }


def normalize_positive_tokens(token_source: Iterable[Any] | None) -> tuple[int, ...]:
    """Return unique positive integer tokens in first-seen order."""

    out: list[int] = []
    seen: set[int] = set()
    for raw_token in list(token_source or []):
        try:
            token = int(raw_token)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def normalize_token_set(token_source: Iterable[Any] | None) -> frozenset[int]:
    return frozenset(normalize_positive_tokens(token_source))


def merge_preserve_tokens(
    *,
    underlying_tokens: Iterable[Any] | None = None,
    sticky_tokens: Iterable[Any] | None = None,
    active_trade_tokens: Iterable[Any] | None = None,
) -> frozenset[int]:
    preserve: set[int] = set(normalize_positive_tokens(underlying_tokens))
    preserve.update(normalize_positive_tokens(sticky_tokens))
    preserve.update(normalize_positive_tokens(active_trade_tokens))
    return frozenset(preserve)


def normalize_rank_tuple(value: Any, *, token: int) -> tuple[float, int, float, int, int]:
    try:
        row = tuple(value)  # type: ignore[arg-type]
    except Exception:
        row = ()
    default = _DEFAULT_RANK
    values: list[Any] = list(row[:5])
    while len(values) < 5:
        values.append(default[len(values)])
    try:
        return (float(values[0]), int(values[1]), float(values[2]), int(values[3]), int(values[4]))
    except Exception:
        return (default[0], default[1], default[2], default[3], int(token))


def rank_key_for_token(token: int, option_rank_by_token: Mapping[int, Sequence[Any]] | None = None) -> tuple[float, int, float, int, int]:
    ranks = option_rank_by_token or {}
    try:
        rank = ranks.get(int(token))  # type: ignore[union-attr]
    except Exception:
        rank = None
    if rank is None:
        return (_DEFAULT_RANK[0], _DEFAULT_RANK[1], _DEFAULT_RANK[2], _DEFAULT_RANK[3], int(token))
    return normalize_rank_tuple(rank, token=int(token))


def enforce_subscription_budget(
    desired_tokens: Iterable[Any] | None,
    *,
    max_tokens: int | None,
    option_rank_by_token: Mapping[int, Sequence[Any]] | None = None,
    underlying_tokens: Iterable[Any] | None = None,
    sticky_tokens: Iterable[Any] | None = None,
    active_trade_tokens: Iterable[Any] | None = None,
) -> SubscriptionBudgetDecision:
    """Apply deterministic feed subscription budget policy.

    Preserved tokens are always kept, even if they exceed the budget. Non-preserved
    candidates are sorted by option rank and clipped to the remaining budget.
    """

    ordered = normalize_positive_tokens(desired_tokens)
    try:
        budget = int(max_tokens or 0)
    except Exception:
        budget = 0
    preserve_set = merge_preserve_tokens(
        underlying_tokens=underlying_tokens,
        sticky_tokens=sticky_tokens,
        active_trade_tokens=active_trade_tokens,
    )
    preserved = tuple(token for token in ordered if token in preserve_set)
    if budget <= 0 or len(ordered) <= budget:
        return SubscriptionBudgetDecision(
            tokens=ordered,
            budget_applied=False,
            budget=budget,
            dropped_tokens=(),
            preserved_tokens=preserved,
            preserve_exceeded=False,
        )

    candidates = [token for token in ordered if token not in preserve_set]
    candidates.sort(key=lambda token: rank_key_for_token(int(token), option_rank_by_token))
    keep_budget = budget - len(preserved)
    preserve_exceeded = keep_budget < 0
    if keep_budget >= 0:
        kept = tuple(dict.fromkeys(tuple(preserved) + tuple(candidates[:keep_budget])))
    else:
        kept = tuple(dict.fromkeys(preserved))
    kept_set = set(kept)
    dropped = tuple(token for token in ordered if token not in kept_set)
    return SubscriptionBudgetDecision(
        tokens=kept,
        budget_applied=True,
        budget=budget,
        dropped_tokens=dropped,
        preserved_tokens=preserved,
        preserve_exceeded=preserve_exceeded,
    )


__all__ = [
    "SubscriptionBudgetDecision",
    "enforce_subscription_budget",
    "merge_preserve_tokens",
    "normalize_positive_tokens",
    "normalize_rank_tuple",
    "normalize_token_set",
    "rank_key_for_token",
]
