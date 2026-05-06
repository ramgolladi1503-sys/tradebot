from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from config import config as cfg
import core.reject_shadow as reject_shadow


IST = ZoneInfo("Asia/Kolkata")


def _ts_ist(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> float:
    return float(datetime(year, month, day, hour, minute, second, tzinfo=IST).timestamp())


def _base_event(symbol: str, ts_epoch: float) -> dict:
    return {
        "ts_epoch": ts_epoch,
        "symbol": symbol,
        "side": "BUY_CALL",
        "entry": 100.0,
        "stop": 95.0,
        "target": 105.0,
        "regime": "TREND",
        "confidence_score": 0.82,
        "gates_failed": ["quote_missing"],
        "soft_vetos": ["quote_missing"],
        "first_blocking_gate": "quote_missing",
        "hard_reject_reason": "quote_missing",
        "execution_allowed": False,
        "mode": "PAPER",
    }


def test_reject_shadow_insert_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)

    ts_epoch = _ts_ist(2026, 2, 24, 10, 5)
    event = _base_event("NIFTY", ts_epoch)
    first = reject_shadow.record_candidate_decision(event)
    second = reject_shadow.record_candidate_decision(event)
    assert first["status"] == "ok"
    assert second["status"] == "ok"

    conn = sqlite3.connect(db_path)
    try:
        reject_shadow.ensure_tables(conn)
        shadow_rows = conn.execute("SELECT COUNT(1) FROM rejected_trades_shadow").fetchone()[0]
        decision_rows = conn.execute("SELECT COUNT(1) FROM candidate_decision_events").fetchone()[0]
        assert int(shadow_rows) == 1
        assert int(decision_rows) == 1
    finally:
        conn.close()


