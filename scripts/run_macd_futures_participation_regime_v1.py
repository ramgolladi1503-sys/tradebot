from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macd_futures_participation_regime_v1.analysis import (  # noqa: E402
    CampaignBlocked,
    SourcePaths,
    bind_macd_ledgers,
    build_basis_state,
    frozen_hypothesis_result,
    load_table,
    prepare_interaction,
    signal_state_support,
    source_manifest,
    summarize_interaction,
    write_json,
)
from research.macd_futures_participation_regime_v1.controls import (  # noqa: E402
    controls_bundle,
)
from research.macd_futures_participation_regime_v1.matching import (  # noqa: E402
    validate_state_matching_coverage,
)
from research.macd_futures_participation_regime_v1.oracle import (  # noqa: E402
    OracleError,
    verify_primary_output,
)
from research.macd_futures_participation_regime_v1.robustness import (  # noqa: E402
    robustness_bundle,
)
from research.macd_futures_participation_regime_v1.timing_control import (  # noqa: E402
    within_session_circular_state_shift_control,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Retrospective MACD x futures-participation regime campaign"
    )
    p.add_argument("--aligned-parquet", required=True)
    p.add_argument("--assignments", required=True)
    p.add_argument("--signal-paths", required=True)
    p.add_argument("--placebo-payoffs", required=True)
    p.add_argument("--output-root", required=True)
    return p.parse_args()


def _write_robustness(out: Path, prefix: str, per_signal) -> dict:
    folds, robustness = robustness_bundle(per_signal)
    folds.to_csv(out / f"{prefix}_FOLD_RESULTS.csv", index=False)
    write_json(out / f"{prefix}_RETROSPECTIVE_ROBUSTNESS.json", robustness)
    return robustness


def _run_oracle(
    out: Path,
    prefix: str,
    state_id: str,
    aligned,
    assignments,
    signal_paths,
    placebo,
    per_signal,
) -> dict:
    try:
        oracle = verify_primary_output(
            aligned,
            assignments,
            signal_paths,
            placebo,
            per_signal,
            state_id,
        )
    except OracleError as exc:
        raise CampaignBlocked(f"INDEPENDENT_ORACLE_ERROR:{state_id}:{exc}") from exc
    write_json(out / f"{prefix}_INDEPENDENT_ORACLE.json", oracle)
    if oracle["verdict"] != "PASS":
        raise CampaignBlocked(
            f"INDEPENDENT_ORACLE_FAIL:{state_id}:mismatches={oracle['mismatch_count']}"
        )
    return oracle


def _evaluate_supported(
    *,
    out: Path,
    prefix: str,
    hypothesis_id: str,
    state_id: str,
    state_col: str,
    support: dict,
    aligned,
    assignments,
    signal_paths,
    placebo,
    signals,
    assigned,
    state,
) -> dict:
    per_signal = prepare_interaction(signals, assigned, state, state_col)

    # Matching quality is a gate, not a descriptive afterthought. A signal may
    # not disappear merely because its same-state placebo pool is inconvenient.
    matching = validate_state_matching_coverage(per_signal, signals)
    write_json(out / f"{prefix}_MATCHING_COVERAGE.json", matching)

    per_signal.to_csv(out / f"{prefix}_PER_SIGNAL_PAIRED_DELTAS.csv", index=False)
    oracle = _run_oracle(
        out,
        prefix,
        state_id,
        aligned,
        assignments,
        signal_paths,
        placebo,
        per_signal,
    )

    summary = summarize_interaction(per_signal)
    summary["pre_payoff_support"] = support
    summary["support_gate_pass"] = True
    result = frozen_hypothesis_result(summary, hypothesis_id)
    result["matching_coverage"] = matching
    result["independent_oracle"] = oracle

    controls = controls_bundle(per_signal)
    write_json(out / f"{prefix}_CORE_NEGATIVE_CONTROLS.json", controls)
    result["core_negative_controls"] = controls

    timing_control = within_session_circular_state_shift_control(
        signals=signals,
        assigned=assigned,
        state=state,
        state_col=state_col,
        primary_per_signal=per_signal,
    )
    write_json(out / f"{prefix}_BASIS_TIMING_CONTROL.json", timing_control)
    result["basis_timing_control"] = timing_control

    result["retrospective_robustness"] = _write_robustness(
        out, prefix, per_signal
    )
    return result


