from __future__ import annotations

import json

from tools.code_excellence.ariadne_clustering import (
    cluster_findings,
    load_normalized_findings,
    normalize_finding,
    render_ariadne_cluster_report,
)


def _finding(
    finding_id,
    *,
    family="propagation_gap",
    finding_type="contract_violation",
    severity="high",
    related=None,
    duplicate_of=None,
):
    return {
        "finding_id": finding_id,
        "source": {"source_type": "runtime_log"},
        "classification": {
            "finding_type": finding_type,
            "severity": severity,
            "confidence": "high",
            "root_cause_family": family,
        },
        "summary": {
            "title": f"Finding {finding_id}",
            "observed_behavior": "observed",
            "expected_behavior": "expected",
        },
        "location": {"files": ["core/review_queue.py"]},
        "relationships": {
            "related_findings": related or [],
            "duplicate_of": duplicate_of,
        },
    }


def test_normalize_finding_extracts_required_fields():
    finding = normalize_finding(_finding("CE-FINDING-1", severity="critical"))

    assert finding.finding_id == "CE-FINDING-1"
    assert finding.finding_type == "contract_violation"
    assert finding.root_cause_family == "propagation_gap"
    assert finding.severity == "critical"
    assert finding.files == ("core/review_queue.py",)


def test_cluster_findings_groups_by_family_and_type_deterministically():
    findings = [
        normalize_finding(_finding("CE-FINDING-2", family="evidence_gap", finding_type="evidence_gap", severity="medium")),
        normalize_finding(_finding("CE-FINDING-1", family="propagation_gap", finding_type="contract_violation", severity="critical")),
        normalize_finding(_finding("CE-FINDING-3", family="propagation_gap", finding_type="contract_violation", severity="high")),
    ]

    report = cluster_findings(findings)

    assert report.cluster_count == 2
    first = report.clusters[0]
    second = report.clusters[1]
    assert first.cluster_id == "ARIADNE-CLUSTER-001"
    assert first.root_cause_family == "evidence_gap"
    assert second.root_cause_family == "propagation_gap"
    assert second.severity == "critical"
    assert [item.finding_id for item in second.findings] == ["CE-FINDING-1", "CE-FINDING-3"]


def test_cluster_findings_preserves_duplicates_and_related_ids():
    findings = [
        normalize_finding(_finding("CE-FINDING-1", related=["CE-FINDING-3"])),
        normalize_finding(_finding("CE-FINDING-2", duplicate_of="CE-FINDING-1")),
        normalize_finding(_finding("CE-FINDING-3", family="safety_boundary_gap", finding_type="safety_boundary_gap")),
    ]

    report = cluster_findings(findings)
    propagation_cluster = next(cluster for cluster in report.clusters if cluster.root_cause_family == "propagation_gap")

    assert propagation_cluster.duplicate_count == 1
    assert propagation_cluster.duplicate_findings[0].finding_id == "CE-FINDING-2"
    assert propagation_cluster.related_finding_ids == ("CE-FINDING-3",)


def test_load_normalized_findings_accepts_dict_with_findings_list(tmp_path):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps({"findings": [_finding("CE-FINDING-1")]}), encoding="utf-8")

    findings = load_normalized_findings(path)

    assert len(findings) == 1
    assert findings[0].finding_id == "CE-FINDING-1"


def test_render_ariadne_cluster_report_contains_scope_guard_and_clusters():
    report = cluster_findings([normalize_finding(_finding("CE-FINDING-1"))])

    markdown = render_ariadne_cluster_report(report)

    assert "# Ariadne Root-Cause Clustering Report" in markdown
    assert "No auto-fix" in markdown
    assert "ARIADNE-CLUSTER-001" in markdown
    assert "CE-FINDING-1" in markdown
