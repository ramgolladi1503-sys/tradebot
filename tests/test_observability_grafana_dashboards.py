from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.observability.yml"
PROVIDER_FILE = ROOT / "observability/grafana/provisioning/dashboards/dashboards.yml"
DASHBOARD_FILE = ROOT / "observability/grafana/dashboards/tradebot-observability-spine.json"
DOC_FILE = ROOT / "docs/observability/GRAFANA_DASHBOARDS.md"


FORBIDDEN_RUNTIME_HOOKS = (
    "run_live.sh",
    "main.py",
    "place_order",
    "modify_order",
    "cancel_order",
    "KITE_API_KEY",
    "KITE_ACCESS_TOKEN",
)


REQUIRED_PANEL_TITLES = {
    "Metrics Endpoint Up",
    "Runtime Cycles Observed",
    "Candidate Events Observed",
    "Blocked Candidate Reasons",
    "Downgraded Candidate Reasons",
    "Fallback Safety Signals",
    "Feed Freshness Signals",
    "Observability Pipeline Metrics",
}


REQUIRED_PROMQL_EXPRESSIONS = {
    'up{job="tradebot-metrics"}',
    "tradebot_runtime_cycles_total",
    "tradebot_candidate_events_total",
    "tradebot_candidate_blocked_total",
    "tradebot_candidate_downgraded_total",
    "tradebot_fallback_events_total",
    "tradebot_feed_freshness_state_total",
    "otelcol_receiver_accepted_metric_points",
    "otelcol_exporter_sent_metric_points",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dashboard() -> dict:
    return json.loads(_read(DASHBOARD_FILE))


def test_grafana_dashboard_provider_is_mounted_read_only() -> None:
    compose = _read(COMPOSE_FILE)

    assert "./observability/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro" in compose
    assert "./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro" in compose
    assert "./observability/grafana/provisioning/datasources:/etc/grafana/provisioning/datasources:ro" in compose


def test_dashboard_provider_loads_dashboard_directory() -> None:
    provider = _read(PROVIDER_FILE)

    assert "apiVersion: 1" in provider
    assert "type: file" in provider
    assert "editable: false" in provider
    assert "path: /var/lib/grafana/dashboards" in provider
    assert "Tradebot Observability" in provider


def test_dashboard_json_is_valid_and_uses_prometheus_datasource() -> None:
    dashboard = _dashboard()

    assert dashboard["uid"] == "tradebot-observability-spine"
    assert dashboard["title"] == "Tradebot Observability Spine"
    assert dashboard["refresh"] == "15s"
    assert dashboard["panels"]

    for panel in dashboard["panels"]:
        assert panel["datasource"] == {"type": "prometheus", "uid": "prometheus"}


def test_dashboard_contains_required_debugging_panels() -> None:
    dashboard = _dashboard()
    panel_titles = {panel["title"] for panel in dashboard["panels"]}

    assert REQUIRED_PANEL_TITLES <= panel_titles


def test_dashboard_contains_expected_promql_only() -> None:
    dashboard = _dashboard()
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }

    assert REQUIRED_PROMQL_EXPRESSIONS <= expressions
    assert all("append=true" not in expr for expr in expressions)
    assert all("broker" not in expr.lower() for expr in expressions)


def test_dashboard_provisioning_has_no_runtime_or_secret_hooks() -> None:
    combined = "\n".join(
        _read(path)
        for path in (COMPOSE_FILE, PROVIDER_FILE, DASHBOARD_FILE, DOC_FILE)
    )

    for forbidden in FORBIDDEN_RUNTIME_HOOKS:
        assert forbidden not in combined


def test_dashboard_documentation_records_limits_and_acceptance() -> None:
    doc = _read(DOC_FILE)

    assert "configuration, documentation, and static validation only" in doc
    assert "Some panels may show no data" in doc
    assert "python -m pytest tests/test_observability_grafana_dashboards.py tests/test_observability_local_stack.py" in doc
    assert "does not prove profitability" in doc
