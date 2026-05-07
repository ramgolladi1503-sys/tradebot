from __future__ import annotations

import types


def test_stale_option_prune_requires_consecutive_windows(monkeypatch):
    """
    Regression guard:
    - Option ticks can be 3-6s sparse intraday.
    - We must not prune tokens immediately on a single stale evaluation.
    """

    import core.kite_depth_ws as m

    # Make the test deterministic and independent of wall-clock time.
    monkeypatch.setattr(m, "_DEPTH_WS_START_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(m, "_STALE_PRUNE_STRIKES_BY_TOKEN", {}, raising=False)

    # Config: no grace, very low max age, but require 3 consecutive stale windows.
    cfg = types.SimpleNamespace(
        FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE=True,
        FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC=0.0,
        FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC=1.0,
        FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS=3,
        FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK=False,
    )
    monkeypatch.setattr(m, "cfg", cfg, raising=False)

    # Freeze time.
    t = {"now": 1000.0}
    monkeypatch.setattr(m, "now_utc_epoch", lambda: float(t["now"]), raising=False)

    # Two option tokens for one symbol.
    tokens = [11, 12]
    token_to_symbol = {11: "NIFTY", 12: "NIFTY"}
    option_rank_by_token = {11: (0.0, 0, 0.0, 0, 0), 12: (0.0, 0, 0.0, 0, 0)}

    # Provide "stale" ticks (age 2s > max_age 1s) for both tokens.
    monkeypatch.setattr(
        m,
        "get_latest_tick_rows_db",
        lambda toks: {int(tok): {"ts_epoch": float(t["now"]) - 2.0} for tok in toks},
        raising=False,
    )

    # 1st evaluation: stale, but should not prune yet.
    out1, meta1 = m._prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol={"NIFTY": 0},
    )
    assert sorted(out1) == sorted(tokens)
    assert int(meta1.get("pruned_count") or 0) == 0

    # 2nd evaluation: still stale, still no prune.
    out2, meta2 = m._prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol={"NIFTY": 0},
    )
    assert sorted(out2) == sorted(tokens)
    assert int(meta2.get("pruned_count") or 0) == 0

    # 3rd evaluation: now pruning allowed (stale for 3 consecutive windows).
    out3, meta3 = m._prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol={"NIFTY": 0},
    )
    assert int(meta3.get("consecutive_stale_windows_required") or 0) == 3
    assert int(meta3.get("pruned_count") or 0) == 2
    assert out3 == []

