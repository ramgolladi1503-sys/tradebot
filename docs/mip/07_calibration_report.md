# Agent 7 Report: Calibration Infrastructure

## Objective
To eliminate arbitrary scoring (e.g., `score += 0.2`, `high_probability`), the system replaces generic strings/floats with a strict `Factor` breakdown mapping to explicit calibration models.

## Implementation Details

### Calibration Status Model (`factors.py`)
Each piece of intelligence context must be framed as a `Factor`. A `Factor` requires:
- `name` and `unit` (e.g., "Source Freshness", "Seconds")
- `measurement_method`
- `evidence_pointer`
- `calibration_status` (`CALIBRATED` or `UNCALIBRATED`)

### The Immutable Rule
The `__post_init__` method of the `Factor` dataclass explicitly intercepts and enforces the following:
```python
if self.calibration_status != CalibrationStatus.CALIBRATED:
    self.execution_influence_allowed = False
    self.ranking_influence_allowed = False
```
This forces all new intelligence into a purely **advisory** state unless a formal Replay Calibration proof exists to mark it otherwise.

### Relevance Model (`relevance_model.py`)
Groups factors together into a single contextual payload for an event. It strictly evaluates permissions, ensuring that if even one uncalibrated or restricted factor is present, the entire context cannot elevate the candidate's execution or ranking permissions.

## Anti-Heuristic Compliance
- No arbitrary `.score` property exists.
- "Confidence" is isolated to parsing confidence, not trading probability.
- Any trading impact is gated behind `replay-calibrated forward volatility impact` constraints.
