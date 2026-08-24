from pathlib import Path


BOOTSTRAP = Path(__file__).parents[1] / "scripts" / "bootstrap_read_only_live_observer.py"


def test_bootstrap_has_no_forbidden_runtime_wiring():
    source = BOOTSTRAP.read_text()
    assert "main.py" not in source
    assert "run_live.sh" not in source
    assert "core.execution" not in source
    assert "place_order" not in source
    assert "execution_status" not in source or "advisory_only" in source


def test_bootstrap_requires_current_session_and_source_sha():
    source = BOOTSTRAP.read_text()
    assert "READ_ONLY_SESSION_DATE_NOT_CURRENT" in source
    assert "READ_ONLY_SOURCE_SHA_REQUIRED" in source
    assert "READ_ONLY_TOKEN_METADATA_INVALID" in source
