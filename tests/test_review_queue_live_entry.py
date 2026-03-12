import json
import time
from pathlib import Path

from config import config as cfg
from core.entry_semantics import build_entry_state
from core import review_queue
from core.blocker_lifecycle import reset_blocker_registries
from core.option_liquidity_cache import clear_option_liquidity_cache, update_option_liquidity_cache


def _make_trade(**overrides):
    base = {
        "trade_id": "T-1",
        "symbol": "SENSEX",
        "instrument": "OPT",
        "expiry_date": "2026-03-05",
        "expiry": "2026-03-05",
        "strike": 81700,
        "option_type": "PE",
        "side": "BUY",
        "entry_price": 150.0,
        "stop_loss": 120.0,
        "target": 210.0,
        "strategy": "CORE",
        "timestamp": "2026-02-26T10:00:00",
    }
    base.update(overrides)
    return base


def _row_by_trade_id(path: Path, trade_id: str) -> dict:
    rows = json.loads(path.read_text())
    for row in rows:
        if str(row.get("trade_id")) == str(trade_id):
            return row
    raise AssertionError(f"trade_id {trade_id} not found in {path}")


def test_trade_blocked_without_option_subscription(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: False)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))

    def _should_not_fetch(*_args, **_kwargs):
        raise AssertionError("REST fallback must not run when strict/live subscription failed")

    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", _should_not_fetch)
    review_queue.add_to_queue(_make_trade())
    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "missing"
    assert rows[0]["quote_validation_status"] in ("NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN")
    assert rows[0]["permission"] == "BLOCK"
    assert rows[0]["final_action"] == "BLOCK"
    assert rows[0]["option_ltp_source"] == "subscription_failed"
    assert rows[0]["hard_blockers"] == ["NO_LIVE_OPTION_FEED"]
    assert rows[0]["soft_penalties"] == []
    assert rows[0]["warnings"] == []
    assert rows[0]["execution_status"] == "blocked"
    assert rows[0]["readiness"] == "BLOCKED"
    status_payload = json.loads((tmp_path / "logs" / "suggestions_status.json").read_text())
    assert status_payload["latest_trade_id"] == "T-1"
    assert status_payload["latest_entry_status"] == "missing"
    assert status_payload["latest_permission"] == "BLOCK"
    assert status_payload["primary_blocker"] == "NO_LIVE_OPTION_FEED"


def test_advisory_entry_keeps_ltp_when_price_mismatch(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))
    trade = _make_trade(
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        entry_price=257.0,
    )
    review_queue.add_to_queue(trade)
    rows = json.loads(qpath.read_text())
    assert rows[0]["entry"] == 565.0
    assert rows[0]["suggested_entry"] == 565.0
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["option_ltp_source"] == "tick_store"
    assert rows[0]["validation_signal_price"] is None
    assert rows[0]["validation_reference_price"] == 257.0
    assert rows[0]["validation_reference_source"] == "entry_price"
    assert rows[0]["pre_validation_entry"] == 257.0
    assert rows[0]["post_validation_entry"] == 565.0


def test_review_queue_preserves_executable_and_display_entry_fields(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "APPROVED_PATH", tmp_path / "approved.json")
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (72.8, time.time()))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)

    lifecycle = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=24600,
        right="PE",
        side="BUY",
        bid=72.2,
        ask=72.8,
        mark=72.5,
        last=72.4,
        quote_age_sec=1.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=True,
        quote_source="tick_store",
    )
    trade = _make_trade(
        trade_id="ADV-EXEC-1",
        instrument_token=77123,
        tradingsymbol="NIFTY26MAR24600PE",
        symbol="NIFTY",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        strike=24600,
        option_type="PE",
        strategy="CORE",
        entry_price=72.8,
        execution_mode="LIVE",
        quote_source="tick_store",
        option_ltp_source="tick_store",
        quote_age_sec=1.0,
        bid=72.2,
        ask=72.8,
        mark_price=72.5,
        current_ltp=72.8,
        **lifecycle,
    )

    with caplog.at_level("DEBUG"):
        review_queue.add_to_queue(trade, extra={"permission": "EXECUTE"})

    payload = json.loads(suggestions_path.read_text().strip())
    assert isinstance(payload["ts_epoch"], float)
    assert payload["execution_entry"] == 72.8
    assert payload["execution_entry_source"] == "ask"
    assert payload["execution_entry_status"] == "executable"
    assert payload["display_entry"] == 72.8
    assert payload["display_entry_source"] == "ask"
    assert payload["display_entry_status"] == "displayable"
    assert payload["entry"] == 72.8
    assert payload["entry_status"] == "displayable"
    assert payload["quote_source"] == "tick_store"
    assert "entry_lifecycle_resolved trade_id=ADV-EXEC-1" in caplog.text
    assert "stage=validate_finalize" in caplog.text
    assert "execution_entry=72.8" in caplog.text
    assert "display_entry=72.8" in caplog.text
    assert "entry_status=displayable" in caplog.text
    assert "entry_clear_reason=None" in caplog.text
    assert "permission=ADVISORY_ONLY" in caplog.text
    assert "readiness=ADVISORY_ONLY" in caplog.text
    assert "advisory_queue_schema_error" not in caplog.text
    assert "advisory_emit_schema_error" not in caplog.text


def test_finalize_entry_lifecycle_uses_display_entry_as_entry():
    entry = {
        "trade_id": "T-LIFECYCLE-DISPLAY",
        "display_entry": 72.8,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "execution_entry": 72.8,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "entry": 70.0,
        "entry_status": "",
    }

    out = review_queue.finalize_entry_lifecycle(entry)

    assert out["entry"] == 72.8
    assert out["entry_source"] == "ask"
    assert out["entry_status"] == "displayable"
    assert out["entry_clear_reason"] is None


def test_finalize_entry_lifecycle_sets_clear_reason_when_display_missing():
    entry = {
        "trade_id": "T-LIFECYCLE-MISSING",
        "display_entry": None,
        "display_entry_status": "",
        "execution_entry": None,
        "execution_entry_status": "",
        "entry": 70.0,
        "entry_status": "PRICE_MISMATCH",
        "entry_clear_reason": None,
    }

    out = review_queue.finalize_entry_lifecycle(entry)

    assert out["display_entry"] is None
    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["entry_clear_reason"] == "price_mismatch"


def test_finalize_entry_lifecycle_restores_snapshot_after_mutation(caplog):
    finalized = review_queue.finalize_entry_lifecycle(
        {
            "trade_id": "T-LIFECYCLE-FROZEN",
            "symbol": "SENSEX",
            "display_entry": 88.5,
            "display_entry_source": "mid",
            "display_entry_status": "displayable",
            "execution_entry": 88.6,
            "execution_entry_source": "ask",
            "execution_entry_status": "executable",
        }
    )
    finalized["entry"] = 10.0
    finalized["display_entry"] = None
    finalized["entry_status"] = "broken"
    finalized["entry_clear_reason"] = "late_mutation"

    with caplog.at_level("WARNING"):
        out = review_queue._enforce_finalized_entry_lifecycle(finalized, stage="unit_test")

    assert out["display_entry"] == 88.5
    assert out["entry"] == 88.5
    assert out["entry_status"] == "displayable"
    assert out["entry_clear_reason"] is None
    assert "entry_lifecycle_mutation_ignored trade_id=T-LIFECYCLE-FROZEN" in caplog.text
    assert "fields=display_entry,entry,entry_status,entry_clear_reason" in caplog.text


def test_finalize_entry_lifecycle_drops_snapshot_before_serialization():
    finalized = review_queue.finalize_entry_lifecycle(
        {
            "trade_id": "T-LIFECYCLE-DROP",
            "display_entry": 51.25,
            "display_entry_source": "last",
            "display_entry_status": "displayable",
        }
    )

    out = review_queue._enforce_finalized_entry_lifecycle(
        finalized,
        stage="unit_test",
        drop_snapshot=True,
    )

    assert "_lifecycle_snapshot" not in out


def test_normalize_canonical_quote_source_maps_component_sources_to_schema_transport():
    executable = review_queue._normalize_canonical_quote_source(
        {
            "quote_source": "last",
            "option_ltp_source": None,
            "execution_entry": 72.8,
            "execution_entry_source": "ask",
            "display_entry": 72.8,
            "display_entry_source": "ask",
        }
    )
    assert executable["quote_source"] == "live"

    fallback = review_queue._normalize_canonical_quote_source(
        {
            "quote_source": "last",
            "display_entry": 72.5,
            "display_entry_source": "mark",
        }
    )
    assert fallback["quote_source"] == "tick_store"

    rest = review_queue._normalize_canonical_quote_source(
        {
            "quote_source": "last",
            "option_ltp_source": "rest_fallback",
            "display_entry": 123.45,
            "display_entry_source": "last",
        }
    )
    assert rest["quote_source"] == "rest_fallback"

    synthetic = review_queue._normalize_canonical_quote_source(
        {
            "quote_source": "last",
            "option_ltp_source": "synthetic_offhours",
            "display_entry": 225.15,
            "display_entry_source": "last",
        }
    )
    assert synthetic["quote_source"] == "synthetic_offhours"


def test_suggestion_emission_schema_failure_records_diagnostic_and_status(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    rejected_path = tmp_path / "rejected_candidates.jsonl"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "rejected_candidates_paths", lambda: [rejected_path])
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (72.8, time.time()))

    real_serialize = review_queue.serialize_advisory_row
    calls = {"count": 0}

    def _fail_emit_only(row, allow_legacy=True):
        calls["count"] += 1
        if calls["count"] == 2:
            raise review_queue.AdvisorySchemaError("forced_emit_failure")
        return real_serialize(row, allow_legacy=allow_legacy)

    monkeypatch.setattr(review_queue, "serialize_advisory_row", _fail_emit_only)

    with caplog.at_level("ERROR"):
        review_queue.add_to_queue(
            _make_trade(
                trade_id="T-EMIT-FAIL-SUGG",
                instrument_token=77123,
                tradingsymbol="NIFTY26MAR24600PE",
                symbol="NIFTY",
                expiry_date="2026-03-26",
                expiry="2026-03-26",
                strike=24600,
                option_type="PE",
                strategy="CORE",
                entry_price=72.8,
                execution_mode="LIVE",
            )
        )

    assert not suggestions_path.exists() or suggestions_path.read_text().strip() == ""
    diagnostic = json.loads((logs_root / "advisory_emit_failures.jsonl").read_text().strip())
    assert diagnostic["trade_id"] == "T-EMIT-FAIL-SUGG"
    assert diagnostic["symbol"] == "NIFTY"
    assert diagnostic["emission_target"] == "suggestions"
    assert diagnostic["failure_reason"] == "forced_emit_failure"
    status = json.loads((logs_root / "suggestions_status.json").read_text())
    assert status["status"] == "error"
    assert status["latest_emit_status"] == "schema_failed"
    assert status["latest_emit_target"] == "suggestions"
    engine = json.loads((logs_root / "engine_cycle_status.json").read_text())
    assert engine["cycle_stage"] == "emit_failed"
    assert engine["latest_emit_status"] == "schema_failed"
    rejected_diagnostic = json.loads(rejected_path.read_text().strip())
    assert rejected_diagnostic["trade_id"] == "T-EMIT-FAIL-SUGG"
    assert rejected_diagnostic["entry_status"] is not None
    assert "blockers" in rejected_diagnostic
    assert rejected_diagnostic["reject_reason"] == "advisory_schema_error"
    assert "advisory_emit_schema_error payload=" in caplog.text


