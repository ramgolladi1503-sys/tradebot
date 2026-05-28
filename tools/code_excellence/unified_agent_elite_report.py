from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


PASS = "PASS"
PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
UNKNOWN = "UNKNOWN"
FAIL = "FAIL"

AGENT_ORDER = (
    "Atlas",
    "Minerva",
    "Cerberus",
    "Evidence Auditor",
    "Ariadne",
    "Daedalus",
    "Vulcan",
)

_FAIL_VERDICTS = {"FAIL", "FAILED", "BLOCK", "BLOCKED", "ERROR"}
_UNKNOWN_VERDICTS = {"UNKNOWN", "INCONCLUSIVE"}
_WARNING_VERDICTS = {"WARN", "WARNING", "PASS_WITH_WARNINGS"}
_PASS_VERDICTS = {"PASS", "SUCCESS", "OK"}


@dataclass(frozen=True)
class AgentEliteSignal:
    agent: str
    verdict: str
    summary: str = ""
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    unknowns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UnifiedAgentEliteReport:
    verdict: str
    agents: tuple[AgentEliteSignal, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    unknowns: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return self.verdict == PASS


def build_unified_agent_elite_report(
    signals: Iterable[AgentEliteSignal],
    required_agents: tuple[str, ...] = AGENT_ORDER,
) -> UnifiedAgentEliteReport:
    by_agent = {signal.agent: signal for signal in signals}
    ordered: list[AgentEliteSignal] = []
    blockers: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []

    for agent in required_agents:
        signal = by_agent.get(agent)
        if signal is None:
            signal = AgentEliteSignal(agent=agent, verdict=UNKNOWN, unknowns=("agent_output_missing",))
        normalized = _normalize_verdict(signal.verdict)
        ordered.append(signal)
        blockers.extend(f"{agent}: {item}" for item in signal.blockers)
        warnings.extend(f"{agent}: {item}" for item in signal.warnings)
        unknowns.extend(f"{agent}: {item}" for item in signal.unknowns)
        if normalized == FAIL and not signal.blockers:
            blockers.append(f"{agent}: critical_block")
        if normalized == UNKNOWN and not signal.unknowns:
            unknowns.append(f"{agent}: unknown_verdict")
        if normalized == PASS_WITH_WARNINGS and not signal.warnings:
            warnings.append(f"{agent}: warning_verdict")

    verdict = _overall_verdict(ordered, blockers, warnings, unknowns)
    return UnifiedAgentEliteReport(
        verdict=verdict,
        agents=tuple(ordered),
        blockers=tuple(_ordered_unique(blockers)),
        warnings=tuple(_ordered_unique(warnings)),
        unknowns=tuple(_ordered_unique(unknowns)),
    )


def signal_from_mapping(payload: Mapping[str, object]) -> AgentEliteSignal:
    agent = str(payload.get("agent") or payload.get("name") or "UNKNOWN")
    verdict = str(payload.get("verdict") or payload.get("status") or UNKNOWN)
    summary = str(payload.get("summary") or payload.get("reason") or "")
    return AgentEliteSignal(
        agent=agent,
        verdict=verdict,
        summary=summary,
        blockers=tuple(str(item) for item in payload.get("blockers", ()) or ()),
        warnings=tuple(str(item) for item in payload.get("warnings", ()) or ()),
        unknowns=tuple(str(item) for item in payload.get("unknowns", ()) or ()),
    )


def render_markdown(report: UnifiedAgentEliteReport) -> str:
    lines = [
        "# Unified Agent Elite Report",
        "",
        f"verdict: {report.verdict}",
        "",
        "## Agent Summary",
        "",
        "| Agent | Verdict | Summary |",
        "| --- | --- | --- |",
    ]
    for signal in report.agents:
        lines.append(f"| {signal.agent} | {_normalize_verdict(signal.verdict)} | {_escape_table(signal.summary)} |")

    lines.extend(["", "## Blockers", ""])
    lines.extend(_markdown_items(report.blockers))
    lines.extend(["", "## Warnings", ""])
    lines.extend(_markdown_items(report.warnings))
    lines.extend(["", "## Unknowns", ""])
    lines.extend(_markdown_items(report.unknowns))
    lines.append("")
    return "\n".join(lines)


def _overall_verdict(
    signals: tuple[AgentEliteSignal, ...],
    blockers: list[str],
    warnings: list[str],
    unknowns: list[str],
) -> str:
    normalized = [_normalize_verdict(signal.verdict) for signal in signals]
    if blockers or FAIL in normalized:
        return FAIL
    if unknowns or UNKNOWN in normalized:
        return UNKNOWN
    if warnings or PASS_WITH_WARNINGS in normalized:
        return PASS_WITH_WARNINGS
    return PASS


def _normalize_verdict(value: str) -> str:
    upper = value.strip().upper().replace("-", "_").replace(" ", "_")
    if upper in _FAIL_VERDICTS:
        return FAIL
    if upper in _UNKNOWN_VERDICTS:
        return UNKNOWN
    if upper in _WARNING_VERDICTS:
        return PASS_WITH_WARNINGS
    if upper in _PASS_VERDICTS:
        return PASS
    return UNKNOWN


def _markdown_items(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
