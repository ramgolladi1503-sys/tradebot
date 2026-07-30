from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

_RANKING_MARKERS = {
    "build_ranked_opportunity_report",
    "build_ranked_pipeline_runtime_report",
    "rank_candidates",
    "score_candidates",
    "select_top_opportunities",
}
_EXECUTION_MARKERS = {
    "place_order",
    "route_execution",
    "execution_router",
    "execute_trade",
    "submit_order",
}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


@dataclass(frozen=True)
class AuthorityEvidence:
    path: str
    ranking_calls: tuple[str, ...]
    execution_calls: tuple[str, ...]
    ranking_results_consumed_by_execution: bool
    assignment_targets: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def inspect_authority(path: str | Path) -> AuthorityEvidence:
    source_path = Path(path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    ranking_calls: set[str] = set()
    execution_calls: set[str] = set()
    ranked_targets: set[str] = set()
    execution_argument_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = _dotted(node.func)
            leaf = call.rsplit(".", 1)[-1]
            if leaf in _RANKING_MARKERS:
                ranking_calls.add(call)
            if leaf in _EXECUTION_MARKERS:
                execution_calls.add(call)
                for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                    for inner in ast.walk(argument):
                        if isinstance(inner, ast.Name):
                            execution_argument_names.add(inner.id)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if isinstance(value, ast.Call) and _dotted(value.func).rsplit(".", 1)[-1] in _RANKING_MARKERS:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for inner in ast.walk(target):
                        if isinstance(inner, ast.Name):
                            ranked_targets.add(inner.id)

    return AuthorityEvidence(
        path=str(source_path),
        ranking_calls=tuple(sorted(ranking_calls)),
        execution_calls=tuple(sorted(execution_calls)),
        ranking_results_consumed_by_execution=bool(ranked_targets & execution_argument_names),
        assignment_targets=tuple(sorted(ranked_targets)),
    )


def inspect_authority_paths(paths: Iterable[str | Path]) -> dict[str, object]:
    evidence = [inspect_authority(path) for path in paths]
    direct_authorities = [item.path for item in evidence if item.ranking_results_consumed_by_execution]
    return {
        "files": [item.to_dict() for item in evidence],
        "direct_authority_files": direct_authorities,
        "ranking_is_proven_execution_authority": bool(direct_authorities),
    }


__all__ = ["AuthorityEvidence", "inspect_authority", "inspect_authority_paths"]
