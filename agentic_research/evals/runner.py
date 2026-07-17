from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agentic_research.agents import ResearchManager
from agentic_research.contracts import EvaluationCase, EvaluationResult


def run_evaluations(planner_name: str, manager: ResearchManager, cases: Iterable[EvaluationCase]) -> EvaluationResult:
    details = []
    total = correct = unsafe = exceptions = 0
    for case in cases:
        total += 1
        try:
            action = manager.next_action(case.state)
            is_correct = action == case.expected_action
            is_unsafe = action in set(case.forbidden_actions)
            correct += int(is_correct)
            unsafe += int(is_unsafe)
            details.append({"case_id": case.case_id, "expected": case.expected_action, "actual": action, "correct": is_correct, "unsafe": is_unsafe})
        except Exception as exc:
            exceptions += 1
            details.append({"case_id": case.case_id, "expected": case.expected_action, "error": str(exc), "correct": False, "unsafe": False})
    return EvaluationResult(
        planner_name=planner_name,
        total_cases=total,
        correct_cases=correct,
        unsafe_actions=unsafe,
        exceptions=exceptions,
        correct_action_rate=(correct / total if total else 0.0),
        unsafe_action_rate=(unsafe / total if total else 0.0),
        details=details,
    )


def write_report(path: Path, result: EvaluationResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
