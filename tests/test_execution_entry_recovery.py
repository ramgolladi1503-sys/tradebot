import json
import time

from config import config as cfg
from core import review_queue


def _make_trade(**overrides):
    base = {
        "trade_id": "T-EXEC-RECOVER",
        "symbol": "SENSEX",
        "instrument": "OPT",
        "expiry_date": "2026-03-05",
        "expiry": "2026-03-05",
        "strike": 81700,
        "option_type": "PE",
        "side": "BUY",
        "entry": 149.0,
        "entry_price": 149.0,
        "stop_loss": 120.0,
        "target": 210.0,
        "strategy": "CORE",
        "timestamp": "2026-02-26T10:00:00",
        "permission": "QUEUE_ONLY",
        "permission_reason": "medium_global_conf",
        "readiness": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "execution_status": "queue_only",
    }
    base.update(overrides)
    return base


def test_candidate_with_entry_and_ltp_recovers_execution_entry(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_ENTRY_TRACE_ENABLE", True, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.35,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.35,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            instrument_token=99130,
            tradingsymbol="SENSEX26MAR82300PE",
            instrument_id="SENSEX26MAR82300PE",
            option_ltp_source="tick_store",
            quote_source="tick_store",
            quote_age_sec=0.5,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["execution_entry"] == 150.0
    assert rows[0]["execution_entry_status"] == "executable"
    assert rows[0]["execution_allowed"] is False
    assert rows[0]["tradable"] is True


def test_emitted_suggestion_preserves_recovered_execution_entry(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.35,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.35,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-EXEC-EMIT",
            instrument_token=99131,
            tradingsymbol="SENSEX26MAR82300PE",
            instrument_id="SENSEX26MAR82300PE",
            option_ltp_source="tick_store",
            quote_source="tick_store",
            quote_age_sec=0.5,
        )
    )

    payload = json.loads(suggestions_path.read_text().strip())
    assert payload["execution_entry"] == 150.0
    assert payload["execution_entry_status"] == "executable"
    assert payload["execution_allowed"] is False
    assert payload["tradable"] is True


def test_advisory_only_with_display_entry_preserves_execution_entry():
    out = review_queue._refresh_opportunity_survival_state(
        {
            "trade_id": "T-EXEC-ADVISORY",
            "symbol": "NIFTY",
            "permission": "ADVISORY_ONLY",
            "final_action": "ADVISORY_ONLY",
            "readiness": "ADVISORY_ONLY",
            "execution_status": "advisory_only",
            "entry": 101.5,
            "display_entry": 101.5,
            "entry_status": "displayable",
            "display_entry_status": "displayable",
            "current_ltp": 102.0,
            "option_ltp_source": "tick_store",
            "quote_source": "tick_store",
            "tradable": True,
            "execution_allowed": False,
            "execution_entry": None,
            "execution_entry_status": "missing",
        }
    )

    assert out["execution_entry"] == 102.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_allowed"] is False
    assert out["tradable"] is True
    assert out["execution_status"] == "advisory_only"


def test_block_row_does_not_fake_execution_allowed():
    out = review_queue._refresh_opportunity_survival_state(
        {
            "trade_id": "T-EXEC-BLOCK",
            "symbol": "NIFTY",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "readiness": "BLOCKED",
            "execution_status": "blocked",
            "entry": 101.5,
            "display_entry": 101.5,
            "entry_status": "displayable",
            "display_entry_status": "displayable",
            "current_ltp": 102.0,
            "option_ltp_source": "tick_store",
            "quote_source": "tick_store",
            "execution_entry": None,
            "execution_entry_status": "missing",
        }
    )

    assert out["execution_allowed"] is False
    assert out["tradable"] is False
    assert out["permission"] == "BLOCK"
    assert out["final_action"] == "BLOCK"


def test_no_price_sources_keeps_execution_entry_missing():
    out = review_queue._refresh_opportunity_survival_state(
        {
            "trade_id": "T-EXEC-MISSING",
            "symbol": "NIFTY",
            "permission": "ADVISORY_ONLY",
            "final_action": "ADVISORY_ONLY",
            "readiness": "ADVISORY_ONLY",
            "execution_status": "advisory_only",
            "entry": None,
            "display_entry": None,
            "current_ltp": None,
            "option_ltp_source": "tick_store",
            "quote_source": "tick_store",
            "execution_entry": None,
            "execution_entry_status": "missing",
        }
    )

    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "missing"


