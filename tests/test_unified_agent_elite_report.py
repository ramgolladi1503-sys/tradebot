from __future__ import annotations

from tools.code_excellence.unified_agent_elite_report import (
    AGENT_ORDER,
    AgentEliteSignal,
    build_unified_agent_elite_report,
    render_markdown,
)


def _signals(verdict="PASS"):
    return tuple(AgentEliteSignal(agent=agent, verdict=verdict, summary=f"{agent} ok") for agent in AGENT_ORDER)


def test_critical_block_makes_unified_verdict_fail():
    signals = list(_signals())
    signals[2] = AgentEliteSignal(agent="Cerberus", verdict="BLOCK", blockers=("boundary violation",))

    report = build_unified_agent_elite_report(signals)

    assert report.verdict == "FAIL"
    assert "Cerberus: boundary violation" in report.blockers


def test_missing_agent_output_makes_unified_verdict_unknown():
    report = build_unified_agent_elite_report(_signals()[1:])

    assert report.verdict == "UNKNOWN"
    assert "Atlas: agent_output_missing" in report.unknowns


def test_warning_only_output_passes_with_warnings():
    signals = list(_signals())
    signals[4] = AgentEliteSignal(agent="Ariadne", verdict="WARN", warnings=("cluster incomplete",))

    report = build_unified_agent_elite_report(signals)

    assert report.verdict == "PASS_WITH_WARNINGS"
    assert "Ariadne: cluster incomplete" in report.warnings


def test_clean_outputs_pass_and_render_markdown():
    report = build_unified_agent_elite_report(_signals())
    rendered = render_markdown(report)

    assert report.verdict == "PASS"
    assert report.clean is True
    assert "# Unified Agent Elite Report" in rendered
    assert "verdict: PASS" in rendered
    assert "| Atlas | PASS | Atlas ok |" in rendered
