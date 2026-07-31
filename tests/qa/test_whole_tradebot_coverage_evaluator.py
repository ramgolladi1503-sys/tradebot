from __future__ import annotations

from pathlib import Path

from tools.qa_certification import evaluate_coverage as coverage_module
from tools.qa_certification.whole_tradebot_manifest import CertificationArea


def _coverage(path: str, *, statements: int = 10, covered: int = 10, branches: int = 4, covered_branches: int = 4):
    return {
        "files": {
            path: {
                "summary": {
                    "num_statements": statements,
                    "covered_lines": covered,
                    "num_branches": branches,
                    "covered_branches": covered_branches,
                }
            }
        }
    }


def test_evaluator_passes_only_when_module_exists_is_measured_and_meets_thresholds(tmp_path, monkeypatch):
    module_path = "core/example.py"
    target = tmp_path / module_path
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        coverage_module,
        "WHOLE_TRADEBOT_AREAS",
        (
            CertificationArea(
                name="example",
                tier="A",
                line_min=100.0,
                branch_min=100.0,
                modules=(module_path,),
                required_test_families=("behavior",),
            ),
        ),
    )

    report = coverage_module.evaluate_coverage(_coverage(module_path), repo_root=tmp_path)

    assert report["verdict"] == "PASS"
    assert report["hard_failure_count"] == 0
    assert report["areas"][0]["modules"][0]["passed"] is True


def test_evaluator_fails_closed_for_unmeasured_module(tmp_path, monkeypatch):
    module_path = "core/example.py"
    target = tmp_path / module_path
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        coverage_module,
        "WHOLE_TRADEBOT_AREAS",
        (
            CertificationArea(
                name="example",
                tier="A",
                line_min=100.0,
                branch_min=100.0,
                modules=(module_path,),
                required_test_families=("safety",),
            ),
        ),
    )

    report = coverage_module.evaluate_coverage({"files": {}}, repo_root=tmp_path)

    assert report["verdict"] == "FAIL"
    failure = report["hard_failures"][0]
    assert failure["path"] == module_path
    assert "module_unmeasured" in failure["reasons"]


def test_evaluator_fails_for_missing_module_even_with_fabricated_coverage(tmp_path, monkeypatch):
    module_path = "core/missing.py"
    monkeypatch.setattr(
        coverage_module,
        "WHOLE_TRADEBOT_AREAS",
        (
            CertificationArea(
                name="example",
                tier="A",
                line_min=90.0,
                branch_min=80.0,
                modules=(module_path,),
                required_test_families=("behavior",),
            ),
        ),
    )

    report = coverage_module.evaluate_coverage(_coverage(module_path), repo_root=tmp_path)

    assert report["verdict"] == "FAIL"
    assert "configured_module_missing" in report["hard_failures"][0]["reasons"]


def test_evaluator_reports_line_and_branch_failures_independently(tmp_path, monkeypatch):
    module_path = "core/example.py"
    target = tmp_path / module_path
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        coverage_module,
        "WHOLE_TRADEBOT_AREAS",
        (
            CertificationArea(
                name="example",
                tier="B",
                line_min=95.0,
                branch_min=90.0,
                modules=(module_path,),
                required_test_families=("regression",),
            ),
        ),
    )

    report = coverage_module.evaluate_coverage(
        _coverage(module_path, statements=100, covered=94, branches=10, covered_branches=8),
        repo_root=tmp_path,
    )

    reasons = report["hard_failures"][0]["reasons"]
    assert "line_coverage_below_threshold" in reasons
    assert "branch_coverage_below_threshold" in reasons
    assert report["areas"][0]["modules"][0]["line_pct"] == 94.0
    assert report["areas"][0]["modules"][0]["branch_pct"] == 80.0


def test_markdown_contains_area_and_module_evidence(tmp_path, monkeypatch):
    module_path = "core/example.py"
    target = tmp_path / module_path
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        coverage_module,
        "WHOLE_TRADEBOT_AREAS",
        (
            CertificationArea(
                name="example",
                tier="A",
                line_min=100.0,
                branch_min=100.0,
                modules=(module_path,),
                required_test_families=("behavior",),
            ),
        ),
    )

    report = coverage_module.evaluate_coverage(_coverage(module_path), repo_root=tmp_path)
    markdown = coverage_module.render_markdown(report)

    assert "Verdict: **PASS**" in markdown
    assert "example" in markdown
    assert f"`{module_path}`" in markdown
