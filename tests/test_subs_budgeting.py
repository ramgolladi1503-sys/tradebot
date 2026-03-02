import core.kite_depth_ws as ws


def _build_budget_fixture():
    underlying_tokens = {1, 2}
    sticky_tokens = {3, 4}
    active_trade_tokens = {5, 6}
    preserve = list(sorted(underlying_tokens | sticky_tokens | active_trade_tokens))
    near_tokens = list(range(7, 81))  # 74 tokens
    far_otm_tokens = list(range(81, 101))  # 20 tokens
    desired_tokens = preserve + near_tokens + far_otm_tokens

    option_rank_by_token = {}
    for i, token in enumerate(near_tokens, start=1):
        option_rank_by_token[int(token)] = (float(i), 0, float(i), 0, int(token))
    for i, token in enumerate(far_otm_tokens, start=1):
        option_rank_by_token[int(token)] = (1000.0 + float(i), 1, 1000.0 + float(i), 1, int(token))

    return {
        "desired_tokens": desired_tokens,
        "underlying_tokens": underlying_tokens,
        "sticky_tokens": sticky_tokens,
        "active_trade_tokens": active_trade_tokens,
        "near_tokens": near_tokens,
        "far_otm_tokens": far_otm_tokens,
        "option_rank_by_token": option_rank_by_token,
    }


def test_budget_prunes_farthest_otm_first_when_desired_exceeds_budget(monkeypatch):
    ctx = _build_budget_fixture()
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    kept, truncated, meta = ws._enforce_subscription_budget(
        ctx["desired_tokens"],
        max_tokens=80,
        option_rank_by_token=ctx["option_rank_by_token"],
        underlying_tokens=ctx["underlying_tokens"],
        sticky_tokens=ctx["sticky_tokens"],
        active_trade_tokens=ctx["active_trade_tokens"],
    )

    assert truncated is True
    assert len(kept) == 80
    assert set(meta["dropped_tokens"]) == set(ctx["far_otm_tokens"])


def test_budget_keeps_underlying_sticky_and_active_trade_tokens(monkeypatch):
    ctx = _build_budget_fixture()
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    kept, _truncated, _meta = ws._enforce_subscription_budget(
        ctx["desired_tokens"],
        max_tokens=80,
        option_rank_by_token=ctx["option_rank_by_token"],
        underlying_tokens=ctx["underlying_tokens"],
        sticky_tokens=ctx["sticky_tokens"],
        active_trade_tokens=ctx["active_trade_tokens"],
    )

    preserve = ctx["underlying_tokens"] | ctx["sticky_tokens"] | ctx["active_trade_tokens"]
    assert preserve.issubset(set(kept))


def test_budget_enforcement_emits_log_event():
    ctx = _build_budget_fixture()
    events = []

    def _capture(event, payload=None):
        events.append((str(event), dict(payload or {})))

    old = ws._log_ws
    ws._log_ws = _capture
    try:
        ws._enforce_subscription_budget(
            ctx["desired_tokens"],
            max_tokens=80,
            option_rank_by_token=ctx["option_rank_by_token"],
            underlying_tokens=ctx["underlying_tokens"],
            sticky_tokens=ctx["sticky_tokens"],
            active_trade_tokens=ctx["active_trade_tokens"],
        )
    finally:
        ws._log_ws = old

    budget_logs = [payload for event, payload in events if event == "FEED_SUBSCRIPTION_BUDGET_ENFORCED"]
    assert budget_logs, "expected FEED_SUBSCRIPTION_BUDGET_ENFORCED log"
    assert int(budget_logs[-1].get("desired_tokens", 0)) == 100
    assert int(budget_logs[-1].get("max_tokens", 0)) == 80
    assert int(budget_logs[-1].get("dropped_tokens", 0)) == 20
