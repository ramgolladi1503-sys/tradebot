import time
import pytest
from unittest.mock import patch, MagicMock
from core.orchestrator import Orchestrator
from core.orchestrator_parts.data import write_cycle_reports

def test_write_cycle_reports_is_non_blocking():
    start = time.perf_counter()
    with patch("core.orchestrator_parts.data._do_write_cycle_reports") as mock_do:
        def slow_write(*args, **kwargs):
            time.sleep(0.5)
        mock_do.side_effect = slow_write
        
        # This call should return immediately since it's offloaded
        write_cycle_reports(cycle_reason="test", decision_traces=[], config_snapshot={})
        
    end = time.perf_counter()
    assert (end - start) < 0.1, "write_cycle_reports blocked the thread!"

def test_pace_loop_avoids_over_sleeping():
    from core.orchestrator import _pace_loop
    start_time = time.perf_counter()
    with patch("time.sleep") as mock_sleep:
        # If elapsed is larger than poll_interval, it shouldn't sleep
        _pace_loop(0.1, start_time - 0.2)
        mock_sleep.assert_not_called()
        
        # If elapsed is less, it should sleep
        _pace_loop(0.1, start_time)
        mock_sleep.assert_called_once()
