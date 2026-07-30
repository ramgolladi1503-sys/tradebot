"""AST-based proof of the active candidate-to-execution runtime call path.

The audit reads source only. It performs no imports of the production Orchestrator,
no broker calls, and no runtime mutation.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CallSite:
    call_name: str
    line_number: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "call_name": self.call_name,
            "line_number": self.line_number,
        }


@dataclass(frozen=True)
class RuntimeCallPathAudit:
    orchestrator_calls: tuple[CallSite, ...]
    trade_builder_calls: tuple[CallSite, ...]
    ordered_execution_path: tuple[CallSite, ...]
    selector_call_count: int
    advisory_rank_call_count: int
    canonical_ui_ranker_called_by_orchestrator: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_payload(self) -> dict[str, Any]:
        return {
            "orchestrator_calls": [item.to_payload() for item in self.orchestrator_calls],
            "trade_builder_calls": [item.to_payload() for item in self.trade_builder_calls],
            "ordered_execution_path": [item.to_payload() for item in self.ordered_execution_path],
            "selector_call_count": self.selector_call_count,
            "advisory_rank_call_count": self.advisory_rank_call_count,
            "canonical_ui_ranker_called_by_orchestrator": self.canonical_ui_ranker_called_by_orchestrator,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "passed": self.passed,
            "broker_api_called": False,
            "is_order_action": False,
        }


_ORCHESTRATOR_PATH: tuple[str, ...] = (
    "self.trade_builder.build_with_trace",
    "self.risk_state.approve",
    "approval_status",
    "self.risk_engine.evaluate_trade",
    "self.execution_guard.evaluate",
    "self.execution_router.execute",
)


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _collect_calls(source: str) -> tuple[CallSite, ...]:
    tree = ast.parse(source)
    calls: list[CallSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name:
            calls.append(CallSite(name, int(getattr(node, "lineno", 0) or 0)))
    return tuple(sorted(calls, key=lambda item: (item.line_number, item.call_name)))


def _first_call(calls: Iterable[CallSite], name: str) -> CallSite | None:
    return next((item for item in calls if item.call_name == name), None)


def audit_runtime_call_path(
    orchestrator_source: str,
    trade_builder_source: str,
) -> RuntimeCallPathAudit:
    orchestrator_calls = _collect_calls(orchestrator_source)
    trade_builder_calls = _collect_calls(trade_builder_source)
    errors: list[str] = []
    warnings: list[str] = []

    ordered: list[CallSite] = []
    for required in _ORCHESTRATOR_PATH:
        call = _first_call(orchestrator_calls, required)
        if call is None:
            errors.append(f"required_runtime_call_missing:{required}")
        else:
            ordered.append(call)

    if len(ordered) == len(_ORCHESTRATOR_PATH):
        line_numbers = [item.line_number for item in ordered]
        if line_numbers != sorted(line_numbers):
            errors.append("runtime_call_order_invalid")

    selector_calls = tuple(
        item for item in trade_builder_calls if item.call_name == "select_best_opportunity"
    )
    advisory_rank_calls = tuple(
        item for item in trade_builder_calls if item.call_name == "annotate_ranked_opportunities"
    )
    if not selector_calls:
        errors.append("trade_builder_execution_selector_missing")
    if not advisory_rank_calls:
        warnings.append("trade_builder_advisory_ranker_missing")

    canonical_ui_ranker_called = any(
        item.call_name == "build_ranked_opportunity_report"
        for item in orchestrator_calls
    )
    if canonical_ui_ranker_called:
        errors.append("ui_only_canonical_ranker_called_from_execution_orchestrator")

    return RuntimeCallPathAudit(
        orchestrator_calls=orchestrator_calls,
        trade_builder_calls=trade_builder_calls,
        ordered_execution_path=tuple(ordered),
        selector_call_count=len(selector_calls),
        advisory_rank_call_count=len(advisory_rank_calls),
        canonical_ui_ranker_called_by_orchestrator=canonical_ui_ranker_called,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def audit_repository_runtime_call_path(repo_root: str | Path) -> RuntimeCallPathAudit:
    root = Path(repo_root)
    orchestrator_source = (root / "core" / "orchestrator.py").read_text(encoding="utf-8")
    trade_builder_source = (root / "strategies" / "trade_builder.py").read_text(encoding="utf-8")
    return audit_runtime_call_path(orchestrator_source, trade_builder_source)


__all__ = [
    "CallSite",
    "RuntimeCallPathAudit",
    "audit_repository_runtime_call_path",
    "audit_runtime_call_path",
]
