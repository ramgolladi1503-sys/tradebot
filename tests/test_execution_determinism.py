from core.execution_engine import ExecutionEngine


class DummyTrade:
    def __init__(self, side="BUY", trade_id="T-DET-1", run_id="RUN-1", qty=1):
        self.side = side
        self.trade_id = trade_id
        self.run_id = run_id
        self.qty = qty


def _snapshot_seq(quotes):
    idx = {"i": 0}

    def _fn():
        i = idx["i"]
        if i >= len(quotes):
            return quotes[-1]
        idx["i"] += 1
        return dict(quotes[i])

    return _fn


def test_same_inputs_same_run_id_same_fill_result():
    quotes = [
        {"bid": 100.0, "ask": 101.0, "ts": 1700000000.0},
        {"bid": 100.0, "ask": 99.5, "ts": 1700000000.1},
        {"bid": 100.0, "ask": 99.0, "ts": 1700000000.2},
    ]
    trade_1 = DummyTrade(side="BUY", trade_id="T-DET-42", run_id="RUN-DET-A")
    trade_2 = DummyTrade(side="BUY", trade_id="T-DET-42", run_id="RUN-DET-A")

    eng_1 = ExecutionEngine()
    eng_2 = ExecutionEngine()

    result_1 = eng_1.simulate_limit_fill(
        trade=trade_1,
        limit_price=100.0,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0.0,
        max_chase_pct=0.0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=0.4,
        run_id="RUN-DET-A",
    )
    result_2 = eng_2.simulate_limit_fill(
        trade=trade_2,
        limit_price=100.0,
        snapshot_fn=_snapshot_seq(quotes),
        timeout_sec=0.05,
        poll_sec=0.0,
        max_chase_pct=0.0,
        spread_widen_pct=1.0,
        max_spread_pct=1.0,
        fill_prob=0.4,
        run_id="RUN-DET-A",
    )

    assert result_1[0] == result_2[0]  # filled flag
    assert result_1[1] == result_2[1]  # fill price
    assert result_1[2].get("reason_if_aborted") == result_2[2].get("reason_if_aborted")


def test_deterministic_slippage_same_inputs_same_output():
    eng = ExecutionEngine()
    s1 = eng.estimate_slippage(100.0, 101.0, volume=15000, qty=10, vol_z=0.5)
    s2 = eng.estimate_slippage(100.0, 101.0, volume=15000, qty=10, vol_z=0.5)
    s3 = eng.estimate_slippage(100.0, 101.0, volume=4000, qty=200, vol_z=2.0)

    assert s1 == s2
    assert s3 > s1
