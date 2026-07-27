from __future__ import annotations

import json
from pathlib import Path


LANES = ("VWAP_RECLAIM", "OPENING_RANGE_BREAKOUT", "OPENING_STATE_MOMENTUM")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_signal_artifacts(repo_root: Path) -> list[dict[str, object]]:
    root = repo_root / "runtime" / "strategy_validation"
    artifacts: list[dict[str, object]] = []
    for lane in LANES:
        lane_dir = root / lane
        report = lane_dir / "candidate_replay_report.json"
        if report.exists():
            data = _load_json(report)
            artifacts.append(
                {
                    "strategy_id": lane,
                    "path": str(report),
                    "kind": "candidate_replay_report",
                    "data_fetch_status": data.get("data_fetch_status"),
                    "certifiable_data": data.get("certifiable_data"),
                    "certification_blockers": data.get("certification_blockers", []),
                    "provenance_count": len(data.get("provenance", []) or []),
                    "fetched_underlying_candles_count": data.get("fetched_underlying_candles_count", 0),
                    "fetched_option_candles_count": data.get("fetched_option_candles_count", 0),
                }
            )
        batch_report = root / "batch_certification_report.json"
        if batch_report.exists():
            for entry in _load_json(batch_report):
                if entry.get("strategy_id") == lane:
                    artifacts.append({"strategy_id": lane, "path": str(batch_report), "kind": "batch_certification_report", "entry": entry})
    historical_ledger = repo_root / "research" / "option_e2e_recertification_v4" / "signal_ledgers_v4_2" / "signal_ledgers.json"
    if historical_ledger.exists():
        for record in _load_json(historical_ledger).get("records", []):
            if record.get("strategy_or_hypothesis_id") in {"Opening-State Momentum", "OPENING_STATE_MOMENTUM"}:
                artifacts.append(
                    {
                        "strategy_id": "OPENING_STATE_MOMENTUM",
                        "path": str(historical_ledger),
                        "kind": "historical_signal_ledger_record",
                        "status": record.get("status"),
                        "blocker": record.get("blocker"),
                        "signal_id": record.get("signal_id"),
                    }
                )
    return artifacts
