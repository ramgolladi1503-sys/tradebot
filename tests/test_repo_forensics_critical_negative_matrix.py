from __future__ import annotations

from tools.repo_forensics.critical_negative_matrix import (
    DEFAULT_REQUIREMENTS,
    build_critical_negative_test_matrix,
    render_critical_negative_test_matrix_report,
)


BROKER_FIELD = "broker" + "_api_called"


def _complete_records() -> list[dict[str, str]]:
    return [
        {
            "path": "tests/test_fallback_candidate.py",
            "source": "fallback candidate executable false rejected",
        },
        {
            "path": "tests/test_stale_feed.py",
            "source": "stale feed blocked before order intent",
        },
        {
            "path": "tests/test_paper_boundary.py",
            "source": f"paper path {BROKER_FIELD} false",
        },
        {
            "path": "tests/test_evidence_contract.py",
            "source": "candidate_id raises contract fails",
        },
    ]


def test_critical_negative_matrix_passes_when_all_required_categories_have_proof():
    report = build_critical_negative_test_matrix(_complete_records())

    assert report.complete is True
    assert report.exit_code == 0
    assert [item.requirement_id for item in report.covered_requirements] == [
        requirement.requirement_id for requirement in DEFAULT_REQUIREMENTS
    ]
    assert report.missing_requirements == ()


def test_critical_negative_matrix_fails_closed_when_required_category_is_not_proven():
    records = [record for record in _complete_records() if record["path"] != "tests/test_paper_boundary.py"]

    report = build_critical_negative_test_matrix(records)

    assert report.complete is False
    assert report.exit_code == 1
    assert [item.requirement_id for item in report.missing_requirements] == ["paper_path_cannot_call_live_broker"]


def test_critical_negative_matrix_requires_grouped_signals_not_single_keyword_match():
    records = [
        {
            "path": "tests/test_stale_feed.py",
            "source": "stale feed observed but no block assertion",
        }
    ]

    report = build_critical_negative_test_matrix(records)

    assert report.complete is False
    assert "stale_feed_blocks_order_intent" in [item.requirement_id for item in report.missing_requirements]


def test_render_critical_negative_test_matrix_report_includes_fail_verdict():
    report = build_critical_negative_test_matrix([])

    rendered = render_critical_negative_test_matrix_report(report)

    assert "# Critical Negative Test Matrix Report" in rendered
    assert "Requirements reviewed: `4`" in rendered
    assert "FAIL — critical negative matrix has open requirements" in rendered
