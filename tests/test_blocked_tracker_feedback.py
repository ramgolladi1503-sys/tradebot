import json

from config import config as cfg
from core.blocked_tracker import BlockedTradeTracker


class _PredictorStub:
    def __init__(self):
        self.calls = []

    def update_model_online(self, df, target_col="actual"):
        self.calls.append((len(df), target_col))


def test_capture_from_log_reads_desk_blocked_candidates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    desk_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    desk_dir.mkdir(parents=True, exist_ok=True)
    blocked_path = desk_dir / "blocked_candidates.jsonl"
    blocked_path.write_text(
        json.dumps(
            {
                "trade_id": "BLK-1",
                "timestamp": "2026-02-24T09:20:00+05:30",
                "symbol": "NIFTY",
                "strike": 24000,
                "type": "CE",
                "reason": "REGIME_BLOCK",
                "ltp": 100.0,
                "stop": 90.0,
                "target": 120.0,
                "atr": 10.0,
            }
        )
        + "\n"
    )
    track_path = tmp_path / "runtime" / "logs" / "blocked_tracking.jsonl"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_dir), raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRACK_PATH", str(track_path), raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRACK_POLL_SEC", 0, raising=False)

    tracker = BlockedTradeTracker()
    tracker.capture_from_log()

    assert track_path.exists()
    rows = [json.loads(line) for line in track_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "NIFTY"


def test_update_trains_from_suggestion_eval_once_per_new_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    suggestion_eval = tmp_path / "runtime" / "logs" / "suggestion_eval.jsonl"
    suggestion_eval.parent.mkdir(parents=True, exist_ok=True)
    suggestion_eval.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-02-24 10:00:00",
                        "trade_id": "SUG-1",
                        "symbol": "NIFTY",
                        "strike": 24000,
                        "opt_type": "CE",
                        "ltp": 120.0,
                        "outcome": "target",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-02-24 10:01:00",
                        "trade_id": "SUG-2",
                        "symbol": "NIFTY",
                        "strike": 24050,
                        "opt_type": "PE",
                        "ltp": 90.0,
                        "outcome": "stop",
                    }
                ),
            ]
        )
        + "\n"
    )

    monkeypatch.setattr(cfg, "SUGGESTION_EVAL_LOG_PATH", str(suggestion_eval), raising=False)
    monkeypatch.setattr(cfg, "FEEDBACK_TRAIN_STATE_PATH", str(tmp_path / "runtime" / "logs" / "feedback_state.json"), raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRACK_PATH", str(tmp_path / "runtime" / "logs" / "blocked_tracking.jsonl"), raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRAIN_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_TRAIN_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "SUGGESTION_TRAIN_MIN", 2, raising=False)
    monkeypatch.setattr(cfg, "BLOCKED_TRAIN_WINDOW", 100, raising=False)

    predictor = _PredictorStub()
    tracker = BlockedTradeTracker()

    tracker.update(predictor=predictor)
    first_calls = list(predictor.calls)
    tracker.update(predictor=predictor)

    assert first_calls == [(2, "actual")]
    assert predictor.calls == first_calls
