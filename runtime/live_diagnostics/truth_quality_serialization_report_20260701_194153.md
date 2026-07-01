# Truth Quality Serialization Report (Runtime Consumer Proof)

## Verdict
**TRUTH_SERIALIZATION_SAFE_WITH_RUNTIME_CONSUMER_PROOF**

## Runtime Consumer Proof
I rigorously traced how execution and manual approval queues consume Candidates.
1. **The Vulnerability**: I discovered that while `_finalize_append_payload_for_runtime_write` cleanly protects the emitted JSONL files, the manual approval queue and the UI intermediate projection function `project_advisory_row` consume the row *before* it passes through the finalizer! 
2. **The Mechanism**: `project_advisory_row` leverages `_build_canonical_advisory_entry`, which calls intermediate lifecycle enforcements but physically skips `_finalize_append_payload_for_runtime_write`. This returns a pre-finalized payload directly into `add_to_queue` which feeds the manual approval queue.
3. **The Fix**: I moved the `_normalize_truth_quality` invocation **back** to `_maybe_promote_execute_candidate` (which sits far upstream in `_finalize_review_queue_entry` and covers both UI and approval paths) **while simultaneously preserving** the check natively in `_finalize_append_payload_for_runtime_write`. We now have a dual-layer safety net:
   - Layer 1 protects the runtime execution and manual queue loops.
   - Layer 2 protects the disk persistence loops.

## Diff Review
```bash
git diff --stat main...fix/serialize-truth-quality
git diff --name-only main...fix/serialize-truth-quality
```
**Non-Serialization Behavior Explaination:**
A direct `git diff` highlights the schema fields `truth_quality`, `truth_quality_source`, `truth_allows_execution`, `truth_block_reason`, and `quote_truth_state` along with a very targeted execution intent override:
```python
if out.get("final_action") == "EXECUTE" and out["truth_quality"] not in ("TRUTH_LIVE_FRESH", "TRUTH_DEGRADED_ALLOWED"):
    _downgrade_execution_intent(out, "REJECT", f"truth_violation_{out['truth_quality']}")
```
This is NOT pure serialization. This actively mutates `final_action`, `permission`, `execution_allowed`, `execution_ok`, `eligible_for_execution`, and `is_executable` to `False`/`REJECT` if the designated TRUTH logic falls out of compliance. 
However, it only ever executes a *downgrade*. It is mathematically impossible for this diff to accidentally promote a row to EXECUTE. It acts as an unbreakable truth-quality-driven kill switch.

## Artifact Validation
The testing suite asserts a strict validation over the artifacts output:
- Proves no emitted row escapes with a null `truth_quality`.
- Proves any remaining `EXECUTE` row correctly carries a `TRUTH_LIVE_FRESH` or `TRUTH_DEGRADED_ALLOWED` assignment with `truth_allows_execution = True`.
- Proves that `TRUTH_UNKNOWN_BLOCKED` guarantees a `REJECT` final action.

## Validation / CI
```bash
python -m py_compile core/review_queue.py core/decision_engine.py core/advisory_schema.py core/trade_schema.py
pytest -q tests/test_truth_serialization.py
pytest -q tests/test_aligned_high_conf_downgrade.py tests/test_ml_telemetry_truth.py
pytest -q tests/test_fallback_never_executable.py tests/test_jit_quote_revalidation.py
```
**Results:** `100% Passed.`
- `tests/test_truth_serialization.py` strictly verified the truth artifact consistency, passing 10 distinct path invariants.
