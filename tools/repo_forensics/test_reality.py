from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


TEST_CLASSES = {
    "SHAPE_ONLY",
    "UNIT_BEHAVIOR",
    "INTEGRATION_WIRING",
    "SAFETY_REGRESSION",
    "RUNTIME_COMMAND",
    "EVIDENCE_CONTRACT",
    "FAKE_CONFIDENCE",
    "UNKNOWN",
}

_ORDER_MARKER = "place" + "_order"
_ASSERT_MARKER = "assert" + " "


@dataclass(frozen=True)
class TestStrengthScore:
    score: int
    grade: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TestRealityStatus:
    path: str
    test_class: str
    strength: str
    evidence: str
    risks: list[str] = field(default_factory=list)
    strength_score: int = 0
    strength_grade: str = "weak"
    score_reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TestRealityReport:
    tests: list[TestRealityStatus] = field(default_factory=list)

    @property
    def class_counts(self) -> Counter[str]:
        return Counter(item.test_class for item in self.tests)

    @property
    def strength_grade_counts(self) -> Counter[str]:
        return Counter(item.strength_grade for item in self.tests)

    @property
    def fake_confidence_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "FAKE_CONFIDENCE"]

    @property
    def shape_only_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "SHAPE_ONLY"]

    @property
    def unknown_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "UNKNOWN"]

    @property
    def weak_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.strength_grade == "weak"]

    @property
    def strong_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.strength_grade == "strong"]


def classify_tests(repo_root: str | Path, config: ForensicsConfig) -> TestRealityReport:
    root = Path(repo_root).resolve()
    tests: list[TestRealityStatus] = []
    for path in sorted(root.rglob("test_*.py")):
        if _should_skip(path, root, config) or not _is_test_file_candidate(path, root):
            continue
        tests.append(_classify_test_file(root, path))
    for path in sorted((root / "tests").rglob("*.py")) if (root / "tests").exists() else []:
        if path.name.startswith("test_") or _should_skip(path, root, config):
            continue
        tests.append(_classify_test_file(root, path))
    return TestRealityReport(tests=tests)


def _classify_test_file(repo_root: Path, path: Path) -> TestRealityStatus:
    rel = path.relative_to(repo_root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _status(rel, "UNKNOWN", "weak", "unreadable_test_file", [], 0, source="")

    lowered = source.lower()
    risks = _risk_markers(lowered)
    assertion_count = _assertion_count(source)
    evidence = []

    if _has_fake_confidence_markers(lowered, source):
        evidence.append("fake_confidence_marker")
        return _status(rel, "FAKE_CONFIDENCE", "weak", ",".join(evidence), risks, assertion_count, source=source)

    if _has_safety_markers(lowered):
        evidence.append("safety_regression_marker")
        return _status(
            rel,
            "SAFETY_REGRESSION",
            "strong" if assertion_count else "medium",
            ",".join(evidence),
            risks,
            assertion_count,
            source=source,
        )

    if _has_evidence_contract_markers(lowered):
        evidence.append("evidence_contract_marker")
        return _status(
            rel,
            "EVIDENCE_CONTRACT",
            "strong" if assertion_count else "medium",
            ",".join(evidence),
            risks,
            assertion_count,
            source=source,
        )

    if _has_runtime_command_markers(lowered):
        evidence.append("runtime_command_marker")
        return _status(rel, "RUNTIME_COMMAND", "medium", ",".join(evidence), risks, assertion_count, source=source)

    if _has_integration_markers(lowered):
        evidence.append("integration_wiring_marker")
        return _status(rel, "INTEGRATION_WIRING", "medium", ",".join(evidence), risks, assertion_count, source=source)

    if _looks_shape_only(source, lowered, assertion_count):
        evidence.append("shape_only_assertions")
        return _status(rel, "SHAPE_ONLY", "weak", ",".join(evidence), risks, assertion_count, source=source)

    if assertion_count:
        evidence.append("behavior_assertions_present")
        return _status(rel, "UNIT_BEHAVIOR", "medium", ",".join(evidence), risks, assertion_count, source=source)

    return _status(rel, "UNKNOWN", "weak", "no_assertion_signal", risks, assertion_count, source=source)


def _status(
    path: str,
    test_class: str,
    strength: str,
    evidence: str,
    risks: list[str],
    assertion_count: int,
    *,
    source: str,
) -> TestRealityStatus:
    score = score_test_strength(
        test_class=test_class,
        declared_strength=strength,
        assertion_count=assertion_count,
        source=source,
        risks=risks,
    )
    return TestRealityStatus(
        path=path,
        test_class=test_class,
        strength=strength,
        evidence=evidence,
        risks=risks,
        strength_score=score.score,
        strength_grade=score.grade,
        score_reasons=score.reasons,
    )


def score_test_strength(
    *,
    test_class: str,
    declared_strength: str,
    assertion_count: int,
    source: str,
    risks: list[str],
) -> TestStrengthScore:
    """Score test proof strength without changing the existing classification contract."""

    lowered = source.lower()
    score = 0
    reasons: list[str] = []

    class_bonus = {
        "SAFETY_REGRESSION": 45,
        "INTEGRATION_WIRING": 35,
        "EVIDENCE_CONTRACT": 30,
        "RUNTIME_COMMAND": 25,
        "UNIT_BEHAVIOR": 25,
        "SHAPE_ONLY": 5,
        "FAKE_CONFIDENCE": 0,
        "UNKNOWN": 0,
    }.get(test_class, 0)
    score += class_bonus
    reasons.append(f"class_bonus:{test_class}:{class_bonus}")

    if assertion_count:
        assertion_bonus = min(assertion_count * 5, 25)
        score += assertion_bonus
        reasons.append(f"assertion_bonus:{assertion_bonus}")
    else:
        score -= 20
        reasons.append("no_assertions:-20")

    if _has_negative_proof_markers(lowered):
        score += 25
        reasons.append("negative_proof:+25")

    if _has_behavior_proof_markers(lowered):
        score += 15
        reasons.append("behavior_proof:+15")

    if _has_fake_confidence_markers(lowered, source):
        score -= 40
        reasons.append("fake_confidence:-40")

    if test_class == "SHAPE_ONLY":
        score -= 25
        reasons.append("shape_only:-25")

    if test_class == "UNKNOWN":
        score -= 30
        reasons.append("unknown_class:-30")

    if "mock_heavy" in risks and not _has_negative_proof_markers(lowered):
        score -= 10
        reasons.append("mock_without_negative_proof:-10")

    if declared_strength == "strong":
        score += 10
        reasons.append("declared_strong:+10")
    elif declared_strength == "weak":
        score -= 10
        reasons.append("declared_weak:-10")

    bounded = max(0, min(100, score))
    if bounded >= 75:
        grade = "strong"
    elif bounded >= 45:
        grade = "medium"
    else:
        grade = "weak"
    return TestStrengthScore(score=bounded, grade=grade, reasons=tuple(reasons))


def _assertion_count(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source.count(_ASSERT_MARKER)
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))