def test_reject_shadow_evaluate_resolves_win_loss_timeout(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_eval.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_TIMEOUT_MIN", 30, raising=False)

    ts_win = _ts_ist(2026, 2, 24, 10, 0)
    ts_loss = _ts_ist(2026, 2, 24, 10, 2)
    ts_timeout = _ts_ist(2026, 2, 24, 10, 4)

    reject_shadow.record_candidate_decision(_base_event("NIFTY_WIN", ts_win))
    reject_shadow.record_candidate_decision(_base_event("NIFTY_LOSS", ts_loss))
    reject_shadow.record_candidate_decision(_base_event("NIFTY_TIMEOUT", ts_timeout))

    reject_shadow.record_price_trace(symbol="NIFTY_WIN", price=101.0, ts_epoch=ts_win + 10, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_WIN", price=105.2, ts_epoch=ts_win + 40, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_LOSS", price=99.0, ts_epoch=ts_loss + 8, mode="PAPER")
    reject_shadow.record_price_trace(symbol="NIFTY_LOSS", price=94.9, ts_epoch=ts_loss + 20, mode="PAPER")

    payload = reject_shadow.evaluate_pending(date="2026-02-24", batch_limit=200)
    assert payload["status"] == "ok"
    assert payload["processed"] >= 3

    conn = sqlite3.connect(db_path)
    try:
        status_map = {
            str(sym): str(status)
            for sym, status in conn.execute(
                "SELECT symbol, shadow_status FROM rejected_trades_shadow WHERE trade_date='2026-02-24'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert status_map["NIFTY_WIN"] == "WIN"
    assert status_map["NIFTY_LOSS"] == "LOSS"
    assert status_map["NIFTY_TIMEOUT"] == "TIMEOUT"


def test_reject_shadow_persists_score_telemetry_to_live_decision_stream(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_telemetry.sqlite"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(logs_root), raising=False)

    event = _base_event("NIFTY", _ts_ist(2026, 5, 4, 14, 11))
    event.update(
        {
            "liquidity_score": 0.8125,
            "quote_consistency_score": 0.91,
            "quote_age_sec": 1.25,
            "quote_truth_source": "live",
            "setup_score": 0.62,
            "trigger_score": 0.54,
            "entry_quality_score": 0.57,
            "execution_quality_score": 0.49,
            "rank_score": 0.578174,
            "raw_rank_score": 0.746802,
            "terminal_rank_score": 0.578174,
            "opportunity_score": 0.654476,
            "quote_validation_status": "OK",
            "quality_detail": {
                "setup_regime_alignment_score": 0.35,
                "setup_structure_score": 0.55,
                "setup_thesis_score": 0.62,
                "trigger_base_score": 0.61,
                "entry_invalidation_score": 0.66,
                "entry_overextension_score": 0.58,
                "entry_timing_quality_score": 0.63,
            },
        }
    )

    payload = reject_shadow.record_candidate_decision(event)

    assert payload["status"] == "ok"
    decision_path = logs_root / "desks" / "DEFAULT" / "candidate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = rows[-1]
    assert latest["liquidity_score"] == 0.8125
    assert latest["quote_consistency_score"] == 0.91
    assert latest["quote_age_sec"] == 1.25
    assert latest["quote_truth_source"] == "live"
    assert latest["native_setup_score"] == 0.62
    assert latest["setup_score"] == 0.62
    assert latest["setup_score_source"] == "native"
    assert latest["setup_regime_alignment_score"] == 0.35
    assert latest["setup_structure_score"] == 0.55
    assert latest["setup_thesis_score"] == 0.62
    assert latest["trigger_score"] == 0.54
    assert latest["trigger_base_score"] == 0.61
    assert latest["entry_quality_score"] == 0.57
    assert latest["entry_invalidation_score"] == 0.66
    assert latest["entry_overextension_score"] == 0.58
    assert latest["entry_timing_quality_score"] == 0.63
    assert latest["execution_quality_score"] == 0.49
    assert latest["rank_score"] == 0.578174
    assert latest["raw_rank_score"] == 0.746802
    assert latest["terminal_rank_score"] == 0.578174
    assert latest["opportunity_score"] == 0.654476
    assert latest["quote_validation_status"] == "OK"
    assert latest["quote_freshness_state"] == "fresh"


def test_reject_shadow_derives_setup_score_from_setup_proxies(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_derived_setup.sqlite"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(logs_root), raising=False)

    event = _base_event("NIFTY", _ts_ist(2026, 5, 4, 14, 13))
    event.update(
        {
            "setup_score": 0.358,
            "quote_validation_status": "OK",
            "quote_age_sec": 1.25,
            "quote_truth_source": "live",
            "quality_detail_source": "derived_from_setup_proxies",
            "quality_detail": {
                "setup_regime_alignment_score": 0.35,
                "setup_structure_score": 0.55,
                "setup_thesis_score": 0.62,
            },
        }
    )

    payload = reject_shadow.record_candidate_decision(event)

    assert payload["status"] == "ok"
    decision_path = logs_root / "desks" / "DEFAULT" / "candidate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = rows[-1]
    assert latest["native_setup_score"] == 0.358
    assert latest["setup_score_source"] == "derived_from_setup_proxies"
    assert latest["setup_score"] == pytest.approx((0.35 + 0.55 + 0.62) / 3.0, rel=1e-6)
    assert latest["quote_age_sec"] == 1.25
    assert latest["quote_truth_source"] == "live"
    assert latest["quote_freshness_state"] == "fresh"


def test_reject_shadow_backfills_nested_liquidity_telemetry(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_nested.sqlite"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(logs_root), raising=False)

    event = _base_event("NIFTY", _ts_ist(2026, 5, 4, 14, 12))
    event.update(
        {
            "score_breakdown": {
                "candidate_quality_score": 0.61,
                "family_consensus_score": 0.47,
                "family_consensus_components": {"regime_alignment": 0.5},
                "family_survival_score": 0.52,
                "family_survival_components": {"setup_score": 0.61},
                "quality_detail": {
                    "setup_regime_alignment_score": 0.35,
                    "setup_structure_score": 0.55,
                    "setup_thesis_score": 0.62,
                    "trigger_base_score": 0.61,
                    "entry_invalidation_score": 0.66,
                    "entry_overextension_score": 0.58,
                    "entry_timing_quality_score": 0.63,
                },
                "liquidity_score": 0.8125,
                "quote_consistency_score": 0.91,
                "setup_score": 0.62,
                "trigger_score": 0.54,
                "entry_quality_score": 0.57,
                "execution_quality_score": 0.49,
                "liquidity_flow_score": 0.74,
                "liquidity_book_score": 0.88,
                "liquidity_spread_score": 0.81,
                "liquidity_volume_score": 0.77,
                "liquidity_oi_score": 0.69,
                "rank_score": 0.578174,
                "raw_rank_score": 0.746802,
                "terminal_rank_score": 0.578174,
                "opportunity_score": 0.654476,
                "quote_validation_status": "OK",
            },
            "source_flags": {
                "candidate_quality_score": 0.61,
                "family_consensus_score": 0.47,
                "family_consensus_components": {"regime_alignment": 0.5},
                "family_survival_score": 0.52,
                "family_survival_components": {"setup_score": 0.61},
                "quality_detail": {
                    "setup_regime_alignment_score": 0.35,
                    "setup_structure_score": 0.55,
                    "setup_thesis_score": 0.62,
                    "trigger_base_score": 0.61,
                    "entry_invalidation_score": 0.66,
                    "entry_overextension_score": 0.58,
                    "entry_timing_quality_score": 0.63,
                },
                "decision_trace": {
                    "candidate_quality_score": 0.61,
                    "family_consensus_score": 0.47,
                    "family_survival_score": 0.52,
                    "setup_score": 0.62,
                    "trigger_score": 0.54,
                    "entry_quality_score": 0.57,
                    "execution_quality_score": 0.49,
                    "liquidity_flow_score": 0.74,
                    "liquidity_book_score": 0.88,
                    "liquidity_spread_score": 0.81,
                    "liquidity_volume_score": 0.77,
                    "liquidity_oi_score": 0.69,
                }
            },
        }
    )

    payload = reject_shadow.record_candidate_decision(event)

    assert payload["status"] == "ok"
    decision_path = logs_root / "desks" / "DEFAULT" / "candidate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = rows[-1]
    assert latest["liquidity_score"] == 0.8125
    assert latest["quote_consistency_score"] == 0.91
    assert latest["setup_score"] == 0.62
    assert latest["setup_regime_alignment_score"] == 0.35
    assert latest["setup_structure_score"] == 0.55
    assert latest["setup_thesis_score"] == 0.62
    assert latest["trigger_score"] == 0.54
    assert latest["trigger_base_score"] == 0.61
    assert latest["entry_quality_score"] == 0.57
    assert latest["entry_invalidation_score"] == 0.66
    assert latest["entry_overextension_score"] == 0.58
    assert latest["entry_timing_quality_score"] == 0.63
    assert latest["execution_quality_score"] == 0.49
    assert latest["liquidity_flow_score"] == 0.74
    assert latest["liquidity_book_score"] == 0.88
    assert latest["liquidity_spread_score"] == 0.81
    assert latest["liquidity_volume_score"] == 0.77
    assert latest["liquidity_oi_score"] == 0.69
    assert latest["candidate_quality_score"] == 0.61
    assert latest["family_consensus_score"] == 0.47
    assert latest["family_consensus_components"] == {"regime_alignment": 0.5}
    assert latest["family_survival_score"] == 0.52
    assert latest["family_survival_components"] == {"setup_score": 0.61}
    assert latest["quality_detail"]["setup_regime_alignment_score"] == 0.35
    assert latest["rank_score"] == 0.578174
    assert latest["raw_rank_score"] == 0.746802
    assert latest["terminal_rank_score"] == 0.578174
    assert latest["opportunity_score"] == 0.654476
    assert latest["quote_validation_status"] == "OK"


def test_reject_shadow_backfills_raw_rank_from_rank_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "shadow_rank.sqlite"
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(reject_shadow, "LOGS_ROOT", str(logs_root), raising=False)

    event = _base_event("NIFTY", _ts_ist(2026, 5, 4, 14, 13))
    event.update(
        {
            "rank_score": 0.578174,
            "terminal_rank_score": 0.578174,
            "opportunity_score": 0.654476,
            "quote_validation_status": "OK",
        }
    )

    payload = reject_shadow.record_candidate_decision(event)

    assert payload["status"] == "ok"
    decision_path = logs_root / "desks" / "DEFAULT" / "candidate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = rows[-1]
    assert latest["rank_score"] == 0.578174
    assert latest["raw_rank_score"] == 0.578174
    assert latest["terminal_rank_score"] == 0.578174
    assert latest["opportunity_score"] == 0.654476
    assert latest["quote_validation_status"] == "OK"
