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


def test_launch_plan_hash_binds_optional_heritage_manifest(tmp_path: Path) -> None:
    plan = build_launch_plan(
        session_date="2026-07-30",
        production_tokens=[1, 2, 3],
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
        sticky_tokens=[3], observation_tokens=list(range(1000, 1051)), budget=60,
        master_sha256="a" * 64, universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"]}, broker_metadata_called=False,
        heritage_manifest_path="/approved/sessions/heritage.json",
        heritage_manifest_sha256="c" * 64,
    )
    path = tmp_path / "launch_plan.json"
    write_launch_plan(path, plan)

    assert load_launch_plan(path)["heritage_manifest_sha256"] == "c" * 64
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["heritage_manifest_sha256"] = "d" * 64
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match=BLOCKED_BY_LAUNCH_PLAN_IDENTITY):
        load_launch_plan(path)


def test_launch_plan_loader_accepts_legacy_plan_without_heritage_fields(tmp_path: Path) -> None:
    plan = _plan()
    plan.pop("heritage_manifest_path")
    plan.pop("heritage_manifest_sha256")
    plan.pop("t1_manifest_reference_status")
    plan["schema_version"] = 1
    basis = {
        key: plan[key]
        for key in (
            "schema_version", "session_date", "production_tokens", "production_underlying_tokens",
            "production_option_tokens", "production_sticky_tokens", "observation_tokens", "overlap_tokens",
            "observation_exclusive_tokens", "final_union_tokens", "configured_budget",
            "missing_observation_tokens", "production_resolution", "master_sha256", "universe_sha256",
            "configuration_fingerprint", "broker_metadata_called",
        )
    }
    from core.market_event_graph_live_launch_plan import _sha
    plan["launch_plan_sha256"] = _sha(basis)
    path = tmp_path / "launch_plan.json"
    path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")

    loaded = load_launch_plan(path)

    assert loaded["schema_version"] == 1
    assert "heritage_manifest_path" not in loaded
    assert "heritage_manifest_sha256" not in loaded


def test_schema_v3_rejects_legacy_t1_status_alias(tmp_path: Path) -> None:
    plan = _plan()
    assert plan["schema_version"] == 3
    path = tmp_path / "launch_plan.json"
    raw = dict(plan)
    raw["t1_prerequisite_status"] = raw.pop("t1_manifest_reference_status")
    from core.market_event_graph_live_launch_plan import _sha
    basis_keys = (
        "schema_version", "session_date", "production_tokens", "production_underlying_tokens",
        "production_option_tokens", "production_sticky_tokens", "observation_tokens", "overlap_tokens",
        "observation_exclusive_tokens", "final_union_tokens", "configured_budget",
        "missing_observation_tokens", "production_resolution", "master_sha256", "universe_sha256",
        "configuration_fingerprint", "broker_metadata_called", "heritage_manifest_path",
        "heritage_manifest_sha256", "t1_prerequisite_status", "venue", "calendar_id",
        "calendar_version", "selected_futures_contract_key", "target_expiry",
    )
    raw["launch_plan_sha256"] = _sha({key: raw[key] for key in basis_keys})
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match=BLOCKED_BY_LAUNCH_PLAN_IDENTITY):
        load_launch_plan(path)


@pytest.mark.parametrize("schema_version", [True, "2", 99])
def test_launch_plan_rejects_noncanonical_schema_version(tmp_path: Path, schema_version) -> None:
    plan = dict(_plan())
    plan["schema_version"] = schema_version
    path = tmp_path / "launch_plan.json"
    path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match=BLOCKED_BY_LAUNCH_PLAN_IDENTITY):
        load_launch_plan(path)


@pytest.mark.parametrize(
    ("path_value", "sha_value"),
    [("/approved/sessions/heritage.json", None), (None, "c" * 64), ("/x", "invalid"), ("", "c" * 64)],
)
def test_launch_plan_rejects_partial_or_invalid_heritage_binding(path_value, sha_value):
    plan = build_launch_plan(
        session_date="2026-07-30", production_tokens=[1, 2, 3],
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
        sticky_tokens=[3], observation_tokens=list(range(1000, 1051)), budget=60,
        master_sha256="a" * 64, universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"]}, broker_metadata_called=False,
        heritage_manifest_path=path_value, heritage_manifest_sha256=sha_value,
    )
    assert plan["ok"] is False
    assert plan["allowed_for_live_execution"] is False


def test_partial_heritage_binding_cannot_create_passing_plan():
    plan = build_launch_plan(
        session_date="2026-07-30", production_tokens=[1, 2, 3],
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
        sticky_tokens=[3], observation_tokens=list(range(1000, 1051)), budget=60,
        master_sha256="a" * 64, universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"]}, broker_metadata_called=False,
        heritage_manifest_path="/approved/sessions/heritage.json",
        heritage_manifest_sha256=None,
    )

    assert plan["ok"] is False
    assert plan["verdict"] == "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
    assert plan["allowed_for_live_execution"] is False


def test_launch_plan_distinguishes_meg_readiness_from_t1_strategy_readiness():
    plan = _plan()

    assert plan["ok"] is True
    assert plan["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert plan["t1_manifest_reference_status"] == "BLOCKED_HERITAGE_MANIFEST_UNCONFIGURED"
    assert plan["allowed_for_live_execution"] is False


def test_launch_plan_labels_manifest_reference_configured_but_unverified():
    plan = build_launch_plan(
        session_date="2026-07-30", production_tokens=[1, 2, 3],
        production_resolution=[{
            "symbol": "NIFTY", "index_token": 1, "tokens": [1, 2],
            "option_count": 1, "final_option_count": 1, "option_min_required": 1,
        }],
        sticky_tokens=[3], observation_tokens=list(range(1000, 1051)), budget=60,
        master_sha256="a" * 64, universe_sha256="b" * 64,
        configuration={"symbols": ["NIFTY"]}, broker_metadata_called=False,
        heritage_manifest_path="/approved/sessions/heritage.json",
        heritage_manifest_sha256="c" * 64,
    )

    assert plan["ok"] is True
    assert plan["t1_manifest_reference_status"] == "HERITAGE_MANIFEST_REFERENCE_CONFIGURED_UNVERIFIED"


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