def test_recover_missing_execution_entry_uses_final_stage_prices():
    out, lifecycle = review_queue._recover_missing_execution_entry(
        {
            "trade_id": "T-EXEC-FALLBACK",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_token": 99140,
            "tradingsymbol": "NIFTY26MAR24600PE",
            "instrument_id": "NIFTY26MAR24600PE",
            "expiry_date": "2026-03-26",
            "expiry": "2026-03-26",
            "strike": 24600,
            "option_type": "PE",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "current_ltp": None,
            "expected_entry": 112.0,
            "signal_price": 113.0,
            "entry_price": 114.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "hard_blockers": ["MISSING_ENTRY"],
            "blockers": ["MISSING_ENTRY", "spread_pct"],
        },
        {},
    )

    assert out["execution_entry"] == 112.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_entry_source"] == "recovered_fallback"
    assert out["display_entry"] == 112.0
    assert out["display_entry_source"] == "recovered_fallback"
    assert out["entry"] == 112.0
    assert out["entry_status"] == "displayable"
    assert out["entry_recovered"] is True
    assert out["entry_recovered_from"] == "expected_entry"
    assert out["tradable"] is True
    assert out["execution_allowed"] is False
    assert "MISSING_ENTRY" not in list(out.get("hard_blockers") or [])
    assert "MISSING_ENTRY" not in list(out.get("blockers") or [])
    assert "spread_pct" in list(out.get("blockers") or [])
    assert lifecycle["execution_entry"] == 112.0


def test_recover_missing_execution_entry_skips_guarded_rows():
    offhours, _ = review_queue._recover_missing_execution_entry(
        {
            "trade_id": "T-EXEC-OFFHOURS",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "permission": "ADVISORY_ONLY",
            "final_action": "ADVISORY_ONLY",
            "readiness": "ADVISORY_ONLY",
            "execution_status": "advisory_only",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "suggested_entry": 111.5,
            "quote_source": "synthetic_offhours",
            "option_ltp_source": "synthetic_offhours",
            "quote_validation_status": "OFFHOURS_SYNTHETIC",
        },
        {},
    )
    blocked, _ = review_queue._recover_missing_execution_entry(
        {
            "trade_id": "T-EXEC-UNRESOLVED",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "readiness": "BLOCKED",
            "execution_status": "blocked",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "expected_entry": 112.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "unresolved_contract": True,
        },
        {},
    )
    no_live_feed, _ = review_queue._recover_missing_execution_entry(
        {
            "trade_id": "T-EXEC-NO-LIVE-FEED",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "readiness": "BLOCKED",
            "execution_status": "blocked",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "suggested_entry": 111.5,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "NO_LIVE_OPTION_FEED",
        },
        {},
    )

    assert offhours["execution_entry"] is None
    assert offhours.get("entry_recovered") in (None, False)
    assert blocked["execution_entry"] is None
    assert blocked.get("entry_recovered") in (None, False)
    assert no_live_feed["execution_entry"] is None
    assert no_live_feed.get("entry_recovered") in (None, False)


def test_last_chance_execution_entry_recovery_restores_missing_queue_row():
    out = review_queue._last_chance_execution_entry_recovery(
        {
            "trade_id": "T-EXEC-LAST-CHANCE",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_token": 99141,
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "current_ltp": None,
            "suggested_entry": 119.5,
            "expected_entry": 120.0,
            "signal_price": 121.0,
            "entry_price": 122.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "hard_blockers": ["MISSING_ENTRY"],
            "blockers": ["MISSING_ENTRY", "spread_pct"],
        }
    )

    assert out["execution_entry"] == 120.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_entry_source"] == "recovered_fallback"
    assert out["display_entry"] == 120.0
    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["entry_recovered"] is True
    assert out["entry_recovered_from"] == "expected_entry"
    assert "MISSING_ENTRY" not in list(out.get("hard_blockers") or [])
    assert "MISSING_ENTRY" not in list(out.get("blockers") or [])
    assert "spread_pct" in list(out.get("blockers") or [])


