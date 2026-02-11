from __future__ import annotations

from pathlib import Path

import pandas as pd

from rl.trading_env import TradingEnv


def _write_env_csv(path: Path, ltp_values):
    rows = []
    for index, ltp in enumerate(ltp_values):
        rows.append(
            {
                "ltp": float(ltp),
                "bid": float(ltp - 0.1),
                "ask": float(ltp + 0.1),
                "spread_pct": 0.001,
                "volume": 1000 + index,
                "atr": 1.0,
                "vwap_dist": 0.01,
                "moneyness": 0.0,
                "is_call": 1.0,
                "vwap_slope": 0.01,
                "rsi_mom": 0.1,
                "vol_z": 0.2,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_reward_changes_with_price_and_position(tmp_path: Path):
    csv_path = tmp_path / "env.csv"
    _write_env_csv(csv_path, [100, 101, 102, 103])

    env = TradingEnv(
        data_csv=str(csv_path),
        transaction_cost_bps=0.0,
        slippage_bps=0.0,
        reward_clip=10.0,
    )
    env.reset()
    _, reward_long, _, _, info_long = env.step(1)
    assert reward_long > 0.0
    assert info_long["position_after"] == 1

    env.reset()
    _, reward_short, _, _, info_short = env.step(2)
    assert reward_short < 0.0
    assert info_short["position_after"] == -1


def test_transaction_cost_and_slippage_reduce_reward(tmp_path: Path):
    csv_path = tmp_path / "flat_env.csv"
    _write_env_csv(csv_path, [100, 100, 100, 100])

    env_zero_cost = TradingEnv(
        data_csv=str(csv_path),
        transaction_cost_bps=0.0,
        slippage_bps=0.0,
        reward_clip=10.0,
    )
    env_with_cost = TradingEnv(
        data_csv=str(csv_path),
        transaction_cost_bps=10.0,
        slippage_bps=10.0,
        reward_clip=10.0,
    )

    env_zero_cost.reset()
    _, reward_zero, _, _, _ = env_zero_cost.step(1)
    env_with_cost.reset()
    _, reward_cost, _, _, _ = env_with_cost.step(1)
    assert reward_zero == 0.0
    assert reward_cost < reward_zero


def test_done_reset_and_debug_logging(tmp_path: Path):
    csv_path = tmp_path / "len_env.csv"
    debug_path = tmp_path / "debug.jsonl"
    _write_env_csv(csv_path, [100, 101, 102, 103, 104, 105])

    env = TradingEnv(
        data_csv=str(csv_path),
        transaction_cost_bps=0.0,
        slippage_bps=0.0,
        reward_clip=10.0,
        debug_steps=2,
        debug_log_path=str(debug_path),
    )

    env.reset()
    done = False
    steps = 0
    while not done:
        _, _, done, _, _ = env.step(0)
        steps += 1
    assert steps == 5  # len(data)-1 transitions

    env.reset()
    assert env.ptr == 0
    assert env.steps == 0

    assert debug_path.exists()
    lines = [line for line in debug_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert '"reward"' in lines[0]