def test_rejected_emission_schema_failure_records_diagnostic_and_status(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    rejected_path = tmp_path / "rejected_candidates.jsonl"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "rejected_candidates_paths", lambda: [rejected_path])
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: False)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no rest fallback")))

    real_serialize = review_queue.serialize_advisory_row
    calls = {"count": 0}

    def _fail_emit_only(row, allow_legacy=True):
        calls["count"] += 1
        if calls["count"] == 2:
            raise review_queue.AdvisorySchemaError("forced_rejected_emit_failure")
        return real_serialize(row, allow_legacy=allow_legacy)

    monkeypatch.setattr(review_queue, "serialize_advisory_row", _fail_emit_only)

    review_queue.add_to_queue(_make_trade(trade_id="T-EMIT-FAIL-REJECT"))

    rejected_diagnostic = json.loads(rejected_path.read_text().strip())
    assert rejected_diagnostic["trade_id"] == "T-EMIT-FAIL-REJECT"
    assert rejected_diagnostic["emission_target"] == "rejected_candidates"
    assert rejected_diagnostic["reject_reason"] == "advisory_schema_error"
    diagnostic = json.loads((logs_root / "advisory_emit_failures.jsonl").read_text().strip())
    assert diagnostic["trade_id"] == "T-EMIT-FAIL-REJECT"
    assert diagnostic["emission_target"] == "rejected_candidates"
    rejected_status = json.loads((logs_root / "rejected_candidates_status.json").read_text())
    assert rejected_status["status"] == "error"
    assert rejected_status["latest_emit_status"] == "schema_failed"
    assert rejected_status["latest_emit_target"] == "rejected_candidates"


def test_validation_schema_failure_skips_queue_write_and_records_rejection(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    rejected_path = tmp_path / "rejected_candidates.jsonl"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "rejected_candidates_paths", lambda: [rejected_path])
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (72.8, time.time()))
    monkeypatch.setattr(
        review_queue,
        "serialize_advisory_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(review_queue.AdvisorySchemaError("forced_validation_failure")),
    )

    with caplog.at_level("WARNING"):
        review_queue.add_to_queue(
            _make_trade(
                trade_id="T-VALIDATE-FAIL",
                instrument_token=77123,
                tradingsymbol="NIFTY26MAR24600PE",
                symbol="NIFTY",
                expiry_date="2026-03-26",
                expiry="2026-03-26",
                strike=24600,
                option_type="PE",
                strategy="CORE",
                entry_price=72.8,
                execution_mode="LIVE",
            )
        )

    assert not qpath.exists()
    assert not suggestions_path.exists() or suggestions_path.read_text().strip() == ""
    rejected_diagnostic = json.loads(rejected_path.read_text().strip())
    assert rejected_diagnostic["trade_id"] == "T-VALIDATE-FAIL"
    assert rejected_diagnostic["reject_reason"] == "advisory_schema_error"
    status = json.loads((logs_root / "suggestions_status.json").read_text())
    assert status["status"] == "error"
    assert status["latest_emit_status"] == "schema_failed"
    assert "advisory_queue_schema_error trade_id=T-VALIDATE-FAIL" in caplog.text


def test_review_queue_persists_freshness_evidence_from_validation(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    trade = _make_trade(
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        entry_price=565.0,
        execution_mode="LIVE",
    )

    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["freshness_reason"] == "quote_within_threshold"
    assert rows[0]["freshness_selected_source"] == "quote"
    assert abs(float(rows[0]["freshness_selected_age_sec"]) - 2.1) < 1e-6
    assert abs(float(rows[0]["price_age_sec"]) - 2.1) < 1e-6


def test_option_stale_blocker_clears_when_quote_becomes_fresh(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    now = {"ts": 112.0, "ltp_ts": 100.0}
    monkeypatch.setattr(review_queue.time, "time", lambda: now["ts"])
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, now["ltp_ts"]))
    trade = _make_trade(
        trade_id="T-STALE-RECOVER",
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        entry_price=565.0,
        execution_mode="LIVE",
    )

    review_queue.add_to_queue(trade)
    stale_row = _row_by_trade_id(qpath, "T-STALE-RECOVER")
    assert stale_row["soft_penalties"] == ["NO_LIVE_OPTION_FEED", "STALE_OPTION_LTP"]
    assert stale_row["readiness"] == "ADVISORY_ONLY"
    assert stale_row["execution_status"] == "advisory_only"
    assert stale_row["entry"] is None
    assert stale_row["entry_status"] == "missing"
    assert stale_row["quote_validation_status"] == "STALE_OPTION_LTP"
    assert stale_row["freshness_reason"] == "quote_exceeds_threshold"
    assert float(stale_row["price_age_sec"]) > float(stale_row["freshness_threshold_sec"])

    now["ts"] = 102.1
    now["ltp_ts"] = 100.0
    review_queue.add_to_queue(trade)
    fresh_row = _row_by_trade_id(qpath, "T-STALE-RECOVER")
    assert "STALE_OPTION_LTP" not in list(fresh_row.get("blockers") or [])
    assert fresh_row["readiness"] == "ADVISORY_ONLY"
    assert fresh_row["execution_status"] == "advisory_only"
    assert fresh_row["entry"] == 565.0
    assert fresh_row["entry_status"] == "displayable"
    assert fresh_row["quote_validation_status"] == "OK"
    assert fresh_row["freshness_reason"] == "quote_within_threshold"
    assert float(fresh_row["price_age_sec"]) <= float(fresh_row["freshness_threshold_sec"])


def test_freshness_reason_updates_after_recovery(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    now = {"ts": 120.0, "ltp_ts": 100.0}
    monkeypatch.setattr(review_queue.time, "time", lambda: now["ts"])
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (230.15, now["ltp_ts"]))
    trade = _make_trade(
        trade_id="T-FRESHNESS-RECOVER",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        entry_price=230.15,
        execution_mode="LIVE",
    )

    review_queue.add_to_queue(trade)
    assert _row_by_trade_id(qpath, "T-FRESHNESS-RECOVER")["freshness_reason"] == "quote_exceeds_threshold"

    now["ts"] = 102.0
    review_queue.add_to_queue(trade)
    recovered = _row_by_trade_id(qpath, "T-FRESHNESS-RECOVER")
    assert recovered["freshness_reason"] == "quote_within_threshold"
    assert recovered["freshness_market_open"] is True


