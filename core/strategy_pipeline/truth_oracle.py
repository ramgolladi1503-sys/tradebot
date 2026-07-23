from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum


class TruthOracleClassification(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


@dataclass(frozen=True)
class TruthOracleResult:
    classification: TruthOracleClassification
    paradigm: str
    checks: dict[str, bool]
    reason: str


def evaluate_truth_oracle(source_code: str, description: str) -> TruthOracleResult:
    """Independent AST structural oracle for known strategy paradigms."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return TruthOracleResult(
            TruthOracleClassification.BLOCK,
            "syntax",
            {"syntax_valid": False},
            f"strategy_source_syntax_error:{exc.msg}",
        )

    tokens = _source_tokens(tree)
    text = description.lower()
    has_compare = any(isinstance(node, ast.Compare) for node in ast.walk(tree))
    has_subtraction = any(
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
        for node in ast.walk(tree)
    )
    no_direct_broker_coupling = not _has_direct_broker_coupling(tree)

    if "orb" in text or "opening range" in text:
        checks = {
            "opening_window_reference": bool(
                tokens
                & {
                    "time",
                    "session",
                    "opening",
                    "open_range",
                    "range_high",
                    "range_low",
                }
            ),
            "breakout_comparison": has_compare,
            "no_direct_broker_coupling": no_direct_broker_coupling,
        }
        return _result("ORB", checks)

    if "vwap pullback" in text or "vwap reclaim" in text:
        checks = {
            "vwap_reference": "vwap" in tokens,
            "price_comparison": has_compare,
            "confirmation_reference": bool(
                tokens & {"confirm", "confirmation", "cross", "reclaim", "hold"}
            ),
            "no_direct_broker_coupling": no_direct_broker_coupling,
        }
        return _result("VWAP", checks)

    if "mean reversion" in text:
        checks = {
            "extension_measure": has_subtraction
            or bool(tokens & {"distance", "extension", "deviation"}),
            "exhaustion_reference": bool(
                tokens
                & {
                    "rsi",
                    "divergence",
                    "exhaustion",
                    "oversold",
                    "overbought",
                }
            ),
            "no_direct_broker_coupling": no_direct_broker_coupling,
        }
        return _result("MEAN_REVERSION", checks)

    if not no_direct_broker_coupling:
        return TruthOracleResult(
            TruthOracleClassification.BLOCK,
            "UNKNOWN",
            {"no_direct_broker_coupling": False},
            "direct_broker_or_order_coupling_detected",
        )
    return TruthOracleResult(
        TruthOracleClassification.UNABLE_TO_VERIFY,
        "UNKNOWN",
        {"no_direct_broker_coupling": True},
        "no_independent_oracle_for_declared_strategy_paradigm",
    )


def _source_tokens(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr.lower())
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tokens.add(node.name.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.update(part for part in _split_words(node.value.lower()) if part)
    return tokens


def _has_direct_broker_coupling(tree: ast.AST) -> bool:
    forbidden = {
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "kite_client",
        "execution_engine",
        "execution_router",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(any(token in alias.name.lower() for token in forbidden) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            if any(token in module for token in forbidden):
                return True
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id.lower()
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr.lower()
            else:
                name = ""
            if name in forbidden:
                return True
    return False


def _split_words(value: str) -> list[str]:
    translated = value
    for char in "-/:.,()[]{}":
        translated = translated.replace(char, " ")
    return translated.split()


def _result(paradigm: str, checks: dict[str, bool]) -> TruthOracleResult:
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        return TruthOracleResult(
            TruthOracleClassification.BLOCK,
            paradigm,
            checks,
            "missing_independent_oracle_checks:" + ",".join(missing),
        )
    return TruthOracleResult(
        TruthOracleClassification.PASS,
        paradigm,
        checks,
        "independent_ast_structure_verified",
    )


__all__ = [
    "TruthOracleClassification",
    "TruthOracleResult",
    "evaluate_truth_oracle",
]
