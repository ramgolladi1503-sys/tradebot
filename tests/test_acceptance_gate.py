from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from config import config as cfg
from core.acceptance_gate import evaluate_acceptance_gate


def _seed_outcomes(db_path: Path, rows: list[tuple[float, float]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                trade_id TEXT,
                r_multiple REAL,
                timestamp_epoch REAL
            )
            """
        )
        conn.execute("DELETE FROM outcomes")
        conn.executemany(
            "INSERT INTO outcomes (trade_id, r_multiple, timestamp_epoch) VALUES (?, ?, ?)",
            [(f"T{i}", r, ts) for i, (r, ts) in enumerate(rows)],
        )
        conn.commit()


def _seed_decision_events(db_path: Path, *, rows: int, linked_rows: int, now_epoch: float) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_events (
                trade_id TEXT,
                timestamp_epoch REAL,
                pnl_horizon_15m REAL,
                realized_pnl REAL
            )
            """
        )
        conn.execute("DELETE FROM decision_events")
        payload = []
        for i in range(rows):
            trade_id = f"T{i}"
            pnl = 1.0 if i < linked_rows else None
            payload.append((trade_id, now_epoch - 120.0 - i, pnl, None))
        conn.executemany(
            "INSERT INTO decision_events (trade_id, timestamp_epoch, pnl_horizon_15m, realized_pnl) VALUES (?, ?, ?, ?)",
            payload,
        )
        conn.commit()


def test_acceptance_gate_passes_with_good_outcomes_and_shadow(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db = tmp_path / "trades.db"
    rows = [(0.6 if i % 4 else -0.2, now_epoch - 1000.0 - i * 60.0) for i in range(40)]
    _seed_outcomes(db, rows)

    truth = tmp_path / "truth_dataset.parquet"
    df = pd.DataFrame(
        {
            "champion_proba": [0.60, 0.55, 0.52, 0.49, 0.51, 0.45] * 20,
            "challenger_proba": [0.70, 0.62, 0.57, 0.44, 0.56, 0.38] * 20,
            "pnl_15m": [1, 1, 1, -1, 1, -1] * 20,
        }
    )
    df.to_parquet(truth, index=False)

    monkeypatch.setattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_TRADES", 20, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 20, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_WIN_RATE", 0.45, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_EXPECTANCY_R", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MAX_DRAWDOWN_R", -10.0, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 30, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MAX_SHADOW_BRIER_DELTA", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MAX_SHADOW_ECE_DELTA", 0.05, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_GATE_LATEST_PATH", str(tmp_path / "acceptance_latest.json"), raising=False)

    out = evaluate_acceptance_gate(strict=True, now_epoch=now_epoch, db_path=db, truth_path=truth)
    assert out["status"] == "PASS"
    assert out["ok"] is True
    assert out["outcome_metrics"]["n"] >= 20


def test_acceptance_gate_degraded_when_shadow_missing_non_strict(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db = tmp_path / "trades.db"
    rows = [(0.4, now_epoch - 1000.0 - i * 60.0) for i in range(30)]
    _seed_outcomes(db, rows)
    monkeypatch.setattr(cfg, "ACCEPTANCE_GATE_LATEST_PATH", str(tmp_path / "acceptance_latest.json"), raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 20, raising=False)
    out = evaluate_acceptance_gate(
        strict=False,
        now_epoch=now_epoch,
        db_path=db,
        truth_path=tmp_path / "missing_truth.parquet",
    )
    assert out["status"] == "DEGRADED"
    assert out["ok"] is False


def test_acceptance_gate_fails_when_shadow_missing_strict(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db = tmp_path / "trades.db"
    rows = [(0.4, now_epoch - 1000.0 - i * 60.0) for i in range(30)]
    _seed_outcomes(db, rows)
    monkeypatch.setattr(cfg, "ACCEPTANCE_GATE_LATEST_PATH", str(tmp_path / "acceptance_latest.json"), raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 20, raising=False)
    out = evaluate_acceptance_gate(
        strict=True,
        now_epoch=now_epoch,
        db_path=db,
        truth_path=tmp_path / "missing_truth.parquet",
    )
    assert out["status"] == "FAIL"
    assert out["ok"] is False


def test_acceptance_gate_fails_when_outcome_link_rate_below_threshold(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db = tmp_path / "trades.db"
    rows = [(0.5 if i % 3 else -0.1, now_epoch - 1000.0 - i * 60.0) for i in range(60)]
    _seed_outcomes(db, rows)
    _seed_decision_events(db, rows=120, linked_rows=20, now_epoch=now_epoch)

    truth = tmp_path / "truth_dataset.parquet"
    pd.DataFrame(
        {
            "champion_proba": [0.55, 0.52, 0.48, 0.62] * 40,
            "challenger_proba": [0.56, 0.50, 0.45, 0.61] * 40,
            "pnl_15m": [1, 1, -1, 1] * 40,
        }
    ).to_parquet(truth, index=False)

    monkeypatch.setattr(cfg, "ACCEPTANCE_GATE_LATEST_PATH", str(tmp_path / "acceptance_latest.json"), raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_TRADES", 20, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 20, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 20, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_LINK_RATE", 0.9, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", 10, raising=False)

    out = evaluate_acceptance_gate(strict=True, now_epoch=now_epoch, db_path=db, truth_path=truth)
    assert out["status"] == "FAIL"
    assert "OUTCOME_LINK_RATE_BELOW_THRESHOLD" in list(out["blockers"] or [])