def test_explicit_market_open_on_entry_survives_into_validation_freshness_fields(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    trade = _make_trade(
        trade_id="T-MARKET-OPEN-SOURCE",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        instrument_id="NIFTY26MAR23000PE",
        execution_mode="SIM",
        market_open=True,
        market_context={"market_open": True, "execution_mode": "SIM"},
        entry_price=565.0,
    )

    review_queue.add_to_queue(trade)
    row = _row_by_trade_id(qpath, "T-MARKET-OPEN-SOURCE")
    assert row["market_open"] is True
    assert row["market_open_source"] == "entry.market_open"
    assert row["freshness_market_open"] is True
    assert row["freshness_reason"] == "quote_within_threshold"


def test_sim_mode_uses_exchange_clock_when_market_open_and_no_explicit_market_open(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    trade = _make_trade(
        trade_id="T-SIM-EXCHANGE-CLOCK",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        instrument_id="NIFTY26MAR23000PE",
        execution_mode="SIM",
        market_open=None,
        market_context={"execution_mode": "SIM"},
        entry_price=565.0,
    )

    review_queue.add_to_queue(trade)
    row = _row_by_trade_id(qpath, "T-SIM-EXCHANGE-CLOCK")
    assert row["market_open"] is True
    assert row["market_open_source"] == "exchange_clock"
    assert row["freshness_market_open"] is True
    assert row["freshness_reason"] == "quote_within_threshold"


def test_planning_mode_uses_exchange_clock_when_market_open_and_no_explicit_market_open(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    trade = _make_trade(
        trade_id="T-PLANNING-EXCHANGE-CLOCK",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        instrument_id="NIFTY26MAR23000PE",
        execution_mode="PLANNING",
        market_open=None,
        market_context={"execution_mode": "PLANNING"},
        entry_price=565.0,
    )

    review_queue.add_to_queue(trade)
    row = _row_by_trade_id(qpath, "T-PLANNING-EXCHANGE-CLOCK")
    assert row["market_open"] is True
    assert row["market_open_source"] == "exchange_clock"
    assert row["freshness_market_open"] is True
    assert row["freshness_reason"] == "quote_within_threshold"


def test_live_tick_store_advisory_row_during_market_hours_does_not_use_market_closed_skip_strict_stale(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    trade = _make_trade(
        trade_id="T-LIVE-TICK-OPEN",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        instrument_id="NIFTY26MAR23000PE",
        execution_mode="SIM",
        market_open=None,
        market_context={"execution_mode": "SIM"},
        entry_price=565.0,
        option_ltp_source="tick_store",
        quote_source="tick_store",
    )

    review_queue.add_to_queue(trade)
    row = _row_by_trade_id(qpath, "T-LIVE-TICK-OPEN")
    assert row["market_open"] is True
    assert row["market_open_source"] == "exchange_clock"
    assert row["freshness_reason"] != "market_closed_skip_strict_stale"


def test_sim_mode_preserves_explicit_false_market_open(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 102.1)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    trade = _make_trade(
        trade_id="T-SIM-EXPLICIT-FALSE",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000PE",
        instrument_id="NIFTY26MAR23000PE",
        execution_mode="SIM",
        market_open=False,
        market_context={"execution_mode": "SIM"},
        entry_price=565.0,
    )

    review_queue.add_to_queue(trade)
    row = _row_by_trade_id(qpath, "T-SIM-EXPLICIT-FALSE")
    assert row["market_open"] is False
    assert row["market_open_source"] == "entry.market_open"
    assert row["freshness_market_open"] is False


def test_no_token_blocker_clears_after_token_resolution(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (155.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 101.0)

    missing_trade = _make_trade(
        trade_id="T-TOKEN-RECOVER",
        symbol="NIFTY",
        instrument_token=None,
        tradingsymbol="NIFTY26MAR24600PE",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        instrument_id="NIFTY26MAR24600PE",
    )
    review_queue.add_to_queue(missing_trade)
    missing_row = _row_by_trade_id(qpath, "T-TOKEN-RECOVER")
    assert "NO_TOKEN" not in list(missing_row.get("blockers") or [])
    assert missing_row["readiness"] == "ADVISORY_ONLY"
    assert missing_row["entry"] == 150.0
    assert missing_row["entry_status"] == "displayable"

    resolved_trade = _make_trade(
        trade_id="T-TOKEN-RECOVER",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR24600PE",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        instrument_id="NIFTY26MAR24600PE",
        execution_mode="LIVE",
        entry_price=155.0,
    )
    review_queue.add_to_queue(resolved_trade)
    resolved_row = _row_by_trade_id(qpath, "T-TOKEN-RECOVER")
    assert "NO_TOKEN" not in list(resolved_row.get("blockers") or [])
    assert resolved_row["entry"] == 155.0
    assert resolved_row["entry_status"] == "displayable"
    assert resolved_row["quote_validation_status"] == "OK"


def test_missing_token_advisory_emits_without_schema_warning(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (155.0, 100.0))
    monkeypatch.setattr(review_queue.time, "time", lambda: 101.0)

    trade = _make_trade(
        trade_id="T-MISSING-TOKEN-SCHEMA",
        symbol="NIFTY",
        instrument_token=None,
        tradingsymbol="NIFTY26MAR24600PE",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        instrument_id="NIFTY26MAR24600PE",
    )

    with caplog.at_level("WARNING"):
        review_queue.add_to_queue(trade)

    payload = json.loads(suggestions_path.read_text().strip())
    assert payload["display_entry"] == 150.0
    assert payload["display_entry_status"] == "displayable"
    assert payload["execution_entry"] is None
    assert "advisory_queue_schema_error" not in caplog.text
    assert "advisory_emit_schema_error" not in caplog.text


def test_entry_populates_after_token_and_quote_recovery(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    now = {"ts": 101.0}
    monkeypatch.setattr(review_queue.time, "time", lambda: now["ts"])
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (180.0, 100.0))

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-ENTRY-RECOVER",
            symbol="NIFTY",
            instrument_token=None,
            tradingsymbol="NIFTY26MAR24600PE",
            expiry_date="2026-03-26",
            expiry="2026-03-26",
            instrument_id="NIFTY26MAR24600PE",
        )
    )
    initial_row = _row_by_trade_id(qpath, "T-ENTRY-RECOVER")
    assert initial_row["entry"] == 150.0
    assert initial_row["entry_status"] == "displayable"

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-ENTRY-RECOVER",
            symbol="NIFTY",
            instrument_token=12345,
            tradingsymbol="NIFTY26MAR24600PE",
            expiry_date="2026-03-26",
            expiry="2026-03-26",
            instrument_id="NIFTY26MAR24600PE",
            execution_mode="LIVE",
            entry_price=180.0,
        )
    )
    recovered = _row_by_trade_id(qpath, "T-ENTRY-RECOVER")
    assert recovered["entry"] == 180.0
    assert recovered["expected_entry"] == 180.0
    assert recovered["entry_status"] == "displayable"
    assert recovered["quote_validation_status"] == "OK"
    assert "NO_TOKEN" not in list(recovered.get("blockers") or [])


def test_status_files_reflect_nonzero_suggestion_count_after_row_write(tmp_path, monkeypatch):
    reset_blocker_registries()
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    qpath = tmp_path / "review_queue.json"
    suggestions_path = logs_root / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))

    (logs_root / "suggestions_status.json").write_text(
        json.dumps({"status": "no_candidates", "suggestion_count": 0}),
        encoding="utf-8",
    )
    (logs_root / "engine_cycle_status.json").write_text(
        json.dumps({"cycle_stage": "no_candidates", "candidates_seen": 0, "candidates_enqueued": 0}),
        encoding="utf-8",
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-STATUS-COUNT",
            instrument_token=99123,
            tradingsymbol="SENSEX26MAR81700PE",
            instrument_id="SENSEX26MAR81700PE",
            entry_price=257.0,
        )
    )

    suggestions_status = json.loads((logs_root / "suggestions_status.json").read_text(encoding="utf-8"))
    engine_status = json.loads((logs_root / "engine_cycle_status.json").read_text(encoding="utf-8"))
    assert suggestions_status["suggestion_count"] > 0
    assert suggestions_status["latest_trade_id"] == "T-STATUS-COUNT"
    assert suggestions_status["status"] in {"ok", "blocked"}
    assert engine_status["candidates_seen"] > 0
    assert engine_status["candidates_enqueued"] > 0
    assert engine_status["cycle_stage"] in {"ok", "blocked"}


def test_market_open_transition_recomputes_readiness(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    now = {"ts": 120.0, "ltp_ts": 100.0}
    monkeypatch.setattr(review_queue.time, "time", lambda: now["ts"])
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (210.0, now["ltp_ts"]))
    trade = _make_trade(
        trade_id="T-MODE-RECOVER",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR24600PE",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        instrument_id="NIFTY26MAR24600PE",
        entry_price=210.0,
        execution_mode="LIVE",
    )
    review_queue.add_to_queue(trade)
    live_row = _row_by_trade_id(qpath, "T-MODE-RECOVER")
    assert live_row["readiness"] == "ADVISORY_ONLY"
    assert "STALE_OPTION_LTP" in list(live_row["soft_penalties"])
    assert live_row["freshness_market_open"] is True

    trade["execution_mode"] = "PAPER"
    trade["market_open"] = False
    trade["market_context"] = {"market_open": False, "execution_mode": "PAPER"}
    review_queue.add_to_queue(trade)
    offhours_row = _row_by_trade_id(qpath, "T-MODE-RECOVER")
    assert offhours_row["readiness"] == "ADVISORY_ONLY"
    assert "STALE_OPTION_LTP" not in list(offhours_row.get("soft_penalties") or [])
    assert offhours_row["soft_penalties"] == []
    assert offhours_row["freshness_reason"] == "market_closed_skip_strict_stale"
    assert offhours_row["freshness_market_open"] is False


def test_offhours_transition_does_not_retain_live_execution_blockers(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue.time, "time", lambda: 120.0)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (500.0, 100.0))
    trade = _make_trade(
        trade_id="T-OFFHOURS-CLEAR",
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        entry_price=500.0,
        execution_mode="LIVE",
    )
    review_queue.add_to_queue(trade)
    assert "STALE_OPTION_LTP" in list(_row_by_trade_id(qpath, "T-OFFHOURS-CLEAR")["blockers"])

    trade["execution_mode"] = "OFFHOURS"
    review_queue.add_to_queue(trade)
    recovered = _row_by_trade_id(qpath, "T-OFFHOURS-CLEAR")
    assert "STALE_OPTION_LTP" not in list(recovered.get("blockers") or [])
    assert "NO_LIVE_OPTION_FEED" not in list(recovered.get("hard_blockers") or [])
    assert recovered["execution_status"] == "advisory_only"
    assert recovered["entry"] == 500.0


def test_advisory_row_replaces_old_blockers_after_recovery(tmp_path, monkeypatch):
    reset_blocker_registries()
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    now = {"ts": 120.0, "ltp_ts": 100.0}
    monkeypatch.setattr(review_queue.time, "time", lambda: now["ts"])
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (230.15, now["ltp_ts"]))
    trade = _make_trade(
        trade_id="T-BLOCKER-REPLACE",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol="NIFTY26MAR23000CE",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        instrument_id="NIFTY26MAR23000CE",
        entry_price=230.15,
        execution_mode="LIVE",
    )
    review_queue.add_to_queue(trade)
    first = _row_by_trade_id(qpath, "T-BLOCKER-REPLACE")
    assert first["soft_penalties"] == ["NO_LIVE_OPTION_FEED", "STALE_OPTION_LTP"]
    assert first["hard_blockers"] == []

    now["ts"] = 102.0
    review_queue.add_to_queue(trade)
    second = _row_by_trade_id(qpath, "T-BLOCKER-REPLACE")
    assert "STALE_OPTION_LTP" not in list(second.get("blockers") or [])
    assert "NO_LIVE_OPTION_FEED" not in list(second.get("blockers") or [])
    assert second["soft_penalties"] == []
    assert second["warnings"] == []


def test_relaxed_price_mismatch_becomes_soft_penalty_not_hard_blocker(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))
    trade = _make_trade(
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        execution_mode="PAPER",
        market_open=False,
        market_context={"market_open": False, "execution_mode": "PAPER"},
        entry_price=257.0,
        confidence=0.6,
    )

    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["hard_blockers"] == []
    assert rows[0]["soft_penalties"] == []
    assert rows[0]["warnings"] == ["PRICE_MISMATCH"]
    assert rows[0]["readiness"] != "BLOCKED"
    assert rows[0]["execution_status"] != "blocked"
    assert float(rows[0]["confidence_penalty"]) == 0.0
    assert float(rows[0]["confidence_final"]) == float(rows[0]["gating_final_confidence"])
    assert float(rows[0]["confidence"]) == float(rows[0]["confidence_final"])


