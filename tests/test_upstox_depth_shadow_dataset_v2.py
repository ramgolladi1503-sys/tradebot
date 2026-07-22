from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from research.upstox_depth_shadow_capture_v2.dataset_registry import (
    DEVELOPMENT,
    HOLDOUT_UNSEEN,
    update_dataset_registry,
)
from research.upstox_depth_shadow_capture_v2.universe import build_shadow_universe


def _master() -> list[dict]:
    records = [
        {"instrument_key": "NSE_INDEX|Nifty 50", "trading_symbol": "NIFTY 50", "instrument_type": "INDEX"},
        {"instrument_key": "NSE_INDEX|Nifty Bank", "trading_symbol": "NIFTY BANK", "instrument_type": "INDEX"},
        {"instrument_key": "BSE_INDEX|SENSEX", "trading_symbol": "SENSEX", "instrument_type": "INDEX"},
        {"instrument_key": "NSE_INDEX|India VIX", "trading_symbol": "INDIA VIX", "instrument_type": "INDEX"},
    ]
    token = 1000
    for name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        for expiry in ("2026-07-28", "2026-08-04"):
            for option_type in ("CE", "PE"):
                token += 1
                records.append(
                    {
                        "instrument_key": f"NSE_FO|{token}",
                        "name": name,
                        "trading_symbol": f"{name}-{expiry}-{option_type}",
                        "instrument_type": option_type,
                        "expiry": expiry,
                        "strike_price": 25000,
                        "lot_size": 65,
                    }
                )
        for expiry in ("2026-07-30", "2026-08-27", "2026-09-24"):
            token += 1
            records.append(
                {
                    "instrument_key": f"NSE_FO|{token}",
                    "name": name,
                    "trading_symbol": f"{name}-{expiry}-FUT",
                    "instrument_type": "FUT",
                    "expiry": expiry,
                    "lot_size": 65,
                }
            )
    return records


def test_shadow_universe_is_deterministic_and_uses_nearest_options() -> None:
    master = _master()
    first = build_shadow_universe(master, as_of_date=date(2026, 7, 23))
    second = build_shadow_universe(list(reversed(master)), as_of_date=date(2026, 7, 23))
    assert first == second
    assert first["selection_uses_outcomes"] is False
    assert first["execution_allowed"] is False
    option_records = [record for record in first["instruments"] if record["role"].startswith("NEAREST_OPTION")]
    assert option_records
    assert {record["expiry"] for record in option_records} == {"2026-07-28"}
    future_records = [record for record in first["instruments"] if record["role"].startswith("FUTURE")]
    assert {record["expiry"] for record in future_records} == {"2026-07-30", "2026-08-27"}
    assert len(first["instrument_keys"]) == len(set(first["instrument_keys"]))


def test_shadow_universe_fails_closed_when_required_spot_is_missing() -> None:
    master = [record for record in _master() if record.get("trading_symbol") != "INDIA VIX"]
    with pytest.raises(ValueError, match="SPOT:INDIA_VIX"):
        build_shadow_universe(master, as_of_date=date(2026, 7, 23))


def test_shadow_universe_enforces_subscription_limit() -> None:
    with pytest.raises(ValueError, match="limit is 5"):
        build_shadow_universe(
            _master(),
            as_of_date=date(2026, 7, 23),
            maximum_instruments=5,
        )


def _write_readiness(root: Path, session_date: str, classification: str = "SHADOW_DEPTH_SESSION_READY_FOR_DEVELOPMENT") -> None:
    target = root / session_date
    target.mkdir(parents=True, exist_ok=True)
    (target / "readiness.json").write_text(
        json.dumps(
            {
                "classification": classification,
                "session_date": session_date,
                "execution_allowed": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_dataset_registry_freezes_first_development_then_unseen_holdout(tmp_path: Path) -> None:
    for session_date in ("20260701", "20260702", "20260703", "20260704"):
        _write_readiness(tmp_path, session_date)
    registry = update_dataset_registry(tmp_path, development_target=2, holdout_target=2)
    assignments = {item["session_date"]: item["split"] for item in registry["assignments"]}
    assert assignments == {
        "20260701": DEVELOPMENT,
        "20260702": DEVELOPMENT,
        "20260703": HOLDOUT_UNSEEN,
        "20260704": HOLDOUT_UNSEEN,
    }
    assert registry["classification"] == "DATASET_ACQUISITION_COMPLETE_CANDIDATE_FREEZE_REQUIRED"
    assert registry["holdout_use_for_discovery_allowed"] is False
    assert registry["assignment_mutation_allowed"] is False


def test_existing_assignments_do_not_change_when_an_earlier_session_arrives_late(tmp_path: Path) -> None:
    _write_readiness(tmp_path, "20260702")
    _write_readiness(tmp_path, "20260703")
    first = update_dataset_registry(tmp_path, development_target=1, holdout_target=2)
    first_assignments = {item["session_date"]: item["split"] for item in first["assignments"]}
    assert first_assignments == {"20260702": DEVELOPMENT, "20260703": HOLDOUT_UNSEEN}

    _write_readiness(tmp_path, "20260701")
    second = update_dataset_registry(tmp_path, development_target=1, holdout_target=2)
    second_assignments = {item["session_date"]: item["split"] for item in second["assignments"]}
    assert second_assignments["20260702"] == DEVELOPMENT
    assert second_assignments["20260703"] == HOLDOUT_UNSEEN
    assert second_assignments["20260701"] == HOLDOUT_UNSEEN


def test_registry_rejects_disappearing_or_invalidated_assigned_session(tmp_path: Path) -> None:
    _write_readiness(tmp_path, "20260701")
    update_dataset_registry(tmp_path, development_target=1, holdout_target=1)
    _write_readiness(tmp_path, "20260701", classification="SHADOW_DEPTH_SESSION_NOT_READY")
    with pytest.raises(ValueError, match="previously assigned sessions"):
        update_dataset_registry(tmp_path, development_target=1, holdout_target=1)
