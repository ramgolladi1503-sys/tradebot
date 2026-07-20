from __future__ import annotations

import pytest

from research.opening_range_retest_edge_screen_v1.controls import CONTROL_CASES, run_control_case


@pytest.mark.parametrize("name, _mutator, _expected", CONTROL_CASES)
def test_orb_edge_screen_negative_control(name, _mutator, _expected) -> None:
    result = run_control_case(name)
    assert result["passed"], result

