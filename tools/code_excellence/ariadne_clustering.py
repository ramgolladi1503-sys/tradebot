from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
DEFAULT_FINDING_TYPE = "unknown"
DEFAULT_ROOT_CAUSE_FAMILY = "unknown"


@dataclass(frozen=True)
class NormalizedFinding:
    finding_id: str
    title: str
    source_type: str
    finding_type: str = DEFAULT_FINDING_TYPE
    severity: str = "medium"
    confidence: str = "medium"
    root_cause_family: str = DEFAULT_ROOT_CAUSE_FAMILY
    observed_behavior: str = ""
    expected_behavior: str = ""
    files: tuple[str, ...] = ()
    related_findings: tuple[str, ...] = ()
    duplicate_of: str | None = None


@dataclass(frozen=True)
class AriadneCluster:
    cluster_id: str
    root_cause_family: str
    finding_type: str
    severity: str
    findings: tuple[NormalizedFinding, ...]
    duplicate_findings: tuple[NormalizedFinding, ...] = ()
    related_finding_ids: tuple[str, ...] = ()

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_findings)


@dataclass(frozen=True)
class AriadneClusteringReport:
    clusters: tuple[AriadneCluster, ...] = field(default_factory=tuple)
    rejected_findings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)

    @property
    def finding_count(self) -> int:
        return sum(cluster.finding_count for cluster in self.clusters)

    @property
    def duplicate_count(self) -> int:
        return sum(cluster.duplicate_count for cluster in self.clusters)


def load_normalized_findings(path: str | Path) -> list[NormalizedFinding]:
    """Load normalized findings from JSON without executing repo/product code.

    Accepted shapes:
    - a JSON list of finding objects
    - a JSON object with a `findings` list
    """

    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        raw_findings = data.get("findings", [])
    else:
        raw_findings = data
    if not isinstance(raw_findings, list):
        raise ValueError("normalized_findings_must_be_list")
    return [normalize_finding(item) for item in raw_findings if isinstance(item, Mapping)]


def normalize_finding(raw: Mapping[str, object]) -> NormalizedFinding:
    source = _mapping(raw.get("source"))
    classification = _mapping(raw.get("classification"))
    summary = _mapping(raw.get("summary"))
    location = _mapping(raw.get("location"))
    relationships = _mapping(raw.get("relationships"))

    finding_id = str(raw.get("finding_id") or "").strip()
    if not finding_id:
        raise ValueError("finding_id_required")

    return NormalizedFinding(
        finding_id=finding_id,
        title=str(summary.get("title") or finding_id).strip(),
        source_type=str(source.get("source_type") or "unknown").strip().lower(),
        finding_type=str(classification.get("finding_type") or DEFAULT_FINDING_TYPE).strip().lower(),
        severity=_normalize_severity(str(classification.get("severity") or "medium")),
        confidence=str(classification.get("confidence") or "medium").strip().lower(),
        root_cause_family=str(classification.get("root_cause_family") or DEFAULT_ROOT_CAUSE_FAMILY).strip().lower(),
        observed_behavior=str(summary.get("observed_behavior") or "").strip(),
        expected_behavior=str(summary.get("expected_behavior") or "").strip(),
        files=tuple(sorted(_string_list(location.get("files")))),
        related_findings=tuple(sorted(_string_list(relationships.get("related_findings")))),
        duplicate_of=_optional_str(relationships.get("duplicate_of")),
    )


