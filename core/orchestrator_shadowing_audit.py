"""AST-only audit for imported authority helpers shadowed in core.orchestrator.

Importing core.orchestrator is intentionally avoided because it constructs a very
broad dependency graph. The audit is deterministic and safe for CI.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASELINE_SHADOWED_TRUTH_ALIASES: frozenset[str] = frozenset(
    {
        "_build_snapshot_numbers",
        "_canonical_feed_truth_state_payload",
        "_candidate_origin",
        "_candidate_runtime_truth_summary",
        "_candidate_trace_payload",
        "_candidate_visibility_bucket",
        "_coerce_trade_dict_to_schema",
        "_feed_truth_cycle_gate",
        "_filter_invalid_cycle_candidates",
        "_is_reportable_executable_candidate",
        "_is_structurally_valid_cycle_candidate",
        "_is_synthetic_candidate",
        "_normalize_feed_runtime_payload",
        "_read_json_dict",
        "_read_latest_feed_runtime_payload",
        "_regime_unstable_diagnostic_payload",
        "_replace_trade_fields",
        "_safe_float",
        "_snapshot_atm_strike",
        "_trade_attr",
    }
)


@dataclass(frozen=True)
class ShadowingAudit:
    imported_aliases: tuple[str, ...]
    locally_defined: tuple[str, ...]
    shadowed_aliases: tuple[str, ...]
    new_shadowing: tuple[str, ...]
    missing_baseline: tuple[str, ...]

    @property
    def controlled(self) -> bool:
        return not self.new_shadowing

    def to_payload(self) -> dict[str, object]:
        return {
            "imported_aliases": list(self.imported_aliases),
            "locally_defined": list(self.locally_defined),
            "shadowed_aliases": list(self.shadowed_aliases),
            "new_shadowing": list(self.new_shadowing),
            "missing_baseline": list(self.missing_baseline),
            "controlled": self.controlled,
            "is_order_action": False,
        }


def audit_orchestrator_truth_shadowing(
    source: str,
    *,
    baseline: Iterable[str] = BASELINE_SHADOWED_TRUTH_ALIASES,
) -> ShadowingAudit:
    tree = ast.parse(source)
    imported: set[str] = set()
    local_defs: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.orchestrator_truth":
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local_defs.add(node.name)

    shadowed = imported & local_defs
    baseline_set = set(baseline)
    return ShadowingAudit(
        imported_aliases=tuple(sorted(imported)),
        locally_defined=tuple(sorted(local_defs)),
        shadowed_aliases=tuple(sorted(shadowed)),
        new_shadowing=tuple(sorted(shadowed - baseline_set)),
        missing_baseline=tuple(sorted(baseline_set - shadowed)),
    )


def audit_repository_orchestrator(repo_root: str | Path) -> ShadowingAudit:
    path = Path(repo_root) / "core" / "orchestrator.py"
    return audit_orchestrator_truth_shadowing(path.read_text(encoding="utf-8"))


__all__ = [
    "BASELINE_SHADOWED_TRUTH_ALIASES",
    "ShadowingAudit",
    "audit_orchestrator_truth_shadowing",
    "audit_repository_orchestrator",
]