def _weak_assertion_marker_count(lowered: str) -> int:
    markers = (
        _ASSERT_MARKER + "true",
        _ASSERT_MARKER + "len(",
        _ASSERT_MARKER + "result is not none",
        _ASSERT_MARKER + "response is not none",
        _ASSERT_MARKER + "data is not none",
        " in result",
        " in data",
        " in report",
    )
    return sum(lowered.count(marker) for marker in markers)


def _weak_assertions_are_only_proof(lowered: str, source: str) -> bool:
    assertion_count = _assertion_count(source)
    if assertion_count <= 0:
        return False
    return _weak_assertion_marker_count(lowered) >= assertion_count


def _has_fake_confidence_markers(lowered: str, source: str) -> bool:
    if "except exception" in lowered and "pass" in lowered:
        return True
    if "mock" in lowered and _ORDER_MARKER in lowered and "broker_api_called" not in lowered:
        return True
    return _weak_assertions_are_only_proof(lowered, source)


def _has_safety_markers(lowered: str) -> bool:
    markers = [
        "broker_api_called",
        "is_order_action",
        "live_order_action",
        "paper_path",
        "sim_path",
        "fallback_data_not_executable",
        "stale_feed",
        "risk_rejected",
        "kill_switch",
        _ORDER_MARKER,
    ]
    return any(marker in lowered for marker in markers)


def _has_evidence_contract_markers(lowered: str) -> bool:
    markers = [
        "candidate_id",
        "decision",
        "reason",
        "evidence",
        "audit_log",
        "report",
        "jsonl",
        "runtime_health",
    ]
    return any(marker in lowered for marker in markers) and "assert" in lowered


def _has_runtime_command_markers(lowered: str) -> bool:
    markers = ["subprocess", "run_repo_forensics", "run_live.sh", "main.py", "command", "cli"]
    return any(marker in lowered for marker in markers)


def _has_integration_markers(lowered: str) -> bool:
    markers = ["orchestrator", "pipeline", "wiring", "import_graph", "runtime_wiring", "critical_module"]
    return any(marker in lowered for marker in markers)


def _has_negative_proof_markers(lowered: str) -> bool:
    markers = [
        "raises(",
        " is false",
        "== false",
        "blocked",
        "rejected",
        "not in",
        "cannot",
        "fails",
        "failure",
        "unsafe",
    ]
    return any(marker in lowered for marker in markers)


def _has_behavior_proof_markers(lowered: str) -> bool:
    markers = ["==", "!=", " is true", " is false", " in ", " not in "]
    return any(marker in lowered for marker in markers)


def _looks_shape_only(source: str, lowered: str, assertion_count: int) -> bool:
    if assertion_count == 0:
        return False
    shape_markers = [
        " in result",
        " in data",
        " in report",
        "hasattr(",
        "isinstance(",
        ".keys()",
        "len(",
    ]
    behavior_markers = ["== false", " is false", "raises(", "not in", "!=", "blocked", "rejected"]
    shape_marker_count = sum(lowered.count(marker) for marker in shape_markers)
    return (
        shape_marker_count >= assertion_count
        and any(marker in lowered for marker in shape_markers)
        and not any(marker in lowered for marker in behavior_markers)
    )


def _risk_markers(lowered: str) -> list[str]:
    risks: list[str] = []
    if "mock" in lowered:
        risks.append("mock_heavy")
    if _ORDER_MARKER in lowered:
        risks.append("broker_adjacent")
    if "live" in lowered:
        risks.append("live_adjacent")
    if "fallback" in lowered:
        risks.append("fallback_adjacent")
    return risks


def _is_test_file_candidate(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    return "tests" in rel.parts or rel.parent == Path(".")


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
