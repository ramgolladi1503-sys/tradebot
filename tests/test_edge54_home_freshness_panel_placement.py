from __future__ import annotations

from pathlib import Path

from dashboard.home_freshness_panel import (
    build_home_freshness_artifacts,
    render_home_freshness_panel,
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


def _reader_result(*, fresh: bool, status: str) -> dict:
    return {
        "fresh": fresh,
        "freshness": {
            "status": status,
            "age_seconds": 1.0 if fresh else 900.0,
            "timestamp_source": "generated_epoch",
            "path": "/tmp/artifact.json",
        },
        "blockers": [] if fresh else ["artifact_age_exceeds_max_age"],
    }


def test_build_home_freshness_artifacts_expands_paths():
    artifacts = build_home_freshness_artifacts(
        {
            "advisory_latest": "~/advisory_latest.json",
            "top_opportunities_latest": "/tmp/top_opportunities_latest.json",
        }
    )

    assert set(artifacts) == {"advisory_latest", "top_opportunities_latest"}
    assert all(isinstance(path, Path) for path in artifacts.values())
    assert str(artifacts["advisory_latest"]).startswith(str(Path.home()))


def test_render_home_freshness_panel_uses_home_artifact_names():
    st = FakeStreamlit()
    calls: list[tuple[str, str]] = []

    def fake_reader(path, *, artifact_name):
        calls.append((str(path), artifact_name))
        return _reader_result(fresh=True, status="fresh")

    summary = render_home_freshness_panel(
        st,
        artifacts={
            "advisory_latest": "/tmp/advisory_latest.json",
            "top_opportunities_latest": "/tmp/top_opportunities_latest.json",
        },
        reader=fake_reader,
    )

    assert summary == {"total": 2, "fresh": 2, "warning": 0, "stale": 0, "not_fresh": 0}
    assert calls == [
        ("/tmp/advisory_latest.json", "advisory_latest"),
        ("/tmp/top_opportunities_latest.json", "top_opportunities_latest"),
    ]
    assert ("success", "All 2 latest artifacts are fresh.") in st.calls


def test_render_home_freshness_panel_surfaces_stale_home_artifact():
    st = FakeStreamlit()

    def fake_reader(path, *, artifact_name):
        if artifact_name == "top_opportunities_latest":
            return _reader_result(fresh=False, status="stale")
        return _reader_result(fresh=True, status="fresh")

    summary = render_home_freshness_panel(
        st,
        artifacts={
            "advisory_latest": "/tmp/advisory_latest.json",
            "top_opportunities_latest": "/tmp/top_opportunities_latest.json",
        },
        reader=fake_reader,
    )

    assert summary["total"] == 2
    assert summary["fresh"] == 1
    assert summary["not_fresh"] == 1
    assert ("error", "1 of 2 latest artifacts are not fresh.") in st.calls
    dataframe_call = next(call for call in st.calls if call[0] == "dataframe")
    rendered_rows = dataframe_call[1]["value"]
    stale_rows = [row for row in rendered_rows if row["severity"] == "error"]
    assert stale_rows == [
        {
            "artifact": "top_opportunities_latest",
            "status": "stale",
            "fresh": False,
            "severity": "error",
            "age": "15.0m",
            "timestamp_source": "generated_epoch",
            "blockers": "artifact_age_exceeds_max_age",
            "path": "/tmp/artifact.json",
        }
    ]
