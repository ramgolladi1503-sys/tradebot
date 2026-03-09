from __future__ import annotations

import time

from config import config as cfg
from core.contracts.invariants import assert_invariants
from core.gating import apply_hard_gates, gate_decision
from core.market_snapshot_builder import build_market_snapshot
from core.orders.execution_plan import ExecutionPlan
from core.tick_store import insert_tick


def _configure_runtime(monkeypatch, tmp_path, *, min_option_tokens: int) -> None:
    db_path = tmp_path / "golden_mvp.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", int(min_option_tokens), raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", int(min_option_tokens), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_STALE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", True, raising=False)
    # Deterministic strict-mode behavior for freshness computation.
    monkeypatch.setattr("core.freshness_sla.is_market_open_ist", lambda: True)


def _resolve_option_tokens_with_mock(monkeypatch) -> list[int]:
    token_map = {
        (24600, "CE"): 910_001,
        (24600, "PE"): 910_002,
        (24650, "CE"): 910_003,
        (24650, "PE"): 910_004,
    }

    def _fake_resolve(symbol, expiry_date, strike, option_type, exchange=None):
        del expiry_date, exchange
        key = (int(float(strike)), str(option_type).upper())
        token = token_map.get(key)
        if token is None:
            return None
        return {
            "instrument_token": int(token),
            "tradingsymbol": f"{symbol}{key[0]}{key[1]}",
            "exchange": "NFO",
            "segment": "NFO-OPT",
        }

    monkeypatch.setattr("core.option_token_resolver.resolve_option_token", _fake_resolve)

    from core.option_token_resolver import resolve_option_token

    out: list[int] = []
    for strike in (24600, 24650):
        for option_type in ("CE", "PE"):
            payload = resolve_option_token("NIFTY", "2026-03-02", strike, option_type, exchange="NFO")
            if not payload:
                continue
            out.append(int(payload["instrument_token"]))
    # Deterministic ordering for snapshot_id stability.
    return sorted(set(out))


def _seed_ticks(index_token: int, option_tokens: list[int], *, age_sec: float) -> None:
    now_epoch = float(time.time())
    ts_epoch = now_epoch - float(age_sec)
    assert insert_tick(ts=ts_epoch, token=index_token, last_price=24_700.0, volume=100_000, oi=0)
    for idx, token in enumerate(option_tokens):
        assert insert_tick(
            ts=ts_epoch,
            token=int(token),
            last_price=100.0 + float(idx),
            volume=1_000 + idx,
            oi=10_000 + idx,
        )


def _patch_now_epoch(monkeypatch, epoch: float) -> None:
    monkeypatch.setattr("core.freshness_sla.now_utc_epoch", lambda: float(epoch))
    monkeypatch.setattr("core.market_snapshot_builder.now_utc_epoch", lambda: float(epoch))


def _build_candidate(snapshot: dict, *, decision_id: str) -> dict:
    freshness = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    return {
        "symbol": "NIFTY",
        "side": "BUY",
        "qty": 1,
        "current_ltp": 101.0,
        "spread_pct": 0.01,
        "volume": 10_000,
        "option_age_sec": freshness.get("max_tick_age_sec"),
        "confidence": 0.72,
        "decision_id": decision_id,
        "snapshot_id": snapshot["snapshot_id"],
    }


def test_mvp_pipeline_snapshot_gates_and_execution_plan(monkeypatch, tmp_path):
    """
    Golden MVP pipeline:
    token resolution (mocked) -> sqlite ticks -> snapshot -> gating -> execution plan (paper).
    """
    _configure_runtime(monkeypatch, tmp_path, min_option_tokens=4)
    base_now_epoch = float(time.time())
    _patch_now_epoch(monkeypatch, base_now_epoch)
    index_token = 256_265
    option_tokens = _resolve_option_tokens_with_mock(monkeypatch)
    assert len(option_tokens) == 4

    # Fresh path: hard gates should pass and plan should carry snapshot_id.
    _seed_ticks(index_token, option_tokens, age_sec=1.0)
    fresh_snapshot = build_market_snapshot(
        "NIFTY",
        index_token=index_token,
        option_tokens=option_tokens,
        strike_window={"atm": 24600, "step": 50, "around": 6},
        expiry_date="2026-03-02",
    )
    assert_invariants(fresh_snapshot, stage="golden_test")
    assert fresh_snapshot["health"]["ok"] is True

    decision = gate_decision(_build_candidate(fresh_snapshot, decision_id="dec-fresh-001"), fresh_snapshot)
    decision_record = {
        **decision,
        "snapshot_id": fresh_snapshot["snapshot_id"],
        "decision_id": "dec-fresh-001",
    }
    assert decision_record["snapshot_id"] == fresh_snapshot["snapshot_id"]
    hard_pass, hard_reasons = apply_hard_gates(
        _build_candidate(fresh_snapshot, decision_id="dec-fresh-001"),
        fresh_snapshot,
    )
    assert hard_pass is True
    assert hard_reasons == []

    plan = ExecutionPlan.from_trade(
        {
            "symbol": "NIFTY",
            "instrument_token": option_tokens[0],
            "side": "BUY",
            "qty": 1,
            "order_type": "LIMIT",
            "stop_loss": 95.0,
            "target": 120.0,
            "snapshot_id": decision_record["snapshot_id"],
            "decision_id": decision_record["decision_id"],
            "signal_id": "sig-fresh-001",
            "timestamp_epoch": fresh_snapshot["timestamp_epoch"],
        },
        mode="PAPER",
    )
    assert plan.snapshot_id == fresh_snapshot["snapshot_id"]
    assert plan.decision_id == "dec-fresh-001"

    # Stale path: hard gate must block on stale LTP.
    _patch_now_epoch(monkeypatch, base_now_epoch + 4_000.0)
    stale_snapshot = build_market_snapshot(
        "NIFTY",
        index_token=index_token,
        option_tokens=option_tokens,
        strike_window={"atm": 24600, "step": 50, "around": 6},
        expiry_date="2026-03-02",
    )
    stale_candidate = _build_candidate(stale_snapshot, decision_id="dec-stale-001")
    stale_pass, stale_reasons = apply_hard_gates(stale_candidate, stale_snapshot)
    assert stale_pass is False
    assert "HARD_STALE_LTP" in stale_reasons
    stale_decision = {
        **gate_decision(stale_candidate, stale_snapshot),
        "snapshot_id": stale_snapshot["snapshot_id"],
    }
    assert stale_decision["snapshot_id"] == stale_snapshot["snapshot_id"]

    # Low token coverage path: threshold must block in snapshot health.
    _configure_runtime(monkeypatch, tmp_path, min_option_tokens=10)
    low_cov_snapshot = build_market_snapshot(
        "NIFTY",
        index_token=index_token,
        option_tokens=option_tokens[:2],
        strike_window={"atm": 24600, "step": 50, "around": 6},
        expiry_date="2026-03-02",
    )
    low_cov_codes = [
        str(item.get("code"))
        for item in list((low_cov_snapshot.get("health") or {}).get("blockers") or [])
    ]
    assert "TOKEN_COVERAGE_BELOW_THRESHOLD" in low_cov_codes