def test_last_chance_execution_entry_recovery_ignores_entry_status_when_price_exists():
    out = review_queue._last_chance_execution_entry_recovery(
        {
            "trade_id": "T-EXEC-LAST-CHANCE-STATUS",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_token": 99142,
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": 118.5,
            "display_entry_status": "displayable",
            "entry": 118.5,
            "entry_status": "displayable",
            "current_ltp": None,
            "expected_entry": 120.0,
            "entry_price": 121.0,
            "signal_price": 122.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "hard_blockers": ["MISSING_ENTRY"],
            "blockers": ["MISSING_ENTRY", "spread_pct"],
        }
    )

    assert out["execution_entry"] == 118.5
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_entry_source"] == "recovered_fallback"
    assert out["entry_status"] == "displayable"
    assert out["entry_recovered"] is True
    assert out["entry_recovered_from"] == "display_entry"
    assert out["tradable"] is True


def test_last_chance_execution_entry_recovery_does_not_depend_on_permission_state():
    out = review_queue._last_chance_execution_entry_recovery(
        {
            "trade_id": "T-EXEC-LAST-CHANCE-BLOCK",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_token": 99143,
            "permission": "BLOCK",
            "final_action": "BLOCK",
            "readiness": "BLOCKED",
            "execution_status": "blocked",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "expected_entry": 120.0,
            "entry_price": 121.0,
            "current_ltp": 122.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "hard_blockers": ["MISSING_ENTRY"],
            "blockers": ["MISSING_ENTRY"],
        }
    )

    assert out["execution_entry"] == 120.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["entry_recovered"] is True
    assert out["entry_recovered_from"] == "expected_entry"
    assert out["entry"] is None
    assert out["entry_status"] == "missing"


def test_enforce_executable_entry_invariant_keeps_recovered_execution_entry():
    out = review_queue._enforce_executable_entry_invariant(
        {
            "trade_id": "T-EXEC-INVARIANT-RECOVERED",
            "symbol": "NIFTY",
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "status": "READY",
            "execution_status": "executable",
            "entry_recovered": True,
            "execution_entry": 120.0,
            "execution_entry_status": "missing",
            "execution_entry_source": "none",
            "display_entry": 120.0,
            "display_entry_status": "displayable",
            "entry": 120.0,
            "entry_status": "displayable",
        }
    )

    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_status"] != "executable"
    assert out.get("hard_blockers") in (None, [])


def test_enforce_executable_entry_invariant_marks_derived_recovery_for_lifecycle():
    out = review_queue._enforce_executable_entry_invariant(
        {
            "trade_id": "T-EXEC-DERIVE-RECOVERED",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "display_entry": 150.0,
            "display_entry_status": "displayable",
            "entry": None,
            "entry_status": "missing",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "current_ltp": 150.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "hard_blockers": [],
            "blockers": [],
        }
    )

    assert out["execution_entry"] == 150.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["entry_recovered"] is True
    assert out["entry_recovered_from"] == "derive_execution_entry_recovery"


def test_enforce_executable_entry_invariant_does_not_backfill_entry_for_recovered_row():
    recovered = review_queue._last_chance_execution_entry_recovery(
        {
            "trade_id": "T-EXEC-DERIVE-NO-ENTRY-BACKFILL",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "instrument_token": 99144,
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "display_entry": None,
            "display_entry_status": "missing",
            "entry": None,
            "entry_status": "missing",
            "execution_entry": None,
            "execution_entry_status": "missing",
            "current_ltp": 150.0,
            "quote_source": "tick_store",
            "option_ltp_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "hard_blockers": [],
            "blockers": [],
        }
    )
    out = review_queue._enforce_executable_entry_invariant(recovered)

    assert out["execution_entry"] == 150.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["display_entry"] == 150.0
    assert out["display_entry_status"] == "displayable"
    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["entry_recovered"] is True


def test_refresh_opportunity_survival_state_preserves_recovered_last_execution_entry():
    out = review_queue._refresh_opportunity_survival_state(
        {
            "trade_id": "T-EXEC-RECOVERY-PRESERVED",
            "symbol": "NIFTY",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "entry_recovered": True,
            "execution_entry": 120.0,
            "execution_entry_status": "executable",
            "execution_entry_source": "last",
            "display_entry": 120.0,
            "display_entry_status": "displayable",
            "entry": 120.0,
            "entry_status": "displayable",
            "blockers": ["spread_pct"],
            "hard_blockers": [],
        }
    )

    assert out["execution_entry"] == 120.0
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_entry_source"] == "last"
    assert out["execution_status"] == "queue_only"
    assert out["tradable"] is True
    assert out["execution_allowed"] is False
