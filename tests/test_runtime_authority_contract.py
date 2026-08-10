import pytest

from core.runtime_authority_contract import (
    AuthorityKind,
    assert_feed_boundary_untouched,
    authority_map_payload,
    build_runtime_authority_map,
    protected_feed_path,
    validate_runtime_authority_map,
)


def test_authority_map_has_one_execution_router():
    stages = build_runtime_authority_map()
    execution = [stage for stage in stages if stage.authority is AuthorityKind.EXECUTION]
    assert [stage.owner_module for stage in execution] == ["core.execution_router"]
    assert [stage.may_call_broker for stage in execution] == [True]
    assert validate_runtime_authority_map(stages) == ()


def test_authority_map_has_one_candidate_selector():
    stages = build_runtime_authority_map()
    selectors = [
        stage for stage in stages
        if stage.authority is AuthorityKind.CANDIDATE_SELECTION
    ]
    assert [stage.owner_module for stage in selectors] == ["core.opportunity_engine"]
    assert [stage.callable_name for stage in selectors] == ["select_best_opportunity"]
    assert [stage.may_call_broker for stage in selectors] == [False]


def test_ui_stages_cannot_call_broker():
    for stage in build_runtime_authority_map():
        if stage.authority is AuthorityKind.UI_ONLY:
            assert stage.may_call_broker is False


def test_feed_paths_are_protected():
    assert protected_feed_path("core/market_data.py")
    assert protected_feed_path("core/kite_depth_ws.py")
    assert protected_feed_path("config/config.py")
    assert not protected_feed_path("core/canonical_execution_decision.py")


def test_feed_boundary_guard_rejects_any_protected_change():
    with pytest.raises(AssertionError, match="feed_boundary_modified"):
        assert_feed_boundary_untouched(
            ["core/canonical_execution_decision.py", "core/market_data.py"]
        )


def test_authority_payload_preserves_non_action_boundary():
    payload = authority_map_payload()
    assert payload["feed_boundary_frozen"] is True
    assert payload["validation_errors"] == []
    assert payload["is_order_action"] is False
