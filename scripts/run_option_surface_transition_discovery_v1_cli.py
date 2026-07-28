#!/usr/bin/env python3
"""Stable CLI entrypoint for option-surface transition discovery.

Pandas 3 no longer preserves DataFrame objects through ``numpy.array_split`` in
all contexts. Patch the implementation's walk-forward helper with an explicit
index-based chronological split before invoking the frozen discovery runner.
No mechanism, threshold, partition, outcome, or economic gate is changed.
"""
from __future__ import annotations

import numpy as np

from scripts import run_option_surface_transition_discovery_v1 as implementation


def chronological_walk_forward(values):
    if values.empty:
        return 0, 0
    ordered = values.sort_values(["session_id", "timestamp"]).reset_index(drop=True)
    index_folds = np.array_split(np.arange(len(ordered)), 4)
    folds = [ordered.iloc[index] for index in index_folds if len(index) >= 3]
    positive = sum(float(fold["net_return_pct"].mean()) > 0 for fold in folds)
    return int(positive), int(len(folds))


def main() -> int:
    implementation._walk_forward = chronological_walk_forward
    return implementation.main()


if __name__ == "__main__":
    raise SystemExit(main())
