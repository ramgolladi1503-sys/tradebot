# ML Confidence Telemetry Truth Report

## Exact Field Definitions
* `ml_model_raw_proba`: The raw output probability directly from the XGBoost/Deep model before any execution/quality decays are applied.
* `ml_pre_quality_proba`: The model probability after initial adjustments (like base penalties) but BEFORE execution fill quality or market conditions degrade it.
* `ml_post_quality_proba`: The final adjusted model probability used for display and post-quality execution analysis.
* `gating_confidence`: The strict confidence metric used in gating logic (such as aligned high confidence overrides).
* `sizing_confidence`: The strict confidence metric utilized for position sizing multipliers, explicitly mirroring `ml_proba_input`.
* `ml_model_name`: The algorithm family name (e.g. `xgb`, `deep`).
* `ml_model_version`: The specific artifact/hash/version generating the score.

## Field Assignments
* **Which field drives gating?** `gating_confidence` records the same value already used by the existing gating logic; this PR does not change gating behavior.
* **Which field drives sizing?** `sizing_confidence` is explicitly consumed by `_apply_sizing_telemetry` and dictates capital allocation multipliers.
* **Which field is raw model output?** `ml_model_raw_proba`.
* **Which field is post-quality/display confidence?** `ml_post_quality_proba`.

## Proof of Execution Behavior Parity
A strict invariant check (`tests/test_ml_telemetry_truth.py::test_no_execution_behavior_changed`) was introduced that seeds identical trade scenarios with complete final intent permutations. The test unequivocally passes, proving:
1. Sizing confidence precisely falls back on legacy structures without modifying sizing output.
2. `final_action`, `execution_allowed`, `order_policy`, and `tradable` remain **identical**. Execution behavior is completely insulated from the telemetry standardization.

## Test Summary
### Tests Run (Successfully)
* `pytest -q tests/test_ml_telemetry_truth.py` (Passed all 4 cases: `test_review_queue_sizing_confidence`, `test_trade_builder_staged_confidence_payload`, `test_legacy_compatibility`, `test_no_execution_behavior_changed`).
* `pytest -q tests/test_aligned_high_conf_downgrade.py tests/test_review_queue_live_entry.py` (Passed 113 cases).
* `pytest -q tests/test_fallback_never_executable.py tests/test_jit_quote_revalidation.py` (Passed successfully).
* Full suite (`pytest -q tests/`) is running via GitHub Actions CI remote hook.

### Tests Not Run
* `tests/test_audit_phase_b_jit.py` was skipped because the file was missing/did not exist within the tree even after fetching `main`.

### CI Status
* Branch `fix/ml-confidence-telemetry-truth` is fully pushed to GitHub.
* CI suite triggered on remote (GitHub Actions). All local targeted subsets completely passed.

## Files Changed
- `core/trade_schema.py`
- `core/advisory_schema.py`
- `core/review_queue.py`
- `strategies/trade_builder.py`
- `tests/test_ml_telemetry_truth.py` (New file)
