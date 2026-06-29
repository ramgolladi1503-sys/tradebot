from types import SimpleNamespace

from config import config as cfg
import core.orchestrator as orchestrator_module
from core.orchestrator import (
    Orchestrator,
    _augment_ranked_candidates_with_soft_reject,
    _build_top_opportunities_payload,
    _filter_invalid_cycle_candidates,
    _is_reportable_executable_candidate,
    _trade_attr,
)
from core.time_utils import now_utc_epoch


def test_build_decision_event_includes_shadow_fields():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 102000.0,
        "daily_pnl": 1200.0,
        "daily_pnl_pct": 0.0117647059,
        "open_risk": 500.0,
        "open_risk_pct": 0.0049019607,
    }
    orch.loss_streak = {"NIFTY": 1}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.02)
    orch._open_risk = lambda: 500.0

    trade = SimpleNamespace(
        trade_id="NIFTY-25600-CE-123",
        symbol="NIFTY",
        strategy="TEST_STRAT",
        regime="TREND",
        side="BUY",
        instrument="OPT",
        instrument_type="OPT",
        expiry="2026-02-12",
        strike=25600,
        option_type="CE",
        right="CE",
        qty_lots=1,
        qty_units=50,
        instrument_token=111,
        model_type="xgb",
        confidence=0.71,
        shadow_confidence=0.66,
        alpha_confidence=0.69,
        alpha_uncertainty=0.12,
        model_version="champ_xgb_v2",
        shadow_model_version="chall_xgb_v3",
    )
    market_data = {
        "symbol": "NIFTY",
        "market_context": {"execution_mode": "PAPER", "market_open": False},
        "regime": "TREND",
        "regime_probs": {"TREND": 0.7, "RANGE": 0.3},
        "shock_score": 0.1,
        "depth_imbalance": 0.05,
        "option_chain": [
            {
                "instrument_token": 111,
                "strike": 25600,
                "type": "CE",
                "ltp": 145.0,
                "bid": 144.5,
                "ask": 145.5,
                "bid_qty": 200,
                "ask_qty": 220,
            }
        ],
    }

    event = orch._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])

    assert event["champion_proba"] == 0.71
    assert event["challenger_proba"] == 0.66
    assert event["champion_model_id"] == "champ_xgb_v2"
    assert event["challenger_model_id"] == "chall_xgb_v3"
    assert event["xgb_proba"] == 0.71
    assert event["instrument_id"] is not None
    assert event["instrument_type"] == "OPT"
    assert event["right"] == "CE"
    assert event["qty_lots"] == 1
    assert event["qty_units"] == 50
    assert event["quote_age_sec"] is not None
    assert event["mode"] == "PAPER"
    assert event["allow_stale_quotes"] is True
    assert event["require_live_quotes"] is False


def test_build_decision_event_non_trade_uses_fallback_instrument_id():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
    }
    orch.loss_streak = {}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
    orch._open_risk = lambda: 0.0

    market_data = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_context": {"execution_mode": "SIM", "market_open": True},
        "quote_age_sec": 1.0,
    }

    event = orch._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["no_signal"])

    assert str(event["instrument_id"]).startswith("MISSING_CONTRACT::NIFTY:OPT:")
    assert event["quote_age_sec"] == 1.0


def test_build_decision_event_uses_latest_option_tick_epoch_fallback():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
    }
    orch.loss_streak = {}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
    orch._open_risk = lambda: 0.0

    market_data = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "quote_ts": None,
        "quote_ts_epoch": None,
        "quote_age_sec": None,
        "timestamp_epoch": None,
        "latest_option_tick_ts": now_utc_epoch() - 1.2,
        "latest_option_tick_age_sec": 1.2,
    }

    event = orch._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=[])

    assert event["quote_age_sec"] is not None
    assert float(event["quote_age_sec"]) >= 0.0
    assert "epoch_missing" not in list(event.get("veto_reasons") or [])


def test_build_decision_event_global_halt_does_not_inject_epoch_missing():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
    }
    orch.loss_streak = {}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
    orch._open_risk = lambda: 0.0

    event = orch._build_decision_event(
        None,
        {"symbol": "GLOBAL"},
        gatekeeper_allowed=False,
        veto_reasons=["latency_breach"],
    )

    reasons = list(event.get("veto_reasons") or [])
    assert "latency_breach" in reasons
    assert "epoch_missing" not in reasons
    assert event["quote_age_sec"] == -1.0


