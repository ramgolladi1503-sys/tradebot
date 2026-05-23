from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_compose_adds_loki_and_promtail_as_local_services() -> None:
    compose = _read("docker-compose.observability.yml")

    assert "loki:" in compose
    assert "grafana/loki:3.2.1" in compose
    assert "3100:3100" in compose
    assert "promtail:" in compose
    assert "grafana/promtail:3.2.1" in compose
    assert "depends_on:" in compose
    assert "- loki" in compose


def test_promtail_mounts_only_log_directories_read_only() -> None:
    compose = _read("docker-compose.observability.yml")

    assert "./observability/promtail-config.yaml:/etc/promtail/config.yaml:ro" in compose
    assert "./logs:/var/log/tradebot/logs:ro" in compose
    assert "./runtime:/var/log/tradebot/runtime:ro" in compose
    assert "./:/" not in compose
    assert ":rw" not in compose


def test_grafana_has_loki_datasource() -> None:
    datasources = _read("observability/grafana/provisioning/datasources/datasources.yml")

    assert "name: Loki" in datasources
    assert "type: loki" in datasources
    assert "url: http://loki:3100" in datasources
    assert "editable: false" in datasources


def test_loki_config_is_local_short_retention_and_filesystem_backed() -> None:
    loki = _read("observability/loki-config.yaml")

    assert "auth_enabled: false" in loki
    assert "http_listen_port: 3100" in loki
    assert "object_store: filesystem" in loki
    assert "replication_factor: 1" in loki
    assert "retention_period: 24h" in loki


def test_promtail_extracts_required_correlation_fields_without_high_cardinality_labels() -> None:
    promtail = _read("observability/promtail-config.yaml")

    for field in (
        "trace_id",
        "candidate_id",
        "cycle_id",
        "run_id",
        "strategy_id",
        "stage",
        "decision",
        "reason",
        "fallback_state",
        "execution_mode",
    ):
        assert f"{field}:" in promtail

    labels_section = promtail.split("- labels:", maxsplit=1)[1].split("- structured_metadata:", maxsplit=1)[0]
    assert "execution_mode:" in labels_section
    assert "trace_id:" not in labels_section
    assert "candidate_id:" not in labels_section
    assert "cycle_id:" not in labels_section
    assert "run_id:" not in labels_section


def test_log_correlation_doc_records_queries_acceptance_and_limits() -> None:
    doc = _read("docs/observability/LOG_CORRELATION.md")

    assert "PR-OBS-11" in doc
    assert "Loki" in doc
    assert "Promtail" in doc
    assert "trace_id" in doc
    assert "candidate_id" in doc
    assert "cycle_id" in doc
    assert "docker compose -f docker-compose.observability.yml up --build" in doc
    assert "read-only" in doc
    assert "does not wire runtime code" in doc