def test_advisory_rest_fallback_is_rate_limited(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_CACHE", {})
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_LAST_ATTEMPT", {})

    calls = {"count": 0}

    def _fake_fetch(_tradingsymbol):
        calls["count"] += 1
        return 123.45, time.time()

    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", _fake_fetch)
    trade = _make_trade(instrument_token=77123, tradingsymbol="NIFTY26MAR24600PE")

    review_queue.add_to_queue(trade, extra={"entry": 100.95})
    review_queue.add_to_queue(dict(trade, timestamp="2026-02-26T10:00:30"))

    rows = json.loads(qpath.read_text())
    assert calls["count"] == 1
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["entry"] == 123.45
    assert rows[0]["option_ltp_source"] == "rest_fallback"


def test_rest_fallback_emits_without_schema_warning(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_CACHE", {})
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_LAST_ATTEMPT", {})
    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", lambda _tradingsymbol: (123.45, time.time()))

    with caplog.at_level("WARNING"):
        review_queue.add_to_queue(
            _make_trade(instrument_token=77123, tradingsymbol="NIFTY26MAR24600PE"),
            extra={"entry": 100.95},
        )

    rows = json.loads(qpath.read_text())
    payload = json.loads(suggestions_path.read_text().strip())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["option_ltp_source"] == "rest_fallback"
    assert payload["display_entry"] == 123.45
    assert payload["display_entry_status"] == "displayable"
    assert payload["quote_source"] == "rest_fallback"
    assert "advisory_queue_schema_error" not in caplog.text
    assert "advisory_emit_schema_error" not in caplog.text


def test_relaxed_mode_allows_rest_fallback_when_subscription_fails(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: False)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_CACHE", {})
    monkeypatch.setattr(review_queue, "_ADVISORY_REST_LTP_LAST_ATTEMPT", {})
    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", lambda _tradingsymbol: (123.45, time.time()))

    trade = _make_trade(
        instrument_token=77123,
        tradingsymbol="NIFTY26MAR24600PE",
        execution_mode="PAPER",
        market_open=False,
        market_context={"market_open": False, "execution_mode": "PAPER"},
    )
    review_queue.add_to_queue(trade, extra={"entry": 100.95})

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["entry"] == 123.45
    assert rows[0]["option_ltp_source"] == "rest_fallback"


def test_review_queue_emits_canonical_advisory_row_to_suggestions_log(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "SUGGESTIONS_LOG_PATH", str(suggestions_path), raising=False)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (72.5, time.time()))

    trade = _make_trade(
        trade_id="ADV-72",
        instrument_token=77123,
        tradingsymbol="NIFTY26MAR24600PE",
        symbol="NIFTY",
        strike=24600,
        option_type="PE",
        strategy="CORE",
        entry_price=72.5,
    )
    review_queue.add_to_queue(trade, extra={"blockers": ["STALE_OPTION_LTP"], "permission": "ADVISORY_ONLY"})

    payload = json.loads(suggestions_path.read_text().strip())
    assert payload["advisory_id"] == "ADV-72"
    assert payload["strategy_name"] == "CORE"
    assert payload["entry"] == 72.5
    assert payload["display_entry"] == 72.5
    assert payload["display_entry_source"] == "last"
    assert payload["display_entry_status"] == "displayable"
    assert payload["execution_entry"] is None
    assert payload["execution_entry_status"] == "non_executable"
    assert "HARD_MISSING_VOLUME" in payload["blockers"]
    assert payload["hard_blockers"] == ["HARD_MISSING_VOLUME"]
    assert payload["soft_penalties"] == []
    assert payload["warnings"] == []
    assert payload["entry_source"] == "last"
    assert payload["entry_status"] == "displayable"
    assert payload["quote_source"] == "tick_store"


def test_issue_classification_missing_enrichment_lowers_confidence_without_suppressing_advisory():
    entry = {
        "trade_id": "T-SOFT-ENRICH",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "entry": 230.15,
        "entry_status": "OK",
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "current_ltp": 230.15,
        "validation_reference_price": 230.15,
        "confidence_base": 0.72,
        "confidence": 0.64,
        "confidence_penalty_total": 0.08,
        "confidence_penalty_reasons": ["premium_out_of_band"],
        "tradable_reasons_blocking": ["MISSING_CROSS_ASSET_FEATURE"],
    }

    out = review_queue._apply_issue_classification(
        dict(entry),
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
    )

    assert out["hard_blockers"] == []
    assert out["soft_penalties"] == ["MISSING_CROSS_ASSET_FEATURE"]
    assert out["warnings"] == []
    assert float(out["confidence_base"]) == 0.72
    assert float(out["builder_confidence"]) == 0.72
    assert float(out["gating_base_confidence"]) == 0.72
    assert float(out["confidence_raw"]) == 0.72
    assert float(out["confidence_penalty_total"]) > 0.08
    assert "premium_out_of_band" in list(out["confidence_penalty_reasons"])
    assert "MISSING_CROSS_ASSET_FEATURE" in list(out["confidence_penalty_reasons"])
    assert float(out["confidence_final"]) > 0.5
    assert float(out["gating_final_confidence"]) == float(out["confidence_final"])
    assert out["advisory_visible"] is True
    assert out["is_executable"] is False
    assert out["execution_status"] == "queue_only"
    assert float(out["entry"]) == 230.15
    assert out["entry_status"] == "OK"


def test_issue_classification_does_not_overwrite_builder_confidence_with_final_confidence():
    entry = {
        "trade_id": "T-CONF-PRESERVE",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "entry": 230.15,
        "entry_status": "OK",
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "current_ltp": 230.15,
        "validation_reference_price": 230.15,
        "builder_confidence": 0.62,
        "confidence": 0.62,
        "confidence_base": 0.62,
        "trade_score_detail": {"confluence_score": 0.77},
        "tradable_reasons_blocking": ["MISSING_CROSS_ASSET_FEATURE"],
    }

    out = review_queue._apply_issue_classification(
        dict(entry),
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
    )

    assert float(out["builder_confidence"]) == 0.62
    assert float(out["gating_base_confidence"]) == 0.62
    assert float(out["gating_final_confidence"]) == float(out["confidence_final"])
    assert float(out["gating_final_confidence"]) < 0.62
    assert float(out["confidence"]) == float(out["confidence_final"])


def test_issue_classification_display_entry_fallback_is_warning_only():
    entry = {
        "trade_id": "T-WARN-FALLBACK",
        "symbol": "NIFTY",
        "permission": "ADVISORY_ONLY",
        "entry": 230.15,
        "entry_status": "OK",
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "confidence_base": 0.52,
        "global_confidence": 0.52,
        "tradable_reasons_blocking": ["DISPLAY_ENTRY_FALLBACK"],
    }

    out = review_queue._apply_issue_classification(
        dict(entry),
        mode_for_entry="PAPER",
        allow_stale_quotes_for_entry=True,
    )

    assert out["hard_blockers"] == []
    assert out["soft_penalties"] == []
    assert out["warnings"] == ["DISPLAY_ENTRY_FALLBACK"]
    assert float(out["confidence_penalty"]) == 0.0
    assert float(out["confidence_penalty_total"]) == 0.0
    assert list(out["confidence_penalty_reasons"]) == []
    assert float(out["confidence_final"]) == 0.52
    assert out["advisory_visible"] is True
    assert out["execution_status"] == "advisory_only"
    assert float(out["entry"]) == 230.15
    assert out["entry_status"] == "OK"


def test_issue_classification_wide_spread_blocks_execution():
    entry = {
        "trade_id": "T-WIDE-SPREAD",
        "symbol": "NIFTY",
        "permission": "ADVISORY_ONLY",
        "entry": 230.15,
        "entry_status": "HARD_SPREAD_TOO_WIDE",
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "global_confidence": 0.66,
    }

    out = review_queue._apply_issue_classification(
        dict(entry),
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
    )

    assert out["hard_blockers"] == ["HARD_SPREAD_TOO_WIDE"]
    assert out["soft_penalties"] == []
    assert out["warnings"] == []
    assert out["advisory_visible"] is True
    assert out["is_executable"] is False
    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert float(out["entry"]) == 230.15
    assert out["entry_status"] == "HARD_SPREAD_TOO_WIDE"


def test_executable_claim_with_only_display_entry_is_downgraded_during_review_finalization():
    entry = {
        "trade_id": "T-DISPLAY-ONLY-CLAIM",
        "symbol": "NIFTY",
        "permission": "EXECUTE",
        "permission_reason": "execution_allowed",
        "readiness": "READY",
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "status": "READY",
        "entry": 230.15,
        "entry_source": "last",
        "entry_status": "displayable",
        "display_entry": 230.15,
        "display_entry_source": "last",
        "display_entry_status": "displayable",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "hard_blockers": [],
        "blockers": [],
    }

    out = review_queue._enforce_executable_entry_invariant(entry)

    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["status"] == "ADVISORY_ONLY"
    assert out["entry"] == 230.15
    assert out["execution_entry"] is None
    assert out["entry_status"] == "displayable"
    assert out["display_entry_status"] == "displayable"


def test_review_queue_syncs_final_confidence_and_derives_sizing_telemetry():
    entry = {
        "trade_id": "T-CONF-SIZE",
        "symbol": "NIFTY",
        "permission": "ADVISORY_ONLY",
        "entry": 230.15,
        "entry_status": "displayable",
        "display_entry": 230.15,
        "display_entry_source": "last",
        "display_entry_status": "displayable",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "non_executable",
        "builder_confidence": 0.55,
        "gating_final_confidence": 0.068,
        "confidence_final": 0.55,
        "confidence": 0.55,
        "sizing_confluence_score": 0.81,
        "qty": 2,
    }

    out = review_queue._synchronize_final_confidence(dict(entry))
    out = review_queue._apply_sizing_telemetry(out)

    assert out["builder_confidence"] == 0.55
    assert out["gating_final_confidence"] == 0.068
    assert out["confidence_final"] == 0.068
    assert out["confidence"] == 0.068
    assert out["sizing_reason"] == "OK"
    assert out["ml_proba_input"] == 0.55
    assert out["confluence_input"] == 0.81
    assert out["ml_proba_source"] == "builder_confidence"
    assert out["confluence_source"] == "sizing_confluence_score"
    assert out["confidence_size_multiplier"] is not None
    assert out["final_qty"] == 2


def test_review_queue_normalizes_canonical_quote_age_before_gating_and_emit():
    entry = {
        "trade_id": "T-AGE-NORM",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "quote_age_sec": 0.0,
        "price_age_sec": 102.9,
        "option_age_sec": None,
        "option_ltp_age_sec": 102.9,
    }

    out = review_queue._apply_canonical_quote_age(dict(entry))

    assert out["quote_age_sec"] == 0.0
    assert out["price_age_sec"] == 0.0
    assert out["option_age_sec"] == 0.0


def test_review_queue_drops_internal_stale_age_sentinel_from_emitted_fields():
    entry = {
        "trade_id": "T-AGE-SENTINEL",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "quote_age_sec": 10**9,
        "price_age_sec": None,
        "option_age_sec": None,
        "option_ltp_age_sec": None,
    }

    out = review_queue._apply_canonical_quote_age(dict(entry))

    assert out["quote_age_sec"] is None
    assert out["price_age_sec"] is None
    assert out["option_age_sec"] is None


def test_advisory_schema_round_trip_preserves_severity_fields():
    row = {
        "trade_id": "T-SEVERITY-1",
        "strategy_id": "CORE",
        "advisory_id": "ADV-SEVERITY-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "timestamp": "2026-03-08T10:00:00+00:00",
        "instrument_type": "OPT",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "non_executable",
        "display_entry": 72.5,
        "display_entry_source": "mark",
        "display_entry_status": "non_executable",
        "entry_reason": "display_from_mark",
        "entry_clear_reason": None,
        "entry": 72.5,
        "entry_status": "non_executable",
        "confidence": 0.7,
        "confidence_base": 0.82,
        "confidence_raw": 0.82,
        "confidence_model_raw": 0.88,
        "confidence_model_component": 0.88,
        "confidence_micro_component": 0.70,
        "confidence_micro_blend_method": "bounded_overlay",
        "confidence_after_micro": 0.84,
        "confidence_after_alpha": 0.81,
        "confidence_after_latency": 0.79,
        "confidence_before_soft_veto": 0.79,
        "confidence_after_soft_veto": 0.74,
        "confidence_penalty_soft_veto_total": 0.05,
        "confidence_penalty_soft_veto_reasons": ["premium_out_of_band"],
        "confidence_gate_threshold": 0.30,
        "confidence_raw_gate_threshold": 0.55,
        "confidence_final_gate_threshold": 0.30,
        "confidence_rejection_stage": "soft_veto",
        "confidence_penalty": 0.12,
        "confidence_penalty_total": 0.12,
        "confidence_penalty_reasons": ["STALE_OPTION_LTP", "MISSING_CROSS_ASSET_FEATURE"],
        "confidence_final": 0.7,
        "readiness": "ADVISORY_ONLY",
        "hard_blockers": [],
        "soft_penalties": ["STALE_OPTION_LTP", "MISSING_CROSS_ASSET_FEATURE"],
        "warnings": ["DISPLAY_ENTRY_FALLBACK"],
        "blockers": ["STALE_OPTION_LTP", "MISSING_CROSS_ASSET_FEATURE", "DISPLAY_ENTRY_FALLBACK"],
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "advisory_only",
        "entry_source": "mark",
        "quote_source": "tick_store",
        "quote_age_sec": 1.25,
        "decision_explain": [],
        "market_open": True,
    }

    serialized = review_queue.serialize_advisory_row(row)
    deserialized = review_queue.deserialize_advisory_row(serialized)

    assert deserialized["hard_blockers"] == []
    assert deserialized["soft_penalties"] == ["STALE_OPTION_LTP", "MISSING_CROSS_ASSET_FEATURE"]
    assert deserialized["warnings"] == ["DISPLAY_ENTRY_FALLBACK"]
    assert float(deserialized["confidence_base"]) == 0.82
    assert float(deserialized["confidence_raw"]) == 0.82
    assert float(deserialized["confidence_model_raw"]) == 0.88
    assert float(deserialized["confidence_model_component"]) == 0.88
    assert float(deserialized["confidence_micro_component"]) == 0.70
    assert deserialized["confidence_micro_blend_method"] == "bounded_overlay"
    assert float(deserialized["confidence_after_micro"]) == 0.84
    assert float(deserialized["confidence_after_alpha"]) == 0.81
    assert float(deserialized["confidence_after_latency"]) == 0.79
    assert float(deserialized["confidence_before_soft_veto"]) == 0.79
    assert float(deserialized["confidence_after_soft_veto"]) == 0.74
    assert float(deserialized["confidence_penalty_soft_veto_total"]) == 0.05
    assert deserialized["confidence_penalty_soft_veto_reasons"] == ["premium_out_of_band"]
    assert float(deserialized["confidence_gate_threshold"]) == 0.30
    assert float(deserialized["confidence_raw_gate_threshold"]) == 0.55
    assert float(deserialized["confidence_final_gate_threshold"]) == 0.30
    assert deserialized["confidence_rejection_stage"] == "soft_veto"
    assert float(deserialized["confidence_penalty"]) == 0.12
    assert float(deserialized["confidence_penalty_total"]) == 0.12
    assert deserialized["confidence_penalty_reasons"] == ["STALE_OPTION_LTP", "MISSING_CROSS_ASSET_FEATURE"]
    assert float(deserialized["confidence_final"]) == 0.7
    assert deserialized["advisory_visible"] is True
    assert deserialized["is_executable"] is False
    assert deserialized["execution_status"] == "advisory_only"
    assert float(deserialized["entry"]) == 72.5
    assert deserialized["entry_status"] == "displayable"
    assert deserialized["display_entry"] == 72.5
    assert deserialized["display_entry_source"] == "mark"


def test_missing_option_token_does_not_use_underlying_or_rest_fallback(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: False)
    monkeypatch.setattr(review_queue, "_instrument_meta_map", lambda ttl_sec=3600: {})
    monkeypatch.setattr(review_queue, "resolve_option_token", lambda *args, **kwargs: None)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))

    def _should_not_fetch(*_args, **_kwargs):
        raise AssertionError("REST fallback must not run when option token is missing")

    monkeypatch.setattr(review_queue, "_fetch_option_ltp_rest", _should_not_fetch)

    trade = _make_trade(
        trade_id="T-MISSING",
        instrument_token=None,
        tradingsymbol="NIFTY26MAR24600PE",
        symbol="NIFTY",
        strike=24600,
        option_type="PE",
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
        suggested_entry=123.45,
        entry=123.45,
    )
    review_queue.add_to_queue(trade, extra={"entry": 100.95})
    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0].get("entry") == 123.45
    assert rows[0]["permission"] == "ADVISORY_ONLY"
    assert rows[0]["execution_allowed"] is False
    assert rows[0]["final_action"] == "ADVISORY_ONLY"
    assert rows[0]["unresolved_contract"] is False
    assert rows[0]["approval_blocked"] is False
    assert rows[0]["status"] != "BLOCKED_CONTRACT"
    assert rows[0]["status_raw"] == "PLANNING"
    assert rows[0].get("suggested_entry") == 123.45
    assert "NO_TOKEN" not in list(rows[0].get("blockers") or [])


