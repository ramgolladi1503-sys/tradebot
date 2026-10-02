import json
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
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_for_live_execution", True),
        ("append", True),
        ("production_underlying_count", 999),
        ("verdict", "PASS_LIVE_SOURCE_PRESESSION_READINESS_WITH_UNVERIFIED_OUTPUT"),
    ],
)
def test_launch_plan_loader_rejects_unhashed_readiness_metadata(tmp_path: Path, field, value) -> None:
    plan = _plan()
    path = tmp_path / "launch_plan.json"
    write_launch_plan(path, plan)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[field] = value
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match=BLOCKED_BY_LAUNCH_PLAN_IDENTITY):
        load_launch_plan(path)


def test_launch_plan_rejects_unowned_flat_production_options() -> None:
    plan = build_launch_plan(
        session_date="2026-07-30",
        production_tokens=[1, 201],
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1],
            "option_count": 0, "final_option_count": 0, "option_min_required": 12,
        }],
        sticky_tokens=[],
        observation_tokens=list(range(1000, 1051)),
        budget=60,
        master_sha256="a" * 64,
        universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"]},
        broker_metadata_called=False,
    )

    assert plan["ok"] is False
    assert plan["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
    assert plan["allowed_for_live_execution"] is False


def test_launch_plan_keeps_sparse_rows_and_sticky_tokens_disjoint(tmp_path: Path) -> None:
    plan = build_launch_plan(
        session_date="2026-07-30",
        production_tokens=[101, 102, 201, 301],
        production_resolution=[
            {
                "symbol": "NIFTY", "index_token": 101, "tokens": [101, 201],
                "option_count": 1, "final_option_count": 1, "option_min_required": 2,
            },
            {
                "symbol": "BANKNIFTY", "index_token": 102, "tokens": [102],
                "option_count": 0, "final_option_count": 0, "option_min_required": 2,
            },
        ],
        sticky_tokens=[301],
        observation_tokens=list(range(1000, 1051)),
        budget=60,
        master_sha256="a" * 64,
        universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY", "BANKNIFTY"]},
        broker_metadata_called=False,
    )
    path = tmp_path / "launch_plan.json"
    write_launch_plan(path, plan)

    assert plan["ok"] is True
    assert plan["production_underlying_tokens"] == [101, 102]
    assert plan["production_option_tokens"] == [201]
    assert plan["production_sticky_tokens"] == [301]
    assert load_launch_plan(path)["production_option_count"] == 1


def test_launch_plan_rejects_duplicate_token_ownership() -> None:
    plan = build_launch_plan(
        session_date="2026-07-30",
        production_tokens=[1, 2],
        production_resolution=[
            {
                "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
                "option_count": 1, "final_option_count": 1, "option_min_required": 1,
            },
            {
                "symbol": "BANKNIFTY", "index_token": 2, "tokens": [2],
                "option_count": 0, "final_option_count": 0, "option_min_required": 1,
            },
        ],
        sticky_tokens=[],
        observation_tokens=list(range(1000, 1051)),
        budget=60,
        master_sha256="a" * 64,
        universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY", "BANKNIFTY"]},
        broker_metadata_called=False,
    )

    assert plan["ok"] is False
    assert plan["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_tokens", [1, None]),
        ("observation_tokens", [*range(1000, 1050), "invalid"]),
        ("sticky_tokens", [True]),
    ],
)
def test_builder_returns_blocked_plan_for_malformed_token_arrays(field, value) -> None:
    kwargs = {
        "session_date": "2026-07-30",
        "production_tokens": [1, 2],
        "production_resolution": [{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
        "sticky_tokens": [],
        "observation_tokens": list(range(1000, 1051)),
        "budget": 60,
        "master_sha256": "a" * 64,
        "universe_sha256": "b" * 64,
        "configuration": {"symbols": ["NIFTY"]},
        "broker_metadata_called": False,
    }
    kwargs[field] = value

    plan = build_launch_plan(**kwargs)

    assert plan["ok"] is False
    assert plan["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
    assert plan["allowed_for_live_execution"] is False
