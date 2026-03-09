#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.feed.runtime_store import write_runtime_snapshot
from core.runtime_health import get_runtime_health
from core.tick_store import init_ticks, insert_tick
from core.time_utils import now_utc_epoch
from strategies.trade_builder import TradeBuilder


class _ExecStub:
    def spread_ok(self, bid, ask, price, **_kwargs):
        try:
            bid_f = float(bid)
            ask_f = float(ask)
            px_f = float(price)
        except Exception:
            return False
        if px_f <= 0 or ask_f < bid_f:
            return False
        return ((ask_f - bid_f) / px_f) <= 0.35

    def estimate_slippage(self, *_args, **_kwargs):
        return 0.0


def main() -> int:
    db_path = Path(cfg.TRADE_DB_PATH).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_ticks()
    ts_epoch = float(now_utc_epoch())
    insert_tick(ts=ts_epoch, token=256265, last_price=24700.0, volume=0, oi=0)
    write_runtime_snapshot(
        {
            "ts_epoch": ts_epoch,
            "ws_connected": True,
            "subscribed_tokens_count": 74,
            "intended_tokens_count": 74,
            "subscribed_tokens_sample": [256265],
            "last_ws_tick_epoch": ts_epoch,
            "source": "harness",
            "runtime_state": "RUNNING",
            "last_error": "",
        }
    )

    cfg.EXPIRY_LOTTO_MODE = True
    cfg.EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM = False
    cfg.EXPIRY_LOTTO_TARGET_CANDIDATES = 4
    cfg.EXPIRY_LOTTO_MIN_OPTION_TOKENS = 4
    builder = TradeBuilder(predictor=object(), execution=_ExecStub())
    builder._resolve_option_contract = lambda symbol, strike, opt_type, expiry, market_data: {
        "expiry": "2026-03-02",
        "tradingsymbol": f"{symbol}-2026-03-02-{int(float(strike))}-{opt_type}",
        "instrument_token": int(float(strike) * 10),
    }
    builder._identity_fields = lambda symbol, instrument, expiry, strike, right, qty_lots: (
        "OPT",
        f"{symbol}|{expiry}|{strike}|{right}",
        50,
        None,
    )
    builder.trade_intent_flags = lambda *args, **kwargs: {
        "tradable": True,
        "tradable_reasons_blocking": [],
        "planning_only": True,
        "execution_allowed": False,
        "execution_reason": "EXPIRY_LOTTO_MODE",
        "source_flags": {},
    }
    chain = []
    for strike, ltp in [(24600, 95.0), (24650, 90.0), (24700, 88.0), (24750, 84.0), (24800, 79.0)]:
        chain.append(
            {
                "type": "CE",
                "strike": float(strike),
                "ltp": float(ltp),
                "bid": round(float(ltp) * 0.98, 2),
                "ask": round(float(ltp) * 1.02, 2),
                "volume": 1000,
                "instrument_token": int(strike * 10),
                "tradingsymbol": f"NIFTYEXP{strike}CE",
            }
        )
    trades = builder.build_expiry_lotto_candidates(
        {
            "symbol": "NIFTY",
            "ltp": 24705.0,
            "atr": 120.0,
            "ltp_change_window": 30.0,
            "day_type": "EXPIRY_DAY",
            "trend_state": "UP",
            "orb_bias": "UP",
            "option_chain": chain,
            "market_open": True,
        }
    )
    payload = {
        "runtime_health": get_runtime_health(),
        "expiry_lotto_count": len(trades),
        "expiry_lotto_ids": [t.trade_id for t in trades],
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