def test_tradingsymbol_known_without_token_resolves_from_instrument_map(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(
        review_queue,
        "_instrument_meta_map",
        lambda ttl_sec=3600: {
            445566: {
                "tradingsymbol": "NIFTY26MAR24600PE",
                "symbol": "NIFTY",
                "strike": 24600.0,
                "type": "PE",
                "expiry": "2026-03-26",
                "segment": "NFO-OPT",
            }
        },
    )

    trade = _make_trade(
        trade_id="T-TSYM-LOOKUP",
        symbol="NIFTY",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        strike=24600,
        option_type="PE",
        tradingsymbol="NIFTY26MAR24600PE",
        instrument_token=None,
        entry_price=123.45,
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )

    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["instrument_token"] == 445566
    assert rows[0]["unresolved_contract"] is False
    assert rows[0]["status"] != "BLOCKED_CONTRACT"


def test_tradingsymbol_known_but_token_missing_remains_non_executable_advisory(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "_instrument_meta_map", lambda ttl_sec=3600: {})
    monkeypatch.setattr(review_queue, "resolve_option_token", lambda *args, **kwargs: None)

    trade = _make_trade(
        trade_id="T-TSYM-NONEXEC",
        symbol="NIFTY",
        expiry_date="2026-03-26",
        expiry="2026-03-26",
        strike=24600,
        option_type="PE",
        tradingsymbol="NIFTY26MAR24600PE",
        instrument_token=None,
        entry_price=123.45,
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )

    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["unresolved_contract"] is False
    assert rows[0]["status"] != "BLOCKED_CONTRACT"
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["entry"] == 123.45
    assert "NO_TOKEN" not in list(rows[0].get("blockers") or [])


def test_valid_contract_missing_manual_approval_sets_approval_blocked(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (155.0, time.time()))
    monkeypatch.setattr(review_queue, "approval_status", lambda trade_id, payload_hash=None, now_epoch=None: (False, "approval_missing"))

    trade = _make_trade(
        trade_id="T-APPROVAL",
        instrument_token=55501,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )
    review_queue.add_to_queue(
        trade,
        extra={
            "approval_payload_hash": "hash-1",
            "approval_reason": "approval_missing",
        },
    )

    rows = json.loads(qpath.read_text())
    assert rows[0].get("unresolved_contract") is not True
    assert rows[0]["approval_blocked"] is True
    assert rows[0]["status"] == "BLOCKED_APPROVAL"
    assert rows[0]["status_raw"] == "PLANNING"
    assert rows[0]["permission"] == "ADVISORY_ONLY"
    assert rows[0]["execution_allowed"] is False
    assert rows[0]["approval_reason"] == "approval_missing"


def test_valid_contract_without_manual_approval_does_not_block(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (155.0, time.time()))
    monkeypatch.setattr(review_queue, "approval_status", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval_status should not run")))

    trade = _make_trade(
        trade_id="T-NO-MANUAL-APPROVAL",
        instrument_token=55501,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )
    review_queue.add_to_queue(
        trade,
        extra={
            "approval_payload_hash": "hash-2",
            "approval_reason": "approval_missing",
        },
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["approval_blocked"] is False


def test_sim_mode_can_skip_manual_approval_when_config_excludes_sim(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", True, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (155.0, time.time()))
    monkeypatch.setattr(review_queue, "approval_status", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval_status should not run in SIM when excluded")))

    trade = _make_trade(
        trade_id="T-SIM-SKIP-APPROVAL",
        instrument_token=55501,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )
    review_queue.add_to_queue(
        trade,
        extra={
            "approval_payload_hash": "hash-3",
            "approval_reason": "approval_missing",
        },
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["approval_blocked"] is False


def test_has_valid_broker_contract_requires_token_tradingsymbol_and_expiry():
    assert review_queue._has_valid_broker_contract(
        {
            "instrument_token": 12345,
            "tradingsymbol": "NIFTY26MAR24600PE",
            "expiry_date": "2026-03-26",
            "instrument_id": "synthetic-only-is-ignored",
        }
    ) is True


def test_has_valid_broker_contract_rejects_synthetic_instrument_id_without_tradingsymbol():
    assert review_queue._has_valid_broker_contract(
        {
            "instrument_token": 12345,
            "tradingsymbol": None,
            "expiry_date": "2026-03-26",
            "instrument_id": "NIFTY|OPT|2026-03-26|24600|PE",
        }
    ) is False


def test_enrich_contract_identity_fills_token_backed_metadata(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_instrument_meta_map",
        lambda ttl_sec=3600: {
            12345: {
                "tradingsymbol": "NIFTY26MAR24600PE",
                "expiry": "2026-03-26",
                "type": "PE",
                "strike": 24600.0,
            }
        },
    )
    monkeypatch.setattr(review_queue, "_option_chain_meta_map", lambda ttl_sec=300: {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}})

    entry = review_queue._enrich_contract_identity(
        {
            "instrument": "OPT",
            "symbol": "NIFTY",
            "instrument_token": 12345,
            "tradingsymbol": None,
            "expiry_date": None,
            "strike": 24600,
            "option_type": "PE",
        }
    )

    assert entry["tradingsymbol"] == "NIFTY26MAR24600PE"
    assert entry["expiry_date"] == "2026-03-26"
    assert review_queue._has_valid_broker_contract(entry) is True


def test_token_present_without_metadata_enrichment_blocks_as_unresolved_contract(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "_instrument_meta_map", lambda ttl_sec=3600: {})
    monkeypatch.setattr(review_queue, "_option_chain_meta_map", lambda ttl_sec=300: {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}})
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not subscribe unresolved contract")))
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not query ltp for unresolved contract")))

    trade = _make_trade(
        trade_id="T-PARTIAL-TOKEN",
        symbol="NIFTY",
        instrument_token=12345,
        tradingsymbol=None,
        expiry_date=None,
        expiry=None,
        instrument_id="12345",
        permission="EXECUTE",
        execution_allowed=True,
        final_action="EXECUTE",
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["unresolved_contract"] is True
    assert rows[0]["approval_blocked"] is False
    assert rows[0]["status"] == "BLOCKED_CONTRACT"
    assert rows[0]["status_raw"] == "PLANNING"
    assert rows[0]["permission"] == "BLOCK"
    assert rows[0]["permission_reason"] == "unresolved_contract"
    assert rows[0]["missing_identity_fields"] == ["tradingsymbol", "expiry_date"]


def test_unresolved_contract_not_emitted_to_normal_suggestions_and_keeps_debug_fields(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    rejected_path = tmp_path / "rejected_candidates.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "rejected_candidates_paths", lambda: [rejected_path])
    monkeypatch.setattr(review_queue, "_instrument_meta_map", lambda ttl_sec=3600: {})
    monkeypatch.setattr(review_queue, "_option_chain_meta_map", lambda ttl_sec=300: {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}})

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-BLOCKED-LOG",
            symbol="NIFTY",
            instrument_token=12345,
            tradingsymbol=None,
            expiry_date=None,
            expiry=None,
            instrument_id="12345",
        )
    )

    queue_rows = json.loads(qpath.read_text())
    assert queue_rows[0]["status"] == "BLOCKED_CONTRACT"
    assert queue_rows[0]["status_raw"] == "PLANNING"
    assert queue_rows[0]["hard_reason"] == "unresolved_contract"
    assert queue_rows[0]["entry_status"] == "missing"
    assert queue_rows[0]["quote_validation_status"] == "MISSING_OPTION_TOKEN"
    assert queue_rows[0]["missing_identity_fields"] == ["tradingsymbol", "expiry_date"]
    assert not suggestions_path.exists()
    blocked_rows = [json.loads(line) for line in rejected_path.read_text().splitlines() if line.strip()]
    assert blocked_rows[-1]["status"] == "BLOCKED_CONTRACT"
    assert blocked_rows[-1]["hard_reason"] == "unresolved_contract"
    assert blocked_rows[-1]["reason_code"] == "unresolved_contract"


def test_valid_row_still_emits_normal_suggestion(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    rejected_path = tmp_path / "rejected_candidates.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "rejected_candidates_paths", lambda: [rejected_path])
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))

    trade = _make_trade(
        trade_id="T-SUGGEST",
        instrument_token=99123,
        tradingsymbol="SENSEX26MAR81700PE",
        execution_mode="PAPER",
        market_open=False,
        market_context={"market_open": False, "execution_mode": "PAPER"},
        entry_price=257.0,
    )
    review_queue.add_to_queue(trade)

    suggestion_rows = [json.loads(line) for line in suggestions_path.read_text().splitlines() if line.strip()]
    assert suggestion_rows[-1]["trade_id"] == "T-SUGGEST"
    assert suggestion_rows[-1]["status"] == "ADVISORY_ONLY"
    assert suggestion_rows[-1]["status_raw"] == "PLANNING"
    assert suggestion_rows[-1]["entry_status"] == "displayable"
    assert suggestion_rows[-1]["display_entry"] == 565.0
    assert suggestion_rows[-1]["display_entry_status"] == "displayable"
    assert suggestion_rows[-1]["soft_penalties"] == []
    assert suggestion_rows[-1]["warnings"] == ["PRICE_MISMATCH"]
    assert not rejected_path.exists()


def test_normalize_queue_row_preserves_canonical_display_entry_when_non_executable():
    normalized = review_queue._normalize_queue_row(
        {
            "trade_id": "T-CANONICAL-NORM",
            "symbol": "NIFTY",
            "status": "ADVISORY_ONLY",
            "display_entry": 72.5,
            "display_entry_source": "mark",
            "display_entry_status": "non_executable",
            "execution_entry": None,
            "execution_entry_source": "none",
            "execution_entry_status": "non_executable",
            "entry_reason": "display_from_mark",
            "entry_clear_reason": None,
            "suggested_entry": 99.0,
            "current_ltp": 101.0,
        }
    )

    assert normalized["entry"] == 72.5
    assert normalized["entry_status"] == "non_executable"
    assert normalized["entry_source"] == "mark"


def test_normalize_queue_row_preserves_quote_validation_status_when_display_alias_differs():
    normalized = review_queue._normalize_queue_row(
        {
            "trade_id": "T-QUOTE-STATUS",
            "symbol": "NIFTY",
            "status": "ADVISORY_ONLY",
            "entry_status": "OK",
            "display_entry": 72.5,
            "display_entry_source": "mark",
            "display_entry_status": "non_executable",
            "execution_entry": None,
            "execution_entry_source": "none",
            "execution_entry_status": "non_executable",
            "entry_reason": "display_from_mark",
            "entry_clear_reason": None,
        }
    )

    assert normalized["quote_validation_status"] == "OK"
    assert normalized["entry_status"] == "non_executable"


def test_validation_uses_executable_reference_over_stale_signal_price(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))

    trade = _make_trade(
        trade_id="T-VALIDATION-REF-OK",
        instrument_token=99140,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        signal_price=150.0,
        entry_price=565.0,
        expected_entry=565.0,
        entry_price_source="ask",
        expected_entry_source="ask",
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "OK"
    assert rows[0]["entry"] == 565.0
    assert rows[0]["suggested_entry"] == 565.0
    assert rows[0]["current_ltp"] == 565.0
    assert rows[0]["validation_signal_price"] == 150.0
    assert rows[0]["validation_reference_price"] == 565.0
    assert rows[0]["validation_reference_source"] == "expected_entry"
    assert rows[0]["entry_price_source"] == "ask"
    assert rows[0]["expected_entry_source"] == "ask"
    assert rows[0]["option_ltp_source"] == "tick_store"
    assert isinstance(rows[0]["price_age_sec"], (int, float))
    assert rows[0]["pre_validation_entry"] == 565.0
    assert rows[0]["post_validation_entry"] == 565.0


def test_validation_keeps_price_mismatch_when_executable_reference_is_off(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))

    trade = _make_trade(
        trade_id="T-VALIDATION-REF-BAD",
        instrument_token=99141,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        signal_price=150.0,
        entry_price=257.0,
        expected_entry=257.0,
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["validation_signal_price"] == 150.0
    assert rows[0]["validation_reference_price"] == 257.0
    assert rows[0]["validation_reference_source"] == "expected_entry"
    assert rows[0]["entry"] == 565.0
    assert rows[0]["pre_validation_entry"] == 257.0
    assert rows[0]["post_validation_entry"] == 565.0


def test_validation_reference_price_does_not_depend_on_expected_entry_being_populated_later(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (224.25, time.time()))

    trade = _make_trade(
        trade_id="T-VALIDATION-ENTRY-FIRST",
        instrument_token=99142,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        signal_price=100.93,
        entry=224.25,
        entry_price=224.25,
        expected_entry=None,
        suggested_entry=None,
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "OK"
    assert rows[0]["validation_signal_price"] == 100.93
    assert rows[0]["validation_reference_price"] == 224.25
    assert rows[0]["validation_reference_source"] == "entry_price"
    assert rows[0]["pre_validation_entry"] == 224.25
    assert rows[0]["post_validation_entry"] == 224.25


def test_stale_pre_validation_entry_is_backfilled_before_validation(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (225.15, time.time()))

    trade = _make_trade(
        trade_id="T-PRE-VALIDATION-BACKFILL",
        instrument_token=99143,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        signal_price=100.95,
        entry=100.95,
        entry_price=225.15,
        expected_entry=None,
        suggested_entry=None,
    )
    review_queue.add_to_queue(trade, extra={"entry": 100.95})

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "OK"
    assert rows[0]["validation_signal_price"] == 100.95
    assert rows[0]["validation_reference_price"] == 225.15
    assert rows[0]["validation_reference_source"] == "entry_price"
    assert rows[0]["pre_validation_entry"] == 100.95
    assert rows[0]["post_validation_entry"] == 225.15
    assert rows[0]["entry"] == 225.15
    assert rows[0]["expected_entry"] == 225.15
    assert rows[0]["current_ltp"] == 225.15


def test_synthetic_offhours_row_skips_price_mismatch_and_marks_offhours_synthetic_without_live_tick(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))

    trade = _make_trade(
        trade_id="T-SYNTH-OFFHOURS",
        instrument_token=99144,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        entry=100.95,
        entry_price=225.15,
        expected_entry=None,
        option_ltp_source="synthetic_offhours",
        quote_source="synthetic_offhours",
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "OFFHOURS_SYNTHETIC"
    assert rows[0]["suggested_entry"] == 225.15
    assert rows[0]["entry"] == 225.15
    assert rows[0]["expected_entry"] == 225.15
    assert rows[0]["validation_reference_price"] == 225.15
    assert rows[0]["validation_reference_source"] == "synthetic_offhours"
    assert rows[0]["current_ltp"] is None


def test_offhours_synthetic_emits_without_schema_warning(tmp_path, monkeypatch, caplog):
    qpath = tmp_path / "review_queue.json"
    suggestions_path = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "canonical_suggestions_log_path", lambda: suggestions_path)
    monkeypatch.setattr(review_queue, "suggestion_log_paths", lambda: [suggestions_path])
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))

    trade = _make_trade(
        trade_id="T-SYNTH-SCHEMA",
        instrument_token=99144,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        entry=100.95,
        entry_price=225.15,
        expected_entry=None,
        option_ltp_source="synthetic_offhours",
        quote_source="synthetic_offhours",
    )

    with caplog.at_level("WARNING"):
        review_queue.add_to_queue(trade)

    payload = json.loads(suggestions_path.read_text().strip())
    assert payload["display_entry"] == 225.15
    assert payload["display_entry_status"] == "displayable"
    assert payload["entry_status"] == "displayable"
    assert "advisory_queue_schema_error" not in caplog.text
    assert "advisory_emit_schema_error" not in caplog.text


