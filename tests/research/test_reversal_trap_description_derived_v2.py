from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(os.environ.get("REVERSAL_V2_SCRIPT", Path(__file__).with_name("run_reversal_trap_description_derived_v2.py")))
spec = importlib.util.spec_from_file_location("reversal_v2", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def arrays(rows):
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close", "basis", "atr", "rsi", "session"])
    return tuple(frame[column].to_numpy(dtype=np.float64 if column != "session" else np.int32) for column in frame.columns)


def test_next_bar_entry_and_session_exit_without_time_stop():
    rows = [
        (100, 101, 94, 95, 100, 2, 20, 0),
        (97, 99, 96, 98, 100, 2, 30, 0),
        (98, 99, 97, 98.5, 100, 2, 35, 0),
        (98.5, 99, 97.5, 98.2, 100, 2, 40, 0),
    ]
    op, hi, lo, cl, basis, atr, rsi, sess = arrays(rows)
    result = module.simulate_candidate(op, hi, lo, cl, basis, atr, rsi, sess, 2.0, 10, 0, 0, 0, 0, 5.0)
    signal, entry, exit_, *_ = result
    assert signal.tolist() == [1]
    assert entry.tolist() == [2]
    assert exit_.tolist() == [3]


def test_same_bar_ambiguity_resolves_to_stop_first():
    rows = [
        (100, 101, 94, 95, 100, 2, 20, 0),
        (97, 99, 96, 98, 100, 2, 30, 0),
        (98, 103, 91, 99, 100, 2, 35, 0),
    ]
    op, hi, lo, cl, basis, atr, rsi, sess = arrays(rows)
    result = module.simulate_candidate(op, hi, lo, cl, basis, atr, rsi, sess, 2.0, 10, 0, 0, 0, 0, 5.0)
    reason = result[-1]
    assert reason.tolist() == [2]


def test_first_outside_and_recent_outside_have_different_expiry():
    rows = [
        (100, 101, 94, 95, 100, 2, 20, 0),
        (95, 96, 93, 94, 100, 2, 20, 0),
        (94, 95, 92, 93, 100, 2, 20, 0),
        (97, 99, 96, 98, 100, 2, 30, 0),
        (98, 99, 97, 98, 100, 2, 35, 0),
    ]
    op, hi, lo, cl, basis, atr, rsi, sess = arrays(rows)
    first = module.simulate_candidate(op, hi, lo, cl, basis, atr, rsi, sess, 2.0, 2, 0, 0, 0, 0, 5.0)
    recent = module.simulate_candidate(op, hi, lo, cl, basis, atr, rsi, sess, 2.0, 2, 0, 0, 1, 0, 5.0)
    assert len(first[0]) == 0
    assert recent[0].tolist() == [3]


def test_wick_rejection_requires_close_back_inside():
    rows = [
        (100, 101, 95, 98, 100, 2, 30, 0),
        (98, 100, 97, 99, 100, 2, 35, 0),
    ]
    op, hi, lo, cl, basis, atr, rsi, sess = arrays(rows)
    result = module.simulate_candidate(op, hi, lo, cl, basis, atr, rsi, sess, 2.0, 10, 2, 0, 0, 0, 5.0)
    assert result[0].tolist() == [0]
    assert result[1].tolist() == [1]
