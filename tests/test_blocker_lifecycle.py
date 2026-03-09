from __future__ import annotations

from datetime import datetime

import core.readiness_gate as readiness_gate
from core.blocker_lifecycle import (
    build_contract_owner_key,
    evaluate_advisory_contract_blockers,
    evaluate_feed_symbol_blockers,
    get_blocker_registry,
    reset_blocker_registries,
    top_active_code,
)
from core.readiness_state import ReadinessState


def setup_function():
    reset_blocker_registries()


def _active_codes(records) -> list[str]:
    return [str(record.code) for record in list(records or [])]


def test_no_live_option_feed_clears_on_recovery():
    registry = get_blocker_registry("feed_test")

    first = evaluate_feed_symbol_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        ws_connected=False,
        expected_option_count=2,
        subscribed_option_count=0,
        latest_option_tick_ts=None,
        latest_option_tick_age_sec=None,
        feed_freshness_sec=8.0,
        min_required_count=1,
    )
    assert "NO_LIVE_OPTION_FEED" in _active_codes(first)

    recovered = evaluate_feed_symbol_blockers(
        registry,
        now_ts=105.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=2,
        subscribed_option_count=2,
        latest_option_tick_ts=104.0,
        latest_option_tick_age_sec=1.0,
        feed_freshness_sec=8.0,
        min_required_count=1,
    )
    assert "NO_LIVE_OPTION_FEED" not in _active_codes(recovered)
    assert top_active_code(recovered) is None


def test_stale_option_ltp_clears_when_quote_freshens():
    registry = get_blocker_registry("advisory_test")

    stale = evaluate_advisory_contract_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=101.0,
        reference_price=101.0,
        quote_age_sec=12.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "STALE_OPTION_LTP" in _active_codes(stale)

    fresh = evaluate_advisory_contract_blockers(
        registry,
        now_ts=102.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=101.0,
        reference_price=101.0,
        quote_age_sec=2.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "STALE_OPTION_LTP" not in _active_codes(fresh)


def test_price_mismatch_clears_when_prices_reconcile():
    registry = get_blocker_registry("advisory_test")

    mismatch = evaluate_advisory_contract_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=118.0,
        reference_price=100.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "PRICE_MISMATCH" in _active_codes(mismatch)

    reconciled = evaluate_advisory_contract_blockers(
        registry,
        now_ts=101.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=101.0,
        reference_price=100.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "PRICE_MISMATCH" not in _active_codes(reconciled)


def test_no_token_clears_after_resolution_success():
    registry = get_blocker_registry("advisory_test")

    missing = evaluate_advisory_contract_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=None,
        live_price=None,
        reference_price=100.0,
        quote_age_sec=None,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "NO_TOKEN" in _active_codes(missing)

    resolved = evaluate_advisory_contract_blockers(
        registry,
        now_ts=101.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=100.0,
        reference_price=100.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "NO_TOKEN" not in _active_codes(resolved)


def test_old_blocker_does_not_survive_contract_change():
    registry = get_blocker_registry("advisory_test")

    contract_a = evaluate_advisory_contract_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=None,
        live_price=None,
        reference_price=100.0,
        quote_age_sec=None,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "NO_TOKEN" in _active_codes(contract_a)

    registry.prune_invalid_owners(
        now_ts=101.0,
        scope="advisory_contract",
        valid_owner_keys={
            build_contract_owner_key(
                symbol="NIFTY",
                expiry="2026-03-17",
                strike=23700,
                right="PE",
                generation="gen2",
            )
        },
    )

    contract_b = evaluate_advisory_contract_blockers(
        registry,
        now_ts=101.0,
        symbol="NIFTY",
        expiry="2026-03-17",
        strike=23700,
        right="PE",
        advisory_generation="gen2",
        instrument_token=456,
        live_price=102.0,
        reference_price=102.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert _active_codes(contract_b) == []


def test_blocker_expires_after_ttl():
    registry = get_blocker_registry("feed_test")

    evaluate_feed_symbol_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        ws_connected=False,
        expected_option_count=1,
        subscribed_option_count=0,
        latest_option_tick_ts=None,
        latest_option_tick_age_sec=None,
        feed_freshness_sec=8.0,
        min_required_count=1,
    )
    registry.expire_stale(200.0, scope="feed_symbol")
    assert registry.get_active(scope="feed_symbol", owner_key="feed|NIFTY") == []


def test_readiness_uses_only_active_blockers(monkeypatch):
    monkeypatch.setattr(readiness_gate.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(readiness_gate.risk_halt, "is_halted", lambda: False)
    monkeypatch.setattr(readiness_gate, "verify_audit_chain", lambda: (True, "ok", 0))
    monkeypatch.setattr(readiness_gate, "_check_kite_auth", lambda: (True, "ok", "OK"))
    monkeypatch.setattr(
        readiness_gate,
        "run_preopen_auth_warm_check",
        lambda **_kwargs: {"degrade_to_planning": False, "reason": "ok"},
    )
    monkeypatch.setattr(readiness_gate, "_check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(readiness_gate, "_disk_free_gb", lambda _=".": 10.0)
    monkeypatch.setattr(readiness_gate, "now_ist", lambda: datetime(2026, 2, 10, 10, 0, 0))
    monkeypatch.setattr(readiness_gate, "is_market_open_ist", lambda now=None: True)
    monkeypatch.setattr(
        readiness_gate,
        "_decision_gate_health",
        lambda now_epoch, market_open, execution_mode=None: {
            "ok": True,
            "feed_ok": True,
            "blockers": [],
            "reasons": [],
            "symbols": ["NIFTY"],
            "allowed_symbols": ["NIFTY"],
            "blocked_symbols": [],
            "blockers_by_symbol": {"NIFTY": []},
            "rows": {},
            "ltp_age_sec": 0.5,
            "depth_age_sec": 0.5,
            "latest_explain": [],
        },
    )
    monkeypatch.setattr(
        readiness_gate,
        "get_feed_debug",
        lambda now_epoch=None: {
            "option_active_blockers_by_symbol": {"NIFTY": []},
        },
    )

    result = readiness_gate.run_readiness_state(write_log=False)
    assert result.state == ReadinessState.READY
    assert result.blockers == []
    assert result.checks["feed_health"]["active_blockers"] == []


def test_advisory_generation_change_prunes_old_price_mismatch():
    registry = get_blocker_registry("advisory_test")

    gen1 = evaluate_advisory_contract_blockers(
        registry,
        now_ts=100.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen1",
        instrument_token=123,
        live_price=118.0,
        reference_price=100.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "PRICE_MISMATCH" in _active_codes(gen1)

    registry.prune_invalid_owners(
        now_ts=101.0,
        scope="advisory_contract",
        valid_owner_keys={
            build_contract_owner_key(
                symbol="NIFTY",
                expiry="2026-03-10",
                strike=23600,
                right="CE",
                generation="gen2",
            )
        },
    )

    gen2 = evaluate_advisory_contract_blockers(
        registry,
        now_ts=101.0,
        symbol="NIFTY",
        expiry="2026-03-10",
        strike=23600,
        right="CE",
        advisory_generation="gen2",
        instrument_token=123,
        live_price=101.0,
        reference_price=100.0,
        quote_age_sec=1.0,
        stale_threshold_sec=5.0,
        abs_tol=1.0,
        pct_tol=0.03,
        subscription_failed=False,
    )
    assert "PRICE_MISMATCH" not in _active_codes(gen2)
