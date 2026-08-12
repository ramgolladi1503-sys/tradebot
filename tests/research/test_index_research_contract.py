import pytest

from research.governance.index_research_contract import (
    DiscoveryResult,
    ResearchOutcome,
    ResearchSpec,
    run_offline_discovery,
)


def spec(index="BANKNIFTY"):
    return ResearchSpec(index, "next_session_open_gap", "09:14:59", "chronological_dev", "untouched_oos", ("baseline",), ("permutation",), "required")


def test_missing_data_is_blocked_not_zero_or_no_edge():
    result = run_offline_discovery(spec(), dataset=None)
    assert result.outcome is ResearchOutcome.BLOCKED_DATA


def test_discovery_refuses_unfrozen_nonempty_data_execution():
    with pytest.raises(ValueError, match="FROZEN_DATA"):
        run_offline_discovery(spec(), dataset=[{"close": 1}])


def test_qualified_result_requires_all_provenance_bindings():
    with pytest.raises(ValueError, match="PROVENANCE"):
        DiscoveryResult("SENSEX", ResearchOutcome.QUALIFIED).validate()


def test_specs_require_negative_and_multiple_testing_controls():
    with pytest.raises(ValueError, match="MULTIPLE_TESTING"):
        ResearchSpec("SENSEX", "gap", "09:14:59", "dev", "oos", ("x",), ("perm",), "missing").validate()