def test_candidate_pool_counts_handle_trade_objects_without_dict_get():
    real_candidates = [
        SimpleNamespace(latency_softened=True),
        {"latency_softened": False},
    ]
    synthetic_candidates = [
        SimpleNamespace(candidate_origin="fallback_min_breadth"),
        {"candidate_origin": "softened_builder_path"},
    ]

    softened = sum(1 for cand in real_candidates if bool(_trade_attr(cand, "latency_softened", False)))
    fallback = sum(
        1
        for cand in synthetic_candidates
        if str(_trade_attr(cand, "candidate_origin", "") or "") == "fallback_min_breadth"
    )

    assert softened == 1
    assert fallback == 1


def test_filter_invalid_cycle_candidates_drops_none_and_symbol_less(monkeypatch):
    monkeypatch.setattr(cfg, "ORCHESTRATOR_INVALID_CYCLE_CANDIDATE_SAMPLE_LIMIT", 2, raising=False)
    valid, invalid = _filter_invalid_cycle_candidates(
        [
            None,
            {"trade_id": "BAD-1"},
            {
                "trade_id": "GOOD-1",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "rank_score": 0.5,
            },
        ],
        symbol="NIFTY",
    )

    assert [row["trade_id"] for row in valid] == ["GOOD-1"]
    invalid_len = len(invalid)
    assert invalid_len == 2


def test_build_top_opportunities_payload_filters_invalid_candidates_before_phase2(monkeypatch):
    captured = {}

    def _fake_phase2(candidates, **kwargs):
        captured["candidates"] = list(candidates)
        return {
            "state": "NO_TRADE",
            "reason": "noop",
            "selected": None,
            "ranked": [],
            "next_active_trade": None,
        }

    monkeypatch.setattr(orchestrator_module, "run_engine_phase2", _fake_phase2)

    _build_top_opportunities_payload(
        candidates=[
            None,
            {"trade_id": "BAD-1"},
            {
                "trade_id": "GOOD-1",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "rank_score": 0.5,
            },
        ],
        executable_top_n=1,
        advisory_top_n=1,
        active_trade=None,
    )

    assert [row.get("trade_id") for row in captured["candidates"]] == ["GOOD-1"]


def test_augment_ranked_candidates_with_soft_reject_keeps_unrankable_soft_rows_out_of_ranked_pool(monkeypatch):
    class _Builder:
        _reject_ctx = {"reason": "latency_guard_cooldown", "gate_reasons": ["latency_guard_cooldown"]}

        def _attach_softened_candidate_contract(self, candidate, market_data=None):
            return dict(candidate)

    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_MAX_PER_SYMBOL", 3, raising=False)
    monkeypatch.setattr(orchestrator_module, "is_critical_reject_reason", lambda *args, **kwargs: False)

    ranked, soft, reject_reason, gate_reasons = _augment_ranked_candidates_with_soft_reject(
        trade_builder=_Builder(),
        ranked_candidates=[],
        market_data={"symbol": "NIFTY", "execution_mode": "LIVE"},
        execution_mode="LIVE",
        symbol="NIFTY",
    )

    assert ranked == []
    soft_len = len(soft)
    assert soft_len == 1
    assert soft[0]["symbol"] == "NIFTY"
    assert soft[0]["trade_id"].startswith("tbsoft_NIFTY_")
    assert soft[0]["rank_score"] is None
    assert reject_reason == "latency_guard_cooldown"
    assert gate_reasons == ["latency_guard_cooldown"]


def test_reportable_executable_candidate_allows_status_fallback_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", True, raising=False)
    candidate = {
        "trade_id": "NIFTY-123",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "candidate_status": "executable",
        "execution_status": None,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "eligible_for_execution": None,
        "execution_blocked": False,
        "execution_entry": 124.5,
    }
    assert _is_reportable_executable_candidate(candidate) is True


