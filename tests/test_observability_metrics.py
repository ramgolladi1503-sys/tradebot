from __future__ import annotations

from urllib.request import urlopen

import pytest

from core.observability import (
    DEFAULT_OBSERVABILITY_METRICS,
    ObservabilityMetricError,
    ObservabilityMetricsRegistry,
    build_default_metrics_registry,
)
from scripts.run_metrics_server import build_server


def test_default_registry_declares_required_metrics() -> None:
    registry = build_default_metrics_registry()

    assert "tradebot_feed_age_ms" in DEFAULT_OBSERVABILITY_METRICS
    assert "tradebot_feed_stale_total" in DEFAULT_OBSERVABILITY_METRICS
    assert "tradebot_candidates_generated_total" in DEFAULT_OBSERVABILITY_METRICS
    assert "tradebot_fallback_executable_total" in DEFAULT_OBSERVABILITY_METRICS
    assert registry.get_value("tradebot_fallback_executable_total") == 0


def test_metrics_render_prometheus_text_format() -> None:
    registry = build_default_metrics_registry()
    registry.set_gauge("tradebot_feed_age_ms", 4200, labels={"symbol": "NIFTY"})
    registry.increment_counter("tradebot_feed_stale_total", labels={"reason": "STALE_FEED"})
    registry.increment_counter("tradebot_candidates_blocked_total", amount=2, labels={"reason": "RISK_BLOCK"})

    rendered = registry.render_prometheus()

    assert "# HELP tradebot_feed_age_ms Tradebot observability metric" in rendered
    assert "# TYPE tradebot_feed_age_ms gauge" in rendered
    assert 'tradebot_feed_age_ms{symbol="NIFTY"} 4200' in rendered
    assert "# TYPE tradebot_feed_stale_total counter" in rendered
    assert 'tradebot_feed_stale_total{reason="STALE_FEED"} 1' in rendered
    assert 'tradebot_candidates_blocked_total{reason="RISK_BLOCK"} 2' in rendered
    assert "tradebot_fallback_executable_total 0" in rendered


def test_counters_accumulate_by_label_set() -> None:
    registry = build_default_metrics_registry()

    registry.increment_counter("tradebot_candidates_generated_total", labels={"strategy": "opening_drive"})
    registry.increment_counter("tradebot_candidates_generated_total", amount=3, labels={"strategy": "opening_drive"})
    registry.increment_counter("tradebot_candidates_generated_total", labels={"strategy": "mean_reversion"})

    assert registry.get_value("tradebot_candidates_generated_total", labels={"strategy": "opening_drive"}) == 4
    assert registry.get_value("tradebot_candidates_generated_total", labels={"strategy": "mean_reversion"}) == 1


def test_latency_metrics_accept_age_and_latency_names_only() -> None:
    registry = build_default_metrics_registry()

    registry.observe_latency_ms("tradebot_strategy_latency_ms", 12.5)
    registry.observe_latency_ms("tradebot_feed_age_ms", 250)

    assert registry.get_value("tradebot_strategy_latency_ms") == 12.5
    assert registry.get_value("tradebot_feed_age_ms") == 250
    with pytest.raises(ObservabilityMetricError, match="latency_metric_name_must_end_with_ms"):
        registry.observe_latency_ms("tradebot_candidates_ranked_total", 1)


def test_invalid_metric_updates_fail_closed() -> None:
    registry = build_default_metrics_registry()

    with pytest.raises(ObservabilityMetricError, match="metric_not_allowed"):
        registry.set_gauge("tradebot_unknown_metric", 1)
    with pytest.raises(ObservabilityMetricError, match="counter_increment_must_be_non_negative"):
        registry.increment_counter("tradebot_feed_stale_total", amount=-1)
    with pytest.raises(ObservabilityMetricError, match="counter_name_must_end_with_total"):
        registry.increment_counter("tradebot_feed_age_ms")
    with pytest.raises(ObservabilityMetricError, match="metric_value_must_be_finite"):
        registry.set_gauge("tradebot_feed_age_ms", float("nan"))
    with pytest.raises(ObservabilityMetricError, match="invalid_label_name"):
        registry.set_gauge("tradebot_feed_age_ms", 1, labels={"bad-label": "x"})


def test_fallback_executable_metric_must_remain_zero() -> None:
    registry = build_default_metrics_registry()

    registry.assert_safety()
    registry.increment_counter("tradebot_fallback_executable_total")

    with pytest.raises(ObservabilityMetricError, match="fallback_executable_metric_must_remain_zero"):
        registry.assert_safety()


def test_metrics_server_serves_metrics_endpoint() -> None:
    registry = build_default_metrics_registry()
    registry.set_gauge("tradebot_feed_age_ms", 99)
    server = build_server(host="127.0.0.1", port=0, registry=registry)
    host, port = server.server_address
    try:
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with urlopen(f"http://{host}:{port}/metrics", timeout=5) as response:  # noqa: S310 - local test server.
            body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()

    assert "tradebot_feed_age_ms 99" in body
    assert "tradebot_fallback_executable_total 0" in body
