from pathlib import Path


def test_governed_runner_uses_only_read_only_entrypoint():
    source = Path("scripts/run_market_event_graph_live_session_v1.py").read_text()
    assert "run_kite_read_only_observation_v1.py" in source
    assert 'subprocess.run(["bash", "run_live.sh"]' not in source
    assert "run_live_observation.sh" not in source


def test_entrypoint_requires_explicit_launch_inputs():
    source = Path("scripts/run_kite_read_only_observation_v1.py").read_text()
    for flag in ("--session-date", "--output-root", "--kite-instruments-file", "--launch-plan", "--token-path"):
        assert flag in source
