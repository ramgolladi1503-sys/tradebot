from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_local_observability_compose_declares_required_services_and_ports() -> None:
    compose = _read("docker-compose.observability.yml")

    for service in (
        "tradebot-metrics:",
        "otel-collector:",
        "prometheus:",
        "tempo:",
        "grafana:",
    ):
        assert service in compose

    for port in (
        "9108:9108",
        "4317:4317",
        "4318:4318",
        "8888:8888",
        "8889:8889",
        "9090:9090",
        "3200:3200",
        "3000:3000",
    ):
        assert port in compose


def test_local_observability_compose_does_not_start_trading_runtime_or_broker_paths() -> None:
    compose = _read("docker-compose.observability.yml")

    assert "scripts/run_metrics_server.py" in compose
    assert "run_live.sh" not in compose
    assert "main.py" not in compose
    assert "core/orchestrator.py" not in compose
    assert "KITE_USE_API: \"false\"" in compose
    assert "EXECUTION_MODE: PAPER" in compose


def test_prometheus_scrapes_tradebot_metrics_and_collector_exporters() -> None:
    prometheus = _read("observability/prometheus.yml")

    assert "job_name: tradebot-metrics" in prometheus
    assert "tradebot-metrics:9108" in prometheus
    assert "job_name: otel-collector" in prometheus
    assert "otel-collector:8888" in prometheus
    assert "otel-collector:8889" in prometheus


def test_otel_collector_routes_traces_to_tempo_and_metrics_to_prometheus_exporter() -> None:
    config = _read("observability/otel-collector-config.yaml")

    assert "endpoint: 0.0.0.0:4317" in config
    assert "endpoint: 0.0.0.0:4318" in config
    assert "otlp/tempo:" in config
    assert "endpoint: tempo:4317" in config
    assert "prometheus:" in config
    assert "endpoint: 0.0.0.0:8889" in config
    assert "traces:" in config
    assert "metrics:" in config


def test_tempo_and_grafana_configs_are_local_and_preprovisioned() -> None:
    tempo = _read("observability/tempo.yaml")
    datasources = _read("observability/grafana/provisioning/datasources/datasources.yml")

    assert "http_listen_port: 3200" in tempo
    assert "backend: local" in tempo
    assert "name: Prometheus" in datasources
    assert "url: http://prometheus:9090" in datasources
    assert "name: Tempo" in datasources
    assert "url: http://tempo:3200" in datasources


def test_local_setup_doc_records_manual_acceptance_and_limits() -> None:
    doc = _read("docs/observability/LOCAL_OBSERVABILITY_SETUP.md")

    assert "docker compose -f docker-compose.observability.yml up --build" in doc
    assert "Tradebot metrics: http://127.0.0.1:9108/metrics" in doc
    assert "Prometheus:       http://127.0.0.1:9090" in doc
    assert "Grafana:          http://127.0.0.1:3000" in doc
    assert "must not:" in doc
    assert "call broker APIs" in doc
    assert "place orders" in doc
    assert "This PR only adds the local free stack configuration" in doc
