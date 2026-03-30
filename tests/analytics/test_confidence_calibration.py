from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest

from config import config as cfg
from core.analytics.confidence_calibration import (
    build_confidence_calibration_report,
    calibrate_confidence,
    load_latest_confidence_calibration_report,
)
from core.analytics.schema import TradeIntentEvent, TradeOutcome


def _ts_ms(hour: int, minute: int) -> int:
    dt = datetime.fromisoformat(f"2026-02-27T{hour:02d}:{minute:02d}:00+05:30").astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def test_build_confidence_calibration_report_smoke(tmp_path: Path):
    events = [
        TradeIntentEvent(
            trade_key="NIFTY|2026-03-05|22500|CE|BUY|a",
            event_id="evt_cal_1",
            intent="accepted",
            ts_epoch_ms=_ts_ms(10, 0),
            symbol="NIFTY",
            source="unit",
            metrics_snapshot={"predicted_confidence": 0.8, "predicted_confidence_source": "confidence_raw_canonical"},
        ),
        TradeIntentEvent(
            trade_key="NIFTY|2026-03-05|22600|CE|BUY|b",
            event_id="evt_cal_2",
            intent="accepted",
            ts_epoch_ms=_ts_ms(10, 5),
            symbol="NIFTY",
            source="unit",
            metrics_snapshot={"predicted_confidence": 0.7, "predicted_confidence_source": "confidence_raw_canonical"},
        ),
        TradeIntentEvent(
            trade_key="NIFTY|2026-03-05|22400|PE|BUY|c",
            event_id="evt_cal_3",
            intent="accepted",
            ts_epoch_ms=_ts_ms(10, 10),
            symbol="NIFTY",
            source="unit",
            metrics_snapshot={"predicted_confidence": 0.2, "predicted_confidence_source": "confidence_raw_canonical"},
        ),
        TradeIntentEvent(
            trade_key="NIFTY|2026-03-05|22300|PE|BUY|d",
            event_id="evt_cal_4",
            intent="accepted",
            ts_epoch_ms=_ts_ms(10, 15),
            symbol="NIFTY",
            source="unit",
            metrics_snapshot={"predicted_confidence": 0.1, "predicted_confidence_source": "confidence_raw_canonical"},
        ),
    ]
    outcomes = [
        TradeOutcome(
            trade_key=events[0].trade_key,
            event_id=events[0].event_id,
            outcome="hit_target",
            ts_epoch_ms=_ts_ms(10, 30),
            symbol="NIFTY",
            exec_feasible=True,
            source="unit",
        ),
        TradeOutcome(
            trade_key=events[1].trade_key,
            event_id=events[1].event_id,
            outcome="hit_target",
            ts_epoch_ms=_ts_ms(10, 35),
            symbol="NIFTY",
            exec_feasible=True,
            source="unit",
        ),
        TradeOutcome(
            trade_key=events[2].trade_key,
            event_id=events[2].event_id,
            outcome="hit_sl",
            ts_epoch_ms=_ts_ms(10, 40),
            symbol="NIFTY",
            exec_feasible=True,
            source="unit",
        ),
        TradeOutcome(
            trade_key=events[3].trade_key,
            event_id=events[3].event_id,
            outcome="no_hit",
            ts_epoch_ms=_ts_ms(10, 45),
            symbol="NIFTY",
            exec_feasible=True,
            source="unit",
        ),
    ]

    report = build_confidence_calibration_report(
        "2026-02-27",
        events=events,
        outcomes=outcomes,
        bins=2,
        min_rows=1,
        min_bin_count=1,
        output_path=tmp_path / "confidence_calibration.json",
    )

    assert report["counts"]["matched_rows"] == 4
    assert report["calibration"]["eligible"] is True
    assert report["calibration"]["brier_score_raw"] == pytest.approx(0.045)
    assert report["calibration"]["brier_score_calibrated_in_sample"] == pytest.approx(0.0)
    assert len(report["calibration"]["reliability_curve"]) == 2
    assert report["samples"][0]["confidence_calibrated"] == 1.0
    assert report["samples"][2]["confidence_calibrated"] == 0.0
    assert (tmp_path / "confidence_calibration.json").exists()


def test_calibrate_confidence_falls_back_when_bin_too_sparse():
    reliability = [
        {"bin_low": 0.0, "bin_high": 0.5, "count": 1, "avg_conf": 0.2, "win_rate": 0.0},
        {"bin_low": 0.5, "bin_high": 1.0, "count": 10, "avg_conf": 0.8, "win_rate": 0.7},
    ]

    assert calibrate_confidence(0.2, reliability, min_bin_count=3) == 0.2
    assert calibrate_confidence(0.8, reliability, min_bin_count=3) == 0.7


def test_load_latest_confidence_calibration_report_prefers_latest_eligible(monkeypatch, tmp_path: Path):
    latest_dir = tmp_path / "2026-03-29"
    latest_dir.mkdir(parents=True)
    (latest_dir / "confidence_calibration.json").write_text(
        """{"date":"2026-03-29","calibration":{"eligible":true,"reliability_curve":[{"bin_low":0.0,"bin_high":1.0,"count":10,"avg_conf":0.5,"win_rate":0.6}]}}""",
        encoding="utf-8",
    )
    older_dir = tmp_path / "2026-03-28"
    older_dir.mkdir(parents=True)
    (older_dir / "confidence_calibration.json").write_text(
        """{"date":"2026-03-28","calibration":{"eligible":false,"reliability_curve":[{"bin_low":0.0,"bin_high":1.0,"count":10,"avg_conf":0.5,"win_rate":0.4}]}}""",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "CONFIDENCE_CALIBRATION_REPORT_DIR", str(tmp_path), raising=False)

    payload = load_latest_confidence_calibration_report(require_eligible=True)

    assert payload is not None
    assert payload["date"] == "2026-03-29"
    assert payload["calibration"]["eligible"] is True
