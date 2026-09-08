from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macd_futures_participation_regime_v1.analysis import (  # noqa: E402
    CampaignBlocked,
    SourcePaths,
    bind_macd_ledgers,
    build_basis_state,
    load_table,
    prepare_interaction,
    signal_state_support,
    source_manifest,
    write_json,
)
from research.macd_futures_participation_regime_v1.full_gates import (  # noqa: E402
    FullGateBlocked,
    evaluate_full_gates,
    semantic_hash,
)
from research.macd_futures_participation_regime_v1.independent_oracle import (  # noqa: E402
    verify_primary_ledger,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Full retrospective MACD x futures-participation regime campaign"
    )
    p.add_argument("--aligned-parquet", required=True)
    p.add_argument("--assignments", required=True)
    p.add_argument("--signal-paths", required=True)
    p.add_argument("--placebo-payoffs", required=True)
    p.add_argument("--delay1-per-signal")
    p.add_argument("--delay2-per-signal")
    p.add_argument("--multiplicity-ledger-json")
    p.add_argument("--output-root", required=True)
    return p.parse_args()


def _load_optional(path: str | None) -> pd.DataFrame | None:
    return load_table(Path(path)) if path else None


def _load_multiplicity(path: str | None) -> dict[str, float] | None:
    if not path:
        return None
    obj = json.loads(Path(path).read_text())
    if not isinstance(obj, dict):
        raise FullGateBlocked("MULTIPLICITY_LEDGER_MUST_BE_JSON_OBJECT")
    out: dict[str, float] = {}
    for key, value in obj.items():
        try:
            p = float(value)
        except (TypeError, ValueError) as exc:
            raise FullGateBlocked(f"MULTIPLICITY_INVALID_PVALUE:{key}") from exc
        if not (0.0 <= p <= 1.0):
            raise FullGateBlocked(f"MULTIPLICITY_PVALUE_OUT_OF_RANGE:{key}:{p}")
        out[str(key)] = p
    return out


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _status(result: dict, oracle: dict, determinism: dict) -> str:
    if oracle.get("status") != "PASS" or determinism.get("status") != "PASS":
        return "MACD_FUTURES_REGIME_BLOCKED"
    if result.get("blockers"):
        return "MACD_FUTURES_REGIME_BLOCKED"
    if result.get("full_numeric_gates_pass"):
        return "MACD_FUTURES_REGIME_RETROSPECTIVE_SUPPORTED"
    if result.get("statistical_core_pass"):
        return "MACD_FUTURES_REGIME_WEAK"
    return "MACD_FUTURES_REGIME_NOT_SUPPORTED"


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
        "retrospective_research_exposed": True,
    }
    write_json(out / "SAFETY.json", safety)

    try:
        write_json(out / "SOURCE_AUTHORITY.json", source_manifest(paths))
        aligned = load_table(paths.aligned_parquet)
        assignments = load_table(paths.assignments)
        signal_paths = load_table(paths.signal_paths)
        placebo = load_table(paths.placebo_payoffs)
        state = build_basis_state(aligned)
        signals, assigned = bind_macd_ledgers(assignments, signal_paths, placebo)

        reached: list[dict] = []
        selected_id: str | None = None
        selected_per_signal: pd.DataFrame | None = None
        queue = [
            ("MACD_FUTURES_PARTICIPATION_REGIME_V1_H1", "h1_active"),
            ("MACD_FUTURES_PARTICIPATION_REGIME_V1_H2", "h2_active"),
        ]
        for hypothesis_id, state_col in queue:
            support = signal_state_support(signals, state, state_col)
            write_json(out / f"{hypothesis_id}_STATE_SUPPORT.json", support)
            if not support["support_gate_pass"]:
                reached.append({
                    "hypothesis_id": hypothesis_id,
                    "status": "INSUFFICIENT_SUPPORT",
                    "pre_payoff_support": support,
                    "outcomes_accessed_for_hypothesis": False,
                })
                continue
            selected_id = hypothesis_id
            selected_per_signal = prepare_interaction(signals, assigned, state, state_col)
            selected_per_signal.to_csv(
                out / f"{hypothesis_id}_PER_SIGNAL_PAIRED_DELTAS.csv", index=False
            )
            break

        if selected_id is None or selected_per_signal is None:
            final = {
                "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
                "verdict": "MACD_FUTURES_REGIME_NOT_SUPPORTED",
                "reason": "H1_AND_H2_INSUFFICIENT_PREPAYOFF_SUPPORT",
                "hypotheses_reached": reached,
                **safety,
            }
            write_json(out / "FINAL_VERDICT.json", final)
            print(json.dumps(final, indent=2, sort_keys=True))
            return 0

        delay1 = _load_optional(args.delay1_per_signal)
        delay2 = _load_optional(args.delay2_per_signal)
        multiplicity = _load_multiplicity(args.multiplicity_ledger_json)

        result1, folds1, loqo1 = evaluate_full_gates(
            selected_per_signal,
            delay1=delay1,
            delay2=delay2,
            hypothesis_id=selected_id,
            external_multiplicity_pvalues=multiplicity,
        )
        result2, folds2, loqo2 = evaluate_full_gates(
            selected_per_signal,
            delay1=delay1,
            delay2=delay2,
            hypothesis_id=selected_id,
            external_multiplicity_pvalues=multiplicity,
        )

        hashes1 = {
            "result": semantic_hash(result1),
            "folds": semantic_hash(folds1.to_dict(orient="records")),
            "loqo": semantic_hash(loqo1.to_dict(orient="records")),
        }
        hashes2 = {
            "result": semantic_hash(result2),
            "folds": semantic_hash(folds2.to_dict(orient="records")),
            "loqo": semantic_hash(loqo2.to_dict(orient="records")),
        }
        determinism = {
            "status": "PASS" if hashes1 == hashes2 else "FAIL",
            "run_1": hashes1,
            "run_2": hashes2,
        }
        oracle = verify_primary_ledger(selected_per_signal, result1)

        write_json(out / "FULL_GATE_RESULT.json", result1)
        folds1.to_csv(out / "CHRONOLOGICAL_FOLD_RESULTS.csv", index=False)
        loqo1.to_csv(out / "LEAVE_ONE_QUARTER_OUT.csv", index=False)
        write_json(out / "INDEPENDENT_ORACLE.json", oracle)
        write_json(out / "DETERMINISM.json", determinism)

        verdict = _status(result1, oracle, determinism)
        final = {
            "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
            "hypothesis_evaluated": selected_id,
            "prepayoff_insufficient_support_hypotheses": reached,
            "verdict": verdict,
            "statistical_core_pass": result1["statistical_core_pass"],
            "full_numeric_gates_pass": result1["full_numeric_gates_pass"],
            "blockers": result1["blockers"],
            "independent_oracle": oracle["status"],
            "determinism": determinism["status"],
            "retrospective_research_exposed": True,
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_write_authority": False,
            "order_authority": False,
            "broker_calls": 0,
            "orders": 0,
            "next_action": (
                "supply canonical delayed-entry ledgers and global multiplicity ledger"
                if result1["blockers"]
                else (
                    "freeze exact successor for separate prospective shadow"
                    if verdict == "MACD_FUTURES_REGIME_RETROSPECTIVE_SUPPORTED"
                    else "reject this hypothesis without retuning"
                )
            ),
        }
        write_json(out / "FINAL_VERDICT.json", final)

        manifest = {
            p.name: _file_hash(p)
            for p in sorted(out.iterdir())
            if p.is_file() and p.name != "SHA256SUMS.json"
        }
        write_json(out / "SHA256SUMS.json", manifest)
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0 if verdict != "MACD_FUTURES_REGIME_BLOCKED" else 2

    except (CampaignBlocked, FullGateBlocked, OSError, ValueError, json.JSONDecodeError) as exc:
        final = {
            "campaign": "MACD_FUTURES_PARTICIPATION_REGIME_V1",
            "verdict": "MACD_FUTURES_REGIME_BLOCKED",
            "blocker": f"{type(exc).__name__}:{exc}",
            "retrospective_research_exposed": True,
            "structural_edge_certified": False,
            "execution_viable": "UNKNOWN",
            "broker_calls": 0,
            "orders": 0,
        }
        write_json(out / "FINAL_VERDICT.json", final)
        print(json.dumps(final, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