def test_synthetic_offhours_row_upgrades_to_live_tick_store_when_fresh_quote_exists(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (225.15, time.time()))

    trade = _make_trade(
        trade_id="T-SYNTH-LIVE-TAKEOVER",
        instrument_token=99146,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        entry=100.95,
        entry_price=225.15,
        expected_entry=None,
        option_ltp_source="synthetic_offhours",
        quote_source="synthetic_offhours",
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    row = rows[0]
    assert row["current_ltp"] == 225.15
    assert row["entry"] == 225.15
    assert row["expected_entry"] == 225.15
    assert row["entry_status"] == "displayable"
    assert row["quote_validation_status"] == "OK"
    assert row["option_ltp_source"] == "tick_store"
    assert row["quote_source"] == "tick_store"
    assert row["validation_reference_source"] != "expected_entry"
    assert row["validation_reference_source"] == "tick_store"
    assert "NO_LIVE_OPTION_FEED" not in list(row.get("blockers") or [])
    assert "NO_LIVE_OPTION_FEED" not in list(row.get("hard_blockers") or [])
    assert "NO_LIVE_OPTION_FEED" not in list(row.get("soft_penalties") or [])


def test_synthetic_offhours_row_clears_stale_expected_entry_before_live_validation(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (206.6, time.time()))

    trade = _make_trade(
        trade_id="T-SYNTH-EXPECTED-RECOVER",
        instrument_token=99147,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        entry=98.28,
        entry_price=98.28,
        expected_entry=98.28,
        option_ltp_source="synthetic_offhours",
        quote_source="synthetic_offhours",
        entry_condition="BUY_ABOVE",
    )
    review_queue.add_to_queue(trade)

    row = json.loads(qpath.read_text())[0]
    assert row["current_ltp"] == 206.6
    assert row["entry"] == 206.6
    assert row["expected_entry"] == 206.6
    assert row["expected_entry_source"] == "tick_store"
    assert row["validation_reference_source"] != "expected_entry"
    assert row["validation_reference_source"] != "expected_entry"
    assert row["validation_reference_price"] == 206.6
    assert row["validation_reference_source"] == "tick_store"
    assert row["entry_status"] == "displayable"
    assert row["quote_validation_status"] == "OK"
    assert "PRICE_MISMATCH" not in list(row.get("blockers") or [])
    assert "PRICE_MISMATCH" not in list(row.get("hard_blockers") or [])
    assert "PRICE_MISMATCH" not in list(row.get("soft_penalties") or [])


def test_quick_synth_row_forces_live_reference_even_with_stale_expected_entry(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (199.45, time.time()))

    trade = _make_trade(
        trade_id="T-QUICK-SYNTH-LIVE-REF",
        instrument_token=99148,
        tradingsymbol="NIFTY26MAR22450CE",
        instrument_id="NIFTY26MAR22450CE",
        symbol="NIFTY",
        strategy="QUICK_SYNTH",
        entry=98.26,
        entry_price=98.26,
        expected_entry=98.26,
        expected_entry_source="ask",
        option_ltp_source="tick_store",
        quote_source="tick_store",
        entry_condition="BUY_ABOVE",
    )
    review_queue.add_to_queue(trade)

    row = json.loads(qpath.read_text())[0]
    assert row["option_ltp_source"] == "tick_store"
    assert row["quote_source"] == "tick_store"
    assert row["current_ltp"] == 199.45
    assert row["expected_entry"] == 199.45
    assert row["expected_entry_source"] == "tick_store"
    assert row["validation_reference_source"] == "tick_store"
    assert row["validation_reference_source"] != "expected_entry"
    assert row["entry_status"] == "displayable"
    assert row["quote_validation_status"] == "OK"
    assert "PRICE_MISMATCH" not in list(row.get("blockers") or [])


def test_live_row_still_produces_price_mismatch_when_entry_and_ltp_diverge(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (565.0, time.time()))

    trade = _make_trade(
        trade_id="T-LIVE-MISMATCH-CONTROL",
        instrument_token=99145,
        tradingsymbol="SENSEX26MAR81700PE",
        instrument_id="SENSEX26MAR81700PE",
        entry_price=257.0,
        expected_entry=257.0,
        option_ltp_source="tick_store",
    )
    review_queue.add_to_queue(trade)

    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] == "displayable"
    assert rows[0]["quote_validation_status"] == "PRICE_MISMATCH"
    assert rows[0]["validation_reference_source"] == "expected_entry"