def test_reportable_executable_candidate_status_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", False, raising=False)
    candidate = {
        "trade_id": "NIFTY-124",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "candidate_status": "executable",
        "execution_status": None,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "execution_blocked": False,
        "execution_entry": 124.5,
    }
    assert _is_reportable_executable_candidate(candidate) is False


def test_build_cycle_market_data_attaches_feed_runtime_evidence(monkeypatch):
    orch = Orchestrator.__new__(Orchestrator)
    orch._cycle_market_snapshot_by_symbol = {}
    monkeypatch.setattr(
        orchestrator_module,
        "_read_latest_feed_runtime_payload",
        lambda: (
            {
                "ts_epoch": 2000.0,
                "ws_connected": True,
                "subscribed_option_tokens_count": 66,
                "last_option_tick_ts_by_symbol": {"NIFTY": 1999.2},
                "option_last_tick_age_by_symbol": {"NIFTY": 0.8},
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
                "option_tokens_subscribed_count_by_symbol": {"NIFTY": 24},
                "runtime_state": "RUNNING",
            },
            None,
        ),
        raising=False,
    )

    out = orch._build_cycle_market_data(
        [
            {
                "symbol": "NIFTY",
                "instrument": "OPT",
                "timestamp": 1999.5,
                "feed_health": {"time_sanity": {"ok": True}},
            }
        ]
    )

    out_len = len(out)
    assert out_len == 1
    row = out[0]
    assert row["ws_connected"] is True
    assert row["subscribed_option_tokens_count"] == 24
    assert row["latest_option_tick_ts"] == 1999.2
    assert row["latest_option_tick_age_sec"] == 0.8
    assert row["option_feed_block_reason"] == "OK"
    assert row["feed_timestamp_epoch"] == 2000.0
    assert row["timestamp_epoch"] == 1999.2
    assert isinstance(row.get("feed_health"), dict)
    assert row["feed_health"]["ws_connected"] is True
    assert row["feed_health"]["runtime_state"] == "RUNNING"


def test_build_decision_event_does_not_flag_unresolved_when_broker_identity_present():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
    }
    orch.loss_streak = {}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
    orch._open_risk = lambda: 0.0

    trade = SimpleNamespace(
        trade_id="NIFTY-TEST-IDENTITY",
        symbol="NIFTY",
        instrument="OPT",
        instrument_type="OPT",
        strike=24650,
        right="CE",
        option_type="CE",
        expiry="2026-04-23",
        expiry_date=None,
        tradingsymbol="NIFTY26APR24650CE",
        instrument_token=123456,
        instrument_id=None,
        qty_lots=1,
        qty_units=50,
    )
    market_data = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "quote_age_sec": 0.5,
    }

    event = orch._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])
    assert "unresolved_contract" not in list(event.get("veto_reasons") or [])


def test_build_decision_event_skips_unresolved_for_synthetic_placeholder():
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 100000.0,
        "daily_pnl": 0.0,
        "daily_pnl_pct": 0.0,
        "open_risk": 0.0,
        "open_risk_pct": 0.0,
    }
    orch.loss_streak = {}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
    orch._open_risk = lambda: 0.0

    trade = SimpleNamespace(
        trade_id="PRE_BUILDER_GATE-NIFTY-123",
        symbol="NIFTY",
        instrument="OPT",
        instrument_type="OPT",
        strategy_family="synthetic_advisory",
        candidate_origin="pre_builder_gate",
        right="CE",
    )
    market_data = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "quote_age_sec": 1.0,
    }

    event = orch._build_decision_event(trade, market_data, gatekeeper_allowed=False, veto_reasons=["no_signal"])
    reasons = list(event.get("veto_reasons") or [])
    assert "unresolved_contract" not in reasons
    assert "no_signal" in reasons


def test_regime_unstable_block_after_prefers_live_override(monkeypatch):
    orch = Orchestrator.__new__(Orchestrator)
    monkeypatch.setattr(cfg, "REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 1, raising=False)
    monkeypatch.setattr(cfg, "LIVE_REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 2, raising=False)
    monkeypatch.setattr(cfg, "PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 3, raising=False)

    out = orch._regime_unstable_block_after(
        {"symbol": "NIFTY", "market_context": {"execution_mode": "LIVE", "market_open": True}}
    )
    assert out == 2
