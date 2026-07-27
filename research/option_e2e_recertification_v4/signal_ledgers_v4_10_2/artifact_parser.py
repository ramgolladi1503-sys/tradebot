from __future__ import annotations

import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_vwap_artifacts(repo_root: Path) -> dict[str, list[dict[str, object]]]:
    repo_root = repo_root.resolve()
    runtime_dir = repo_root / "runtime" / "strategy_validation" / "VWAP_RECLAIM"
    legacy_option_replay_audit_records: list[dict[str, object]] = []
    for name in ("candidate_replay_report.json", "phase_4_report.json"):
        path = runtime_dir / name
        if not path.exists():
            continue
        payload = _load_json(path)
        legacy_option_replay_audit_records.append(
            {
                "semantic_path": f"runtime/strategy_validation/VWAP_RECLAIM/{name}",
                "artifact_type": name.removesuffix(".json"),
                "evidence_domain": "OPTION_REPLAY_AUDIT_ONLY",
                "active_for_signal_truth": False,
                "strategy_id": payload.get("strategy_id"),
                "data_fetch_attempted": payload.get("data_fetch_attempted"),
                "data_fetch_status": payload.get("data_fetch_status"),
                "provenance_count": len(payload.get("provenance", []) or []),
                "fetched_underlying_candles_count": payload.get("fetched_underlying_candles_count", 0),
                "fetched_option_candles_count": payload.get("fetched_option_candles_count", 0),
                "blockers": payload.get("certification_blockers") or payload.get("blockers", []),
            }
        )

    invalidated_historical_records: list[dict[str, object]] = []
    ledger_path = (
        repo_root
        / "research"
        / "option_e2e_recertification_v4"
        / "signal_ledgers_v4_2"
        / "signal_ledgers.json"
    )
    if ledger_path.exists():
        for record in _load_json(ledger_path).get("records", []):
            if record.get("strategy_or_hypothesis_id") != "Opening-State Momentum":
                continue
            invalidated_historical_records.append(
                {
                    "semantic_path": "research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json",
                    "artifact_type": "historical_signal_ledger_record",
                    "evidence_domain": "INVALIDATED_HISTORICAL_RECORD",
                    "active_for_signal_truth": False,
                    "strategy_or_hypothesis_id": record.get("strategy_or_hypothesis_id"),
                    "signal_id": record.get("signal_id"),
                    "status": record.get("status"),
                    "blocker": record.get("blocker"),
                    "invalidated": True,
                }
            )
    return {
        "legacy_option_replay_audit_records": legacy_option_replay_audit_records,
        "invalidated_historical_records": invalidated_historical_records,
    }