def test_ready_status_preserves_raw_planning_for_executable_row(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(review_queue, "build_permission_payload", lambda **kwargs: {"permission": "EXECUTE", "permission_reason": "aligned_high_conf", "global_confidence": 0.91})
    monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.91})

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-READY",
            instrument_token=99123,
            tradingsymbol="SENSEX26MAR81700PE",
            instrument_id="SENSEX26MAR81700PE",
            permission="EXECUTE",
            execution_allowed=True,
            final_action="EXECUTE",
            execution_mode="LIVE",
            quote_source="tick_store",
            option_ltp_source="tick_store",
            quote_age_sec=0.5,
            signal_price=150.0,
            current_ltp=150.0,
            best_bid=149.5,
            best_ask=150.0,
            bid=149.5,
            ask=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["status"] == "READY"
    assert rows[0]["status_raw"] == "PLANNING"


def test_queue_only_permission_preserves_queue_only_final_action(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.29,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.29,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-QUEUE",
            instrument_token=99123,
            tradingsymbol="SENSEX26MAR81700PE",
            instrument_id="SENSEX26MAR81700PE",
            signal_price=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission"] == "QUEUE_ONLY"
    assert rows[0]["final_action"] == "QUEUE_ONLY"
    assert rows[0]["status"] == "QUEUE_ONLY"
    assert rows[0]["status_raw"] == "PLANNING"
    assert float(rows[0]["threshold_display"]) == 0.0
    assert float(rows[0]["threshold_advisory"]) == 0.15
    assert float(rows[0]["threshold_execution"]) == 0.30
    assert rows[0]["confidence_vs_threshold_reason"] == "meets_advisory_below_execution_threshold"


def test_entry_lifecycle_failure_adds_blocker_without_overriding_queue_only(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.29,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.29,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-LIFECYCLE-PRESERVE",
            instrument_token=99188,
            tradingsymbol="SENSEX26MAR81700PE",
            instrument_id="SENSEX26MAR81700PE",
            permission="QUEUE_ONLY",
            permission_reason="medium_global_conf",
            readiness="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            execution_status="queue_only",
            signal_price=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission"] == "QUEUE_ONLY"
    assert rows[0]["permission_reason"] == "medium_global_conf"
    assert rows[0]["readiness"] == "QUEUE_ONLY"
    assert rows[0]["final_action"] == "QUEUE_ONLY"
    assert rows[0]["entry_status"] == "missing"
    assert "MISSING_ENTRY" in list(rows[0].get("blockers") or [])


def test_advisory_only_permission_stays_advisory_only_for_low_confidence(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "ADVISORY_ONLY",
            "permission_reason": "low_global_conf",
            "global_confidence": 0.14,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.14,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-ADVISORY",
            instrument_token=99124,
            tradingsymbol="SENSEX26MAR81700CE",
            instrument_id="SENSEX26MAR81700CE",
            option_type="CE",
            signal_price=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission"] == "ADVISORY_ONLY"
    assert rows[0]["final_action"] == "ADVISORY_ONLY"
    assert rows[0]["status"] == "ADVISORY_ONLY"
    assert float(rows[0]["threshold_display"]) == 0.0
    assert float(rows[0]["threshold_advisory"]) == 0.15
    assert float(rows[0]["threshold_execution"]) == 0.30
    assert rows[0]["confidence_vs_threshold_reason"] == "below_advisory_threshold"


def test_execute_permission_stays_execute_when_aligned_and_high_confidence(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "EXECUTE",
            "permission_reason": "aligned_high_conf",
            "global_confidence": 0.91,
        },
    )
    monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.91})

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-EXECUTE",
            instrument_token=99125,
            tradingsymbol="SENSEX26MAR81800PE",
            instrument_id="SENSEX26MAR81800PE",
            strike=81800,
            execution_mode="LIVE",
            quote_source="tick_store",
            option_ltp_source="tick_store",
            quote_age_sec=0.5,
            signal_price=150.0,
            current_ltp=150.0,
            best_bid=149.5,
            best_ask=150.0,
            bid=149.5,
            ask=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission"] == "EXECUTE"
    assert rows[0]["final_action"] == "EXECUTE"
    assert rows[0]["status"] == "READY"
    assert float(rows[0]["threshold_display"]) == 0.0
    assert float(rows[0]["threshold_advisory"]) == 0.15
    assert float(rows[0]["threshold_execution"]) == 0.30
    assert rows[0]["confidence_vs_threshold_reason"] == "meets_execution_threshold"


def test_high_confidence_permission_downgrade_records_hard_gate_provenance(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "EXECUTE",
            "permission_reason": "aligned_high_conf",
            "global_confidence": 0.91,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": False,
            "hard_reasons": ["HARD_SPREAD_TOO_WIDE"],
            "soft_reasons": [],
            "final_confidence": 0.91,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-QUEUE-DOWNGRADE",
            instrument_token=99126,
            tradingsymbol="SENSEX26MAR81900PE",
            instrument_id="SENSEX26MAR81900PE",
            strike=81900,
            execution_mode="LIVE",
            quote_source="tick_store",
            option_ltp_source="tick_store",
            quote_age_sec=0.5,
            signal_price=150.0,
            current_ltp=150.0,
            best_bid=149.5,
            best_ask=150.0,
            bid=149.5,
            ask=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission_base"] == "EXECUTE"
    assert rows[0]["permission_reason_base"] == "aligned_high_conf"
    assert rows[0]["permission"] == "EXECUTE"
    assert rows[0]["permission_reason"] == "aligned_high_conf"
    assert rows[0].get("permission_downgraded_from") in (None, "")
    assert rows[0].get("permission_downgrade_reason") in (None, "")
    assert rows[0]["readiness"] == "ADVISORY_ONLY"
    assert rows[0]["execution_status"] == "advisory_only"
    assert rows[0]["final_action"] == "ADVISORY_ONLY"
    assert rows[0]["final_blocker"] == "HARD_SPREAD_TOO_WIDE"
    assert rows[0]["confidence_vs_threshold_reason"] == "hard_blocker_overrides_threshold"


def test_unknown_volume_stays_none_in_gate_candidate_and_does_not_fall_back_to_oi(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    captured = {}
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
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

    def _capture_gate(candidate, snapshot):
        captured["candidate"] = dict(candidate)
        return {"hard_pass": False, "hard_reasons": ["HARD_MISSING_VOLUME"], "soft_reasons": [], "final_confidence": 0.35}

    monkeypatch.setattr(review_queue, "gate_decision", _capture_gate)

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-UNKNOWN-VOLUME",
            instrument_token=99129,
            tradingsymbol="SENSEX26MAR82200PE",
            instrument_id="SENSEX26MAR82200PE",
            strike=82200,
            oi=99999,
            volume=None,
        )
    )

    rows = json.loads(qpath.read_text())
    assert captured["candidate"]["volume"] is None
    assert rows[0]["permission_base"] == "QUEUE_ONLY"
    assert rows[0]["permission_reason_base"] == "medium_global_conf"
    assert rows[0]["permission"] == "QUEUE_ONLY"
    assert rows[0]["permission_reason"] == "medium_global_conf"
    assert rows[0].get("permission_downgraded_from") in (None, "")
    assert rows[0].get("permission_downgrade_reason") in (None, "")
    assert rows[0]["final_blocker"] == "HARD_MISSING_VOLUME"


