from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.closure import (  # type: ignore
        AuthorityClosureDeterminismError,
        AuthorityClosureInputError,
        AuthorityClosureReconciliationError,
        build_all_strategy_authority_closure,
        load_authority_closure_inputs,
    )
    from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.compact_publication import (  # type: ignore
        build_authority_compact_publication,
    )
    from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.provenance_evidence import (  # type: ignore
        ProvenanceEvidenceError,
    )
else:
    from .closure import (
        AuthorityClosureDeterminismError,
        AuthorityClosureInputError,
        AuthorityClosureReconciliationError,
        build_all_strategy_authority_closure,
        load_authority_closure_inputs,
    )
    from .compact_publication import build_authority_compact_publication
    from .provenance_evidence import ProvenanceEvidenceError


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build all-strategy authority closure from full census runs.")
    parser.add_argument("--run-a", required=True, type=Path)
    parser.add_argument("--run-b", required=True, type=Path)
    parser.add_argument("--compact-census-dir", type=Path, default=None)
    parser.add_argument("--signal-provenance-dir", type=Path, default=None)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--compact-output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    signal_provenance_dir = args.signal_provenance_dir or (
        repo_root
        / "research"
        / "option_e2e_recertification_v4"
        / "signal_ledger_provenance_v1"
    )
    try:
        snapshot = load_authority_closure_inputs(
            full_run_a=args.run_a,
            full_run_b=args.run_b,
            signal_ledger_provenance_dir=signal_provenance_dir,
            compact_census_dir=args.compact_census_dir,
        )
        build_all_strategy_authority_closure(snapshot=snapshot, output_dir=args.output_dir)
        if args.compact_output_dir is not None:
            build_authority_compact_publication(
                full_authority_dir=args.output_dir,
                output_dir=args.compact_output_dir,
            )
    except (
        AuthorityClosureInputError,
        AuthorityClosureDeterminismError,
        AuthorityClosureReconciliationError,
        ProvenanceEvidenceError,
        OSError,
    ) as exc:
        print("AUTHORITY_CLOSURE_INPUT_INTEGRITY_FAILED")
        print(str(exc))
        return 1
    print("AUTHORITY_CLOSURE_INPUT_INTEGRITY_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
