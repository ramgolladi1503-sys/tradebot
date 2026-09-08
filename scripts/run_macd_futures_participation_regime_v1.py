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
from research.macd_futures_participation_regime_v1.robustness import (  # noqa: E402
    robustness_bundle,
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
        if h1_support["support_gate_pass"]:
            h1_ps = prepare_interaction(signals, assigned, state, "h1_active")
            h1_ps.to_csv(out / "H1_PER_SIGNAL_PAIRED_DELTAS.csv", index=False)
            h1_summary = summarize_interaction(h1_ps)
            h1_summary["pre_payoff_support"] = h1_support
            h1_summary["support_gate_pass"] = True
            h1 = frozen_hypothesis_result(
                h1_summary,
                "MACD_FUTURES_PARTICIPATION_REGIME_V1_H1",
            )
            h1["retrospective_robustness"] = _write_robustness(out, "H1", h1_ps)
            robustness_completed.append("H1")
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

            h2_support = signal_state_support(signals, state, "h2_active")
            write_json(out / "H2_STATE_SUPPORT.json", h2_support)
            if h2_support["support_gate_pass"]:
                h2_ps = prepare_interaction(signals, assigned, state, "h2_active")
                h2_ps.to_csv(out / "H2_PER_SIGNAL_PAIRED_DELTAS.csv", index=False)
                h2_summary = summarize_interaction(h2_ps)
                h2_summary["pre_payoff_support"] = h2_support
                h2_summary["support_gate_pass"] = True
                h2 = frozen_hypothesis_result(
                    h2_summary,
                    "MACD_FUTURES_PARTICIPATION_REGIME_V1_H2",
                )
                h2["retrospective_robustness"] = _write_robustness(out, "H2", h2_ps)
                robustness_completed.append("H2")
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
            "retrospective_robustness_completed_for": robustness_completed,
            "full_gate_status": "PARTIAL_RETROSPECTIVE_GATES_ONLY",
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_write_authority": False,
            "order_authority": False,
            "broker_calls": 0,
            "orders": 0,
            "next_required_gates": [
                "session_block_permutation",
                "one_and_two_bar_delay",
                "basis_state_permutation",
                "condition_removal",
                "global_multiplicity_FDR",
                "independent_oracle",
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
