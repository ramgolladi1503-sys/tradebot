from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from config import config as cfg
from core.blocked_tracker import BlockedTradeTracker
from core.outcome_labels import attach_candidate_outcome_labels, attach_trade_outcome_labels
from core import trade_store
from core.trade_logger import update_trade_outcome


def test_candidate_outcome_scenarios_map_to_expected_labels():
    blocked_win = attach_candidate_outcome_labels(
        {
            "permission": "BLOCK",
            "execution_status": "blocked",
            "outcome": "target",
        }
    )
    skipped = attach_candidate_outcome_labels(
        {
            "allocation_reason": "deferred_slot_cap",
            "outcome": "no_hit",
        }
    )
    later_exec = attach_candidate_outcome_labels(
        {
            "execution_status": "advisory_only",
            "became_executable_later": True,
            "later_execution_status": "executable",
        }
    )

    assert blocked_win["candidate_outcome_label"] == "blocked_falsely"
    assert skipped["candidate_outcome_label"] == "skipped_by_allocator"
    assert later_exec["candidate_outcome_label"] == "non_executable_then_executable_later"


def test_missing_optional_data_yields_safe_fallback_labeling():
    candidate = attach_candidate_outcome_labels(
        {
            "permission": "ADVISORY_ONLY",
            "readiness": "ADVISORY_ONLY",
            "execution_status": "advisory_only",
        }
    )
    trade = attach_trade_outcome_labels({"exit_reason": "UNKNOWN"})

    assert candidate["candidate_outcome_label"] == "advisory_only_never_became_executable"
    assert candidate["candidate_outcome_label_provenance"]["rule"] == "non_executable_no_terminal_outcome"
    assert trade["trade_outcome_label"] == "adverse_excursion"
    assert trade["trade_outcome_label_provenance"]["scope"] == "trade"


def test_labels_attach_to_skipped_and_executed_opportunities(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / "data"), raising=False)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", str(Path(cfg.LOGS_ROOT) / "trade_log.jsonl"), raising=False)
    monkeypatch.setattr(cfg, "OUTCOME_LABEL_POOR_FILL_QUALITY_RISK_FRACTION", 0.4, raising=False)
    monkeypatch.setattr(cfg, "OUTCOME_LABEL_THESIS_INVALIDATED_SECONDS", 900.0, raising=False)
    Path(cfg.DATA_ROOT).mkdir(parents=True, exist_ok=True)
    Path(cfg.LOGS_ROOT).mkdir(parents=True, exist_ok=True)

    trade_store.insert_trade(
        {
            "trade_id": "T-LABEL-1",
            "timestamp": "2026-02-10T10:00:00Z",
            "symbol": "NIFTY",
            "underlying": "NIFTY",
            "instrument": "OPT",
            "instrument_type": "OPT",
            "instrument_token": 123,
            "strike": 22000,
            "expiry": "2026-02-14",
            "option_type": "CE",
            "right": "CE",
            "instrument_id": "NIFTY|2026-02-14|22000|CE",
            "side": "BUY",
            "entry": 100.0,
            "stop_loss": 90.0,
            "target": 130.0,
            "qty": 1,
            "qty_lots": 1,
            "qty_units": 50,
            "validity_sec": 180,
            "confidence": 0.8,
            "strategy": "SCALP",
            "regime": "TREND",
        }
    )
    Path(cfg.TRADE_LOG_PATH).write_text(
        json.dumps(
            {
                "trade_id": "T-LABEL-1",
                "timestamp": "2026-02-10T10:00:00Z",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "side": "BUY",
                "entry": 100.0,
                "stop_loss": 90.0,
                "target": 130.0,
                "qty": 1,
                "qty_units": 50,
                "strategy": "SCALP",
                "fill_price": 108.0,
                "slippage": 8.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    updated_row = update_trade_outcome("T-LABEL-1", 99.0, 0, exit_reason="STOP")

    assert updated_row is not None
    assert updated_row["trade_outcome_label"] == "poor_fill_quality"
    assert updated_row["trade_outcome_label_provenance"]["rule"] == "adverse_fill_vs_reference"

    blocked = BlockedTradeTracker()._finalize(
        {
            "blocked_id": "B-1",
            "symbol": "NIFTY",
            "strike": 22000,
            "type": "CE",
            "reason": "REGIME_BLOCK",
            "entry": 100.0,
            "exit": 120.0,
            "mfe": 20.0,
            "mae": -2.0,
            "atr": 10.0,
        },
        outcome="TARGET_HIT",
    )
    assert blocked["candidate_outcome_label"] == "blocked_falsely"

    con = sqlite3.connect(str(db_path))
    outcome = con.execute(
        """
        SELECT realized_pnl, outcome_label, exit_reason
        FROM outcomes
        WHERE trade_id='T-LABEL-1'
        ORDER BY rowid DESC
        LIMIT 1
        """
    ).fetchone()
    con.close()
    assert outcome is not None
