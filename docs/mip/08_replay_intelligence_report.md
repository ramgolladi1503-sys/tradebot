# Agent 8 Report: Replay Intelligence

## Objective
To act as the sole authority on whether an extracted Intelligence event is allowed to influence trading ranking or execution parameters. This is done via offline, data-backed replay.

## Core Rules

1. **Never Assume Impact**: A headline like "RBI Hikes Rates" cannot default to "increase risk". It must be measured.
2. **Measurement Rigor**: The `IntelligenceReplayEngine` (`core/intelligence/replay/intelligence_replay.py`) demands:
   - `min_sample_size`: At least 30 historical occurrences to even attempt calibration.
   - `date_range`: Explicit measurement windows.
   - `confidence_interval`: E.g., showing a 95% confidence that slippage increases by 10-15%.
3. **Fail to Uncalibrated**: If there are only 5 historical SEBI circulars of a specific type, the engine actively refuses to calibrate. The event is emitted downstream strictly as `UNCALIBRATED`, thereby triggering the `__post_init__` block in `Factor` that locks out `ranking_influence_allowed = False`.

## Application
Scripts like `run_intelligence_replay.py` will be run periodically offline to update the static factor configurations. The live system does not run live calibrations. It strictly reads the pre-computed offline proofs.
