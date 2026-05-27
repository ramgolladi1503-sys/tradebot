from core.feed.subscription_budget_policy import (
    enforce_subscription_budget,
    merge_preserve_tokens,
    normalize_positive_tokens,
    normalize_rank_tuple,
    rank_key_for_token,
)


def test_normalize_positive_tokens_preserves_first_seen_order_and_filters_bad_values():
    assert normalize_positive_tokens(["5", 3, 5, 0, -1, None, "bad", 7]) == (5, 3, 7)
    assert normalize_positive_tokens(None) == ()


def test_merge_preserve_tokens_unions_valid_sources():
    assert merge_preserve_tokens(
        underlying_tokens=[1, "2", 0],
        sticky_tokens=[2, 3, None],
        active_trade_tokens=["4", "bad"],
    ) == frozenset({1, 2, 3, 4})


def test_rank_tuple_normalization_and_default_key_are_deterministic():
    assert normalize_rank_tuple((1, "0", 25.5, "1", "10"), token=99) == (1.0, 0, 25.5, 1, 10)
    assert normalize_rank_tuple(("bad",), token=99) == (float("inf"), 1, float("inf"), 2, 99)
    assert rank_key_for_token(9, {9: (0.5, 0, 10.0, 0, 9)}) == (0.5, 0, 10.0, 0, 9)
    assert rank_key_for_token(9, {}) == (float("inf"), 1, float("inf"), 2, 9)


def test_budget_disabled_or_under_budget_preserves_tokens_without_applying_budget():
    decision = enforce_subscription_budget(
        [1, 2, 3],
        max_tokens=0,
        underlying_tokens={1},
        sticky_tokens={2},
    )
    assert decision.tokens == (1, 2, 3)
    assert decision.budget_applied is False
    assert decision.dropped_tokens == ()
    assert decision.preserved_tokens == (1, 2)
    assert decision.to_payload()["preserved_count"] == 2

    under_budget = enforce_subscription_budget([1, 2, 3], max_tokens=5)
    assert under_budget.tokens == (1, 2, 3)
    assert under_budget.budget_applied is False


def test_budget_keeps_preserved_tokens_and_best_ranked_candidates():
    decision = enforce_subscription_budget(
        [100, 201, 202, 203, 204],
        max_tokens=3,
        underlying_tokens={100},
        option_rank_by_token={
            201: (3.0, 1, 75.0, 1, 201),
            202: (1.0, 0, 25.0, 0, 202),
            203: (2.0, 0, 50.0, 1, 203),
            204: (4.0, 1, 100.0, 0, 204),
        },
    )
    assert decision.budget_applied is True
    assert decision.tokens == (100, 202, 203)
    assert decision.dropped_tokens == (201, 204)
    assert decision.preserved_tokens == (100,)
    assert decision.preserve_exceeded is False
    payload = decision.to_payload()
    assert payload["budget"] == 3
    assert payload["kept_count"] == 3
    assert payload["dropped_count"] == 2


def test_preserved_tokens_are_kept_even_when_they_exceed_budget():
    decision = enforce_subscription_budget(
        [1, 2, 3, 4, 5],
        max_tokens=2,
        underlying_tokens={1, 2},
        sticky_tokens={3},
        active_trade_tokens={4},
        option_rank_by_token={5: (0, 0, 0, 0, 5)},
    )
    assert decision.budget_applied is True
    assert decision.tokens == (1, 2, 3, 4)
    assert decision.dropped_tokens == (5,)
    assert decision.preserved_tokens == (1, 2, 3, 4)
    assert decision.preserve_exceeded is True


def test_unknown_ranked_candidates_are_ordered_after_known_candidates_with_token_tiebreaker():
    decision = enforce_subscription_budget(
        [50, 30, 40, 20],
        max_tokens=2,
        option_rank_by_token={40: (1, 0, 1, 0, 40)},
    )
    assert decision.tokens == (40, 20)
    assert decision.dropped_tokens == (50, 30)