def cluster_findings(findings: Iterable[NormalizedFinding]) -> AriadneClusteringReport:
    accepted: list[NormalizedFinding] = []
    duplicate_by_primary: dict[str, list[NormalizedFinding]] = defaultdict(list)
    rejected: list[str] = []
    finding_by_id: dict[str, NormalizedFinding] = {}

    for finding in sorted(findings, key=lambda item: item.finding_id):
        if finding.finding_id in finding_by_id:
            rejected.append(f"duplicate_finding_id:{finding.finding_id}")
            continue
        finding_by_id[finding.finding_id] = finding
        if finding.duplicate_of:
            duplicate_by_primary[finding.duplicate_of].append(finding)
        else:
            accepted.append(finding)

    grouped: dict[tuple[str, str], list[NormalizedFinding]] = defaultdict(list)
    for finding in accepted:
        grouped[(finding.root_cause_family or DEFAULT_ROOT_CAUSE_FAMILY, finding.finding_type or DEFAULT_FINDING_TYPE)].append(finding)

    clusters: list[AriadneCluster] = []
    for index, ((family, finding_type), group) in enumerate(sorted(grouped.items()), start=1):
        sorted_group = tuple(sorted(group, key=lambda item: item.finding_id))
        duplicate_findings = tuple(
            sorted(
                [duplicate for item in sorted_group for duplicate in duplicate_by_primary.get(item.finding_id, [])],
                key=lambda item: item.finding_id,
            )
        )
        related_ids = tuple(
            sorted(
                {
                    related_id
                    for item in sorted_group
                    for related_id in item.related_findings
                    if related_id in finding_by_id and related_id not in {member.finding_id for member in sorted_group}
                }
            )
        )
        clusters.append(
            AriadneCluster(
                cluster_id=f"ARIADNE-CLUSTER-{index:03d}",
                root_cause_family=family,
                finding_type=finding_type,
                severity=_max_severity([*sorted_group, *duplicate_findings]),
                findings=sorted_group,
                duplicate_findings=duplicate_findings,
                related_finding_ids=related_ids,
            )
        )
    return AriadneClusteringReport(clusters=tuple(clusters), rejected_findings=tuple(rejected))


def render_ariadne_cluster_report(report: AriadneClusteringReport) -> str:
    lines: list[str] = []
    lines.append("# Ariadne Root-Cause Clustering Report")
    lines.append("")
    lines.append("## Scope Guard")
    lines.append("")
    lines.append("- Static normalized-finding clustering only.")
    lines.append("- No product code execution.")
    lines.append("- No broker calls.")
    lines.append("- No auto-fix.")
    lines.append("- No remediation planning.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Clusters: `{report.cluster_count}`")
    lines.append(f"- Findings: `{report.finding_count}`")
    lines.append(f"- Duplicates: `{report.duplicate_count}`")
    lines.append(f"- Rejected findings: `{len(report.rejected_findings)}`")
    lines.append("")
    lines.append("## Clusters")
    lines.append("")
    lines.append("| Cluster | Root-Cause Family | Type | Severity | Findings | Duplicates | Related |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    for cluster in report.clusters:
        lines.append(
            f"| {cluster.cluster_id} | {cluster.root_cause_family} | {cluster.finding_type} | {cluster.severity} | {cluster.finding_count} | {cluster.duplicate_count} | {len(cluster.related_finding_ids)} |"
        )
    lines.append("")
    for cluster in report.clusters:
        lines.append(f"### {cluster.cluster_id} — {cluster.root_cause_family} / {cluster.finding_type}")
        lines.append("")
        lines.append(f"- Severity: `{cluster.severity}`")
        lines.append(f"- Related findings outside cluster: `{', '.join(cluster.related_finding_ids) if cluster.related_finding_ids else 'none'}`")
        lines.append("- Findings:")
        for finding in cluster.findings:
            lines.append(f"  - `{finding.finding_id}` {finding.title} ({finding.severity}, {finding.source_type})")
        lines.append("- Duplicates:")
        if cluster.duplicate_findings:
            for finding in cluster.duplicate_findings:
                lines.append(f"  - `{finding.finding_id}` duplicate_of=`{finding.duplicate_of}` {finding.title}")
        else:
            lines.append("  - none")
        lines.append("")
    if report.rejected_findings:
        lines.append("## Rejected Findings")
        lines.append("")
        for item in report.rejected_findings:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def write_ariadne_cluster_report(report: AriadneClusteringReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_ariadne_cluster_report(report), encoding="utf-8")
    return target


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_severity(value: str) -> str:
    lowered = value.strip().lower()
    return lowered if lowered in SEVERITY_ORDER else "medium"


def _max_severity(findings: Iterable[NormalizedFinding]) -> str:
    severities = [finding.severity for finding in findings]
    if not severities:
        return "info"
    return max(severities, key=lambda severity: SEVERITY_ORDER.get(severity, 0))
