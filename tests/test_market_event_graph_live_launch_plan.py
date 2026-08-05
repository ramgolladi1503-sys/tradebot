from pathlib import Path

import pytest

from core.market_event_graph_live_launch_plan import (
    BLOCKED_BY_LAUNCH_PLAN_IDENTITY,
    build_launch_plan,
    canonicalize_launch_plan,
    load_launch_plan,
    semantic_sha256,
    verify_frozen_launch_plan,
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


def test_semantic_hash_ignores_generated_quote_value_when_selection_is_stable() -> None:
    first = _plan()
    second = dict(first)
    second["production_resolution"] = [dict(first["production_resolution"][0], ltp=101.25, generated_at="later")]
    assert semantic_sha256(first, "r" * 64) == semantic_sha256(second, "r" * 64)


def test_semantic_hash_changes_for_tokens_modes_interval_and_authority() -> None:
    plan = _plan()
    base = semantic_sha256(plan, "r" * 64)
    changed_token = dict(plan, final_union_tokens=[*plan["final_union_tokens"], 9999])
    changed_mode = dict(plan, subscription_modes={"999": "FULL"})
    changed_interval = dict(plan, interval_seconds=60)
    changed_authority = dict(plan, allowed_for_live_execution=True)
    assert semantic_sha256(changed_token, "r" * 64) != base
    assert semantic_sha256(changed_mode, "r" * 64) != base
    assert semantic_sha256(changed_interval, "r" * 64) != base
    assert semantic_sha256(changed_authority, "r" * 64) != base


def test_semantic_projection_is_insertion_order_independent() -> None:
    plan = _plan()
    reordered = {key: plan[key] for key in reversed(list(plan))}
    assert canonicalize_launch_plan(plan, "r" * 64) == canonicalize_launch_plan(reordered, "r" * 64)


def test_resolver_snapshot_changes_when_selection_changes() -> None:
    first = _plan()
    second = dict(first)
    second["production_resolution"] = [dict(first["production_resolution"][0], option_strikes_selected=[200.0])]
    assert semantic_sha256(first, "a" * 64) != semantic_sha256(second, "b" * 64)


def test_quote_only_resolver_snapshot_change_does_not_change_semantic_hash() -> None:
    plan = _plan()
    assert semantic_sha256(plan, "a" * 64) == semantic_sha256(plan, "b" * 64)


def test_frozen_verifier_rejects_missing_marker_before_feed_use(tmp_path: Path) -> None:
    plan_path = tmp_path / "launch_plan.json"
    write_launch_plan(plan_path, _plan())
    with pytest.raises(ValueError, match="FROZEN_MARKER_MISSING"):
        verify_frozen_launch_plan(
            plan_path,
            expected_semantic_sha256="a" * 64,
            expected_resolver_snapshot_sha256="b" * 64,
            session_date="2026-07-30",
        )
