from pathlib import Path

import pytest

from core.market_event_graph_live_launch_plan import (
    BLOCKED_BY_LAUNCH_PLAN_IDENTITY,
    build_launch_plan,
    load_launch_plan,
    write_launch_plan,
)


def _plan():
    observation_tokens = list(range(1000, 1051))
    return build_launch_plan(
        session_date="2026-07-30",
        production_tokens=[1, 2, 3],
        production_resolution=[{"symbol": "NIFTY", "index_token": 1}],
        sticky_tokens=[3],
        observation_tokens=observation_tokens,
        budget=60,
        master_sha256="a" * 64,
        universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"], "budget": 60},
        broker_metadata_called=False,
    )


def test_launch_plan_is_hash_bound_and_immutable(tmp_path: Path) -> None:
    plan = _plan()
    path = tmp_path / "capture" / "launch_plan.json"

    write_launch_plan(path, plan)

    assert load_launch_plan(path)["launch_plan_sha256"] == plan["launch_plan_sha256"]
    with pytest.raises(FileExistsError):
        write_launch_plan(path, plan)


def test_launch_plan_rejects_modified_identity(tmp_path: Path) -> None:
    plan = _plan()
    path = tmp_path / "launch_plan.json"
    write_launch_plan(path, plan)
    raw = path.read_text(encoding="utf-8").replace('"configured_budget": 60', '"configured_budget": 59')
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match=BLOCKED_BY_LAUNCH_PLAN_IDENTITY):
        load_launch_plan(path)
