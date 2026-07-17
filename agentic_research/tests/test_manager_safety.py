import pytest

from agentic_research.agents import ResearchManager


class UnsafePlanner:
    def choose_next(self, state):
        return "place_order"


def test_manager_rejects_unsafe_planner_output():
    with pytest.raises(ValueError, match="forbidden_action"):
        ResearchManager(UnsafePlanner()).next_action({})