def main() -> int:
    args = parse_args()
    out = Path(args.output_root)
    out.mkdir(parents=True, exist_ok=True)
    paths = SourcePaths(
        aligned_parquet=Path(args.aligned_parquet),
        assignments=Path(args.assignments),
        signal_paths=Path(args.signal_paths),
        placebo_payoffs=Path(args.placebo_payoffs),
    )

    safety = {
        "buy_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "broker_calls": 0,
        "orders": 0,
        "structural_edge_certified": False,
        "execution_viable": "UNKNOWN",
    }
    write_json(out / "SAFETY.json", safety)

    try:
        manifest = source_manifest(paths)
        write_json(out / "SOURCE_AUTHORITY.json", manifest)

        aligned = load_table(paths.aligned_parquet)
        assignments = load_table(paths.assignments)
        signal_paths = load_table(paths.signal_paths)
        placebo = load_table(paths.placebo_payoffs)

        state = build_basis_state(aligned)
        signals, assigned = bind_macd_ledgers(assignments, signal_paths, placebo)

        h1_support = signal_state_support(signals, state, "h1_active")
        write_json(out / "H1_STATE_SUPPORT.json", h1_support)

        evaluated = []
        robustness_completed = []
        oracle_completed = []
        controls_completed = []
        timing_control_completed = []
        matching_completed = []

        if h1_support["support_gate_pass"]:
            h1 = _evaluate_supported(
                out=out,
                prefix="H1",
                hypothesis_id="MACD_FUTURES_PARTICIPATION_REGIME_V1_H1",
                state_id="H1",
                state_col="h1_active",
                support=h1_support,
                aligned=aligned,
                assignments=assignments,
                signal_paths=signal_paths,
                placebo=placebo,
                signals=signals,
                assigned=assigned,
                state=state,
            )
            robustness_completed.append("H1")
            oracle_completed.append("H1")
            controls_completed.append("H1")
            timing_control_completed.append("H1")
            matching_completed.append("H1")
            write_json(out / "H1_PRIMARY_RESULT.json", h1)
            evaluated.append(h1)
        else:
            h1 = {
                "hypothesis_id": "MACD_FUTURES_PARTICIPATION_REGIME_V1_H1",
                "status": "INSUFFICIENT_SUPPORT",
                "pre_payoff_support": h1_support,
                "outcomes_accessed_for_hypothesis": False,
            }
            write_json(out / "H1_PRIMARY_RESULT.json", h1)
            evaluated.append(h1)

            # H2 is reached only because H1 failed its frozen pre-payoff support
            # gate. H1 outcomes remain unopened in this branch of the campaign.
            h2_support = signal_state_support(signals, state, "h2_active")
            write_json(out / "H2_STATE_SUPPORT.json", h2_support)
            if h2_support["support_gate_pass"]:
                h2 = _evaluate_supported(
                    out=out,
                    prefix="H2",
                    hypothesis_id="MACD_FUTURES_PARTICIPATION_REGIME_V1_H2",
                    state_id="H2",
                    state_col="h2_active",
                    support=h2_support,
                    aligned=aligned,
                    assignments=assignments,
                    signal_paths=signal_paths,
                    placebo=placebo,
                    signals=signals,
                    assigned=assigned,
                    state=state,
                )
                robustness_completed.append("H2")
                oracle_completed.append("H2")
                controls_completed.append("H2")
                timing_control_completed.append("H2")
                matching_completed.append("H2")
            else:
                h2 = {
                    "hypothesis_id": "MACD_FUTURES_PARTICIPATION_REGIME_V1_H2",
                    "status": "INSUFFICIENT_SUPPORT",
                    "pre_payoff_support": h2_support,
                    "outcomes_accessed_for_hypothesis": False,
                }
            write_json(out / "H2_PRIMARY_RESULT.json", h2)
            evaluated.append(h2)

        final = {
            "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
            "hypotheses_evaluated": evaluated,
            "retrospective_research_exposed": True,
            "matching_coverage_completed_for": matching_completed,
            "retrospective_robustness_completed_for": robustness_completed,
            "independent_oracle_completed_for": oracle_completed,
            "core_negative_controls_completed_for": controls_completed,
            "basis_timing_control_completed_for": timing_control_completed,
            "full_gate_status": "PARTIAL_RETROSPECTIVE_GATES_ONLY",
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_write_authority": False,
            "order_authority": False,
            "broker_calls": 0,
            "orders": 0,
            "next_required_gates": [
                "one_and_two_bar_delay",
                "global_multiplicity_FDR",
                "determinism_rerun",
                "prospective_independent_evaluation_if_retrospective_supported",
                "execution_cost_authority",
            ],
        }
        write_json(out / "PRIMARY_STAGE_VERDICT.json", final)
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0
    except CampaignBlocked as exc:
        blocked = {
            "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
            "verdict": "MACD_FUTURES_REGIME_BLOCKED",
            "blocker": str(exc),
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_calls": 0,
            "orders": 0,
        }
        write_json(out / "PRIMARY_STAGE_VERDICT.json", blocked)
        print(json.dumps(blocked, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
