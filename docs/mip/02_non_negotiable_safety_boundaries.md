# Agent 2 Report: Non-Negotiable Safety Boundaries

## Safety Critical Paths

The system utilizes highly constrained pathways to promote a candidate from generation to execution. We have identified the following safety-critical paths:

1. **Phase-2**: Candidates must pass extensive deep checks (e.g., `_engine_phase2_adapter_base.py`). Any failing checks revert the candidate to an `ADVISORY_ONLY` state or block it entirely.
2. **Ranking**: Ranking (`candidate_ranking.py`) strictly relies on calibrated score expectations. Execution is strictly ordered based on `execution_allowed` flags.
3. **Execution**: The `execution_engine.py` strictly gates execution. It verifies that `execution_ok=True` and that all required block/suspend flags are clear.
4. **Quote Truth & Freshness**: Monitored by `quote_truth.py` and `feed_freshness_gate.py`. Stale or inconsistent market quotes immediately flag candidates as `HARD_REJECT_STATE`.
5. **Fallback Logic**: Fallbacks (`live_fallback_execution_contract.py`) are severely constrained. Fallback data triggering execution is explicitly flagged as a `HARD_REJECT` marker (`fallback_driven_data`).
6. **Risk Engine & Governance**: `pretrade_risk_engine.py` evaluates positional limits, slippage costs, and latency health. Governance gates enforce manual overrides and explicit system halts.

## Non-Negotiable Rules for the Market Intelligence Platform (MIP)

Based on the repository's strict safety boundaries, the new MIP **MUST NEVER BREAK** the following rules:

* **Rule 1**: The MIP must never set, force, or suggest `execution_ok=True`.
* **Rule 2**: The MIP must never remove existing blockers or clear soft/hard reject states.
* **Rule 3**: The MIP must never bypass Phase-2 deep checks.
* **Rule 4**: The MIP must never bypass quote truth or freshness gates.
* **Rule 5**: The MIP must never create a candidate out of thin air. It is strictly an advisory context provider.
* **Rule 6**: The MIP must never change a stop loss, target, or any execution threshold unless explicitly designed as an advisory suggestion mapped via the `advisory_schema`.
* **Rule 7**: Any ranking influence from the MIP is explicitly **FORBIDDEN** unless the payload has been formally validated through replay calibration (`calibration_status = CALIBRATED`). Until then, `ranking_influence_allowed = false`.
* **Rule 8**: All MIP data attached to a candidate must default to `execution_influence_allowed = false`.
* **Rule 9**: There shall be no fake edge or arbitrary confidence values injected. Any probability claim must trace back to explicit, verifiable evidence.