def test_option_chain_liquidity_populates_queued_entry_volume_and_oi(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "_option_chain_meta_map",
        lambda ttl_sec=300: {
            "by_token": {
                99131: {
                    "instrument_token": 99131,
                    "tradingsymbol": "SENSEX26MAR82400PE",
                    "expiry": "2026-03-05",
                    "strike": 82400.0,
                    "type": "PE",
                    "volume": 4321.0,
                    "current_volume": 4321.0,
                    "oi": 67890.0,
                    "oi_change": 321.0,
                    "quote_age_sec": 1.25,
                }
            },
            "by_contract": {},
            "by_symbol_strike_type": {},
        },
    )
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.35,
        },
    )
    monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.35})

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-CHAIN-LIQUIDITY",
            instrument_token=99131,
            tradingsymbol="SENSEX26MAR82400PE",
            instrument_id="SENSEX26MAR82400PE",
            strike=82400,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["volume"] == 4321.0
    assert rows[0]["current_volume"] == 4321.0
    assert rows[0]["oi"] == 67890.0
    assert rows[0]["oi_change"] == 321.0
    assert rows[0]["quote_age_sec"] == 1.25
    assert rows[0]["liquidity_source"] == "option_chain_meta"
    assert rows[0]["liquidity_missing_fields"] == []


def test_queue_entry_preserves_trade_liquidity_fields(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
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
    monkeypatch.setattr(review_queue, "gate_decision", lambda *_args, **_kwargs: {"hard_pass": True, "hard_reasons": [], "soft_reasons": [], "final_confidence": 0.35})

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-TRADE-LIQUIDITY",
            instrument_token=99133,
            tradingsymbol="SENSEX26MAR82600PE",
            instrument_id="SENSEX26MAR82600PE",
            volume=4321.0,
            current_volume=4321.0,
            oi=67890.0,
            oi_change=321.0,
            quote_age_sec=0.8,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["volume"] == 4321.0
    assert rows[0]["current_volume"] == 4321.0
    assert rows[0]["oi"] == 67890.0
    assert rows[0]["oi_change"] == 321.0
    assert rows[0]["quote_age_sec"] == 0.8
    assert rows[0]["liquidity_source"] == "trade_payload"
    assert rows[0]["liquidity_cache_hit"] is False
    assert rows[0]["liquidity_missing_fields"] == []


def test_queue_entry_hydrates_liquidity_from_cache_when_trade_fields_missing(tmp_path, monkeypatch):
    clear_option_liquidity_cache()
    try:
        qpath = tmp_path / "review_queue.json"
        captured = {}
        monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
        monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
        monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
        monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
        monkeypatch.setattr(
            review_queue,
            "_option_chain_meta_map",
            lambda ttl_sec=300: {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}},
        )
        monkeypatch.setattr(
            review_queue,
            "build_permission_payload",
            lambda **kwargs: {
                "permission": "QUEUE_ONLY",
                "permission_reason": "medium_global_conf",
                "global_confidence": 0.35,
            },
        )

        def _capture_gate(candidate, _snapshot):
            captured["candidate"] = dict(candidate)
            return {
                "hard_pass": candidate.get("volume") == 5100.0,
                "hard_reasons": [] if candidate.get("volume") == 5100.0 else ["HARD_MISSING_VOLUME"],
                "soft_reasons": [],
                "final_confidence": 0.35,
            }

        monkeypatch.setattr(review_queue, "gate_decision", _capture_gate)
        update_option_liquidity_cache(
            [
                {
                    "symbol": "SENSEX",
                    "expiry": "2026-03-05",
                    "strike": 81700,
                    "type": "PE",
                    "instrument_token": 99135,
                    "volume": 5100,
                    "current_volume": 5100,
                    "oi": 45000,
                    "oi_change": 125,
                    "snapshot_ts_epoch": time.time(),
                }
            ],
            source="unit_test_cache",
        )

        review_queue.add_to_queue(
            _make_trade(
                trade_id="T-CACHE-LIQUIDITY",
                instrument_token=99135,
                tradingsymbol="SENSEX26MAR81700PE",
                instrument_id="SENSEX26MAR81700PE",
            )
        )

        rows = json.loads(qpath.read_text())
        assert captured["candidate"]["volume"] == 5100.0
        assert rows[0]["volume"] == 5100.0
        assert rows[0]["current_volume"] == 5100.0
        assert rows[0]["oi"] == 45000.0
        assert rows[0]["oi_change"] == 125.0
        assert rows[0]["liquidity_source"] == "unit_test_cache"
        assert rows[0]["liquidity_cache_hit"] is True
        assert rows[0]["liquidity_missing_fields"] == []
        assert rows[0]["permission"] == "QUEUE_ONLY"
    finally:
        clear_option_liquidity_cache()


def test_option_chain_volume_prevents_hard_missing_volume_gate_failure(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    captured = {}
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "_option_chain_meta_map",
        lambda ttl_sec=300: {
            "by_token": {
                99132: {
                    "instrument_token": 99132,
                    "tradingsymbol": "SENSEX26MAR82500PE",
                    "expiry": "2026-03-05",
                    "strike": 82500.0,
                    "type": "PE",
                    "volume": 5000.0,
                    "current_volume": 5000.0,
                    "oi": 25000.0,
                    "oi_change": 250.0,
                }
            },
            "by_contract": {},
            "by_symbol_strike_type": {},
        },
    )
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "QUEUE_ONLY",
            "permission_reason": "medium_global_conf",
            "global_confidence": 0.35,
        },
    )

    def _capture_gate(candidate, _snapshot):
        captured["candidate"] = dict(candidate)
        return {
            "hard_pass": candidate.get("volume") == 5000.0,
            "hard_reasons": [] if candidate.get("volume") == 5000.0 else ["HARD_MISSING_VOLUME"],
            "soft_reasons": [],
            "final_confidence": 0.35,
        }

    monkeypatch.setattr(review_queue, "gate_decision", _capture_gate)

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-CHAIN-VOLUME-GATE",
            instrument_token=99132,
            tradingsymbol="SENSEX26MAR82500PE",
            instrument_id="SENSEX26MAR82500PE",
            strike=82500,
        )
    )

    rows = json.loads(qpath.read_text())
    assert captured["candidate"]["volume"] == 5000.0
    assert rows[0]["permission"] == "QUEUE_ONLY"
    assert rows[0]["permission_reason"] == "medium_global_conf"
    assert rows[0]["final_action"] == "QUEUE_ONLY"
    assert rows[0].get("permission_downgraded_from") in (None, "")


def test_medium_confidence_candidate_with_valid_volume_stays_queue_only(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
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
        lambda candidate, _snapshot: {
            "hard_pass": candidate.get("volume") == 5000.0,
            "hard_reasons": [] if candidate.get("volume") == 5000.0 else ["HARD_MISSING_VOLUME"],
            "soft_reasons": [],
            "final_confidence": 0.35,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-VALID-VOLUME",
            instrument_token=99130,
            tradingsymbol="SENSEX26MAR82300PE",
            instrument_id="SENSEX26MAR82300PE",
            strike=82300,
            volume=5000,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission"] == "QUEUE_ONLY"
    assert rows[0]["permission_reason"] == "medium_global_conf"
    assert rows[0]["final_action"] == "QUEUE_ONLY"
    assert rows[0]["status"] == "QUEUE_ONLY"
    assert rows[0].get("permission_downgraded_from") in (None, "")


def test_low_conf_advisory_only_keeps_base_permission_reason(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "ADVISORY_ONLY",
            "permission_reason": "low_global_conf",
            "global_confidence": 0.14,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.14,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-LOW-CONF",
            instrument_token=99127,
            tradingsymbol="SENSEX26MAR82000CE",
            instrument_id="SENSEX26MAR82000CE",
            option_type="CE",
            right="CE",
            strike=82000,
            signal_price=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission_base"] == "ADVISORY_ONLY"
    assert rows[0]["permission_reason_base"] == "low_global_conf"
    assert rows[0]["permission"] == "ADVISORY_ONLY"
    assert rows[0]["permission_reason"] == "low_global_conf"
    assert rows[0].get("permission_downgraded_from") in (None, "")
    assert rows[0].get("permission_downgrade_reason") in (None, "")
    assert rows[0]["confidence_vs_threshold_reason"] == "below_advisory_threshold"


def test_execute_permission_soft_conf_reject_records_downgrade_provenance(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "GATING_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (150.0, time.time()))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        review_queue,
        "build_permission_payload",
        lambda **kwargs: {
            "permission": "EXECUTE",
            "permission_reason": "aligned_high_conf",
            "global_confidence": 0.91,
        },
    )
    monkeypatch.setattr(
        review_queue,
        "gate_decision",
        lambda *_args, **_kwargs: {
            "hard_pass": True,
            "hard_reasons": [],
            "soft_reasons": [],
            "final_confidence": 0.25,
        },
    )

    review_queue.add_to_queue(
        _make_trade(
            trade_id="T-SOFT-CONF-DOWNGRADE",
            instrument_token=99128,
            tradingsymbol="SENSEX26MAR82100PE",
            instrument_id="SENSEX26MAR82100PE",
            strike=82100,
            execution_mode="LIVE",
            quote_source="tick_store",
            option_ltp_source="tick_store",
            quote_age_sec=0.5,
            signal_price=150.0,
            current_ltp=150.0,
            best_bid=149.5,
            best_ask=150.0,
            bid=149.5,
            ask=150.0,
        )
    )

    rows = json.loads(qpath.read_text())
    assert rows[0]["permission_base"] == "EXECUTE"
    assert rows[0]["permission_reason_base"] == "aligned_high_conf"
    assert rows[0]["permission"] == "EXECUTE"
    assert rows[0]["permission_reason"] == "aligned_high_conf"
    assert rows[0].get("permission_downgraded_from") in (None, "")
    assert rows[0].get("permission_downgrade_reason") in (None, "")
    assert rows[0]["confidence_vs_threshold_reason"] == "meets_advisory_below_execution_threshold"
