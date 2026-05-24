from __future__ import annotations

from dashboard.ui.freshness_panel import (
    build_freshness_panel_row,
    collect_latest_artifact_freshness_rows,
    render_latest_artifact_freshness_panel,
    summarize_freshness_panel_rows,
)


class FakeStreamlit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def markdown(self, value: str) -> None:
        self.calls.append(("markdown", value))

    def caption(self, value: str) -> None:
        self.calls.append(("caption", value))

    def error(self, value: str) -> None:
        self.calls.append(("error", value))

    def warning(self, value: str) -> None:
        self.calls.append(("warning", value))

    def success(self, value: str) -> None:
        self.calls.append(("success", value))

    def dataframe(self, value, **kwargs) -> None:
        self.calls.append(("dataframe", {"value": value, "kwargs": kwargs}))


def _fresh_result() -> dict:
    return {
        "fresh": True,
        "freshness": {
            "status": "fresh",
            "age_seconds": 12.5,
            "timestamp_source": "generated_epoch",
            "path": "/tmp/fresh.json",
        },
        "blockers": [],
    }


def _stale_result() -> dict:
    return {
        "fresh": False,
        "freshness": {
            "status": "stale",
            "age_seconds": 900.0,
            "timestamp_source": "generated_epoch",
            "path": "/tmp/stale.json",
        },
        "blockers": ["artifact_age_exceeds_max_age"],
    }


def test_build_freshness_panel_row_for_fresh_result():
    row = build_freshness_panel_row("advisory_latest", _fresh_result())

    assert row["artifact"] == "advisory_latest"
    assert row["status"] == "fresh"
    assert row["fresh"] is True
    assert row["severity"] == "ok"
    assert row["age"] == "12.5s"
    assert row["timestamp_source"] == "generated_epoch"
    assert row["blockers"] == "none"


def test_build_freshness_panel_row_for_stale_result():
    row = build_freshness_panel_row("top_opportunities", _stale_result())

    assert row["status"] == "stale"
    assert row["fresh"] is False
    assert row["severity"] == "error"
    assert row["age"] == "15.0m"
    assert row["blockers"] == "artifact_age_exceeds_max_age"


def test_collect_latest_artifact_freshness_rows_uses_reader():
    calls: list[tuple[str, str]] = []

    def fake_reader(path, *, artifact_name):
        calls.append((str(path), artifact_name))
        return _fresh_result()

    rows = collect_latest_artifact_freshness_rows(
        {"advisory_latest": "/tmp/advisory.json", "top_opportunities": "/tmp/top.json"},
        reader=fake_reader,
    )

    assert [row["artifact"] for row in rows] == ["advisory_latest", "top_opportunities"]
    assert calls == [
        ("/tmp/advisory.json", "advisory_latest"),
        ("/tmp/top.json", "top_opportunities"),
    ]


def test_summarize_freshness_panel_rows_counts_not_fresh():
    rows = [
        build_freshness_panel_row("fresh", _fresh_result()),
        build_freshness_panel_row("stale", _stale_result()),
    ]

    summary = summarize_freshness_panel_rows(rows)

    assert summary == {"total": 2, "fresh": 1, "warning": 0, "stale": 1, "not_fresh": 1}


def test_render_latest_artifact_freshness_panel_success_path():
    st = FakeStreamlit()
    rows = [build_freshness_panel_row("advisory_latest", _fresh_result())]

    summary = render_latest_artifact_freshness_panel(st, rows)

    assert summary["fresh"] == 1
    assert ("success", "All 1 latest artifacts are fresh.") in st.calls
    dataframe_calls = [call for call in st.calls if call[0] == "dataframe"]
    assert len(dataframe_calls) == 1
    assert dataframe_calls[0][1]["kwargs"] == {"use_container_width": True, "hide_index": True}


def test_render_latest_artifact_freshness_panel_error_path():
    st = FakeStreamlit()
    rows = [build_freshness_panel_row("top_opportunities", _stale_result())]

    summary = render_latest_artifact_freshness_panel(st, rows)

    assert summary["not_fresh"] == 1
    assert ("error", "1 of 1 latest artifacts are not fresh.") in st.calls


def test_render_latest_artifact_freshness_panel_empty_path():
    st = FakeStreamlit()

    summary = render_latest_artifact_freshness_panel(st, [])

    assert summary == {"total": 0, "fresh": 0, "warning": 0, "stale": 0, "not_fresh": 0}
    assert ("caption", "No latest artifact freshness rows available.") in st.calls
