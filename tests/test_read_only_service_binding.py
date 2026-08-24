from pathlib import Path


def test_service_shell_uses_existing_governed_loader_only():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_read_only_live_pipeline_service.sh").read_text()
    assert "live_credentials.sh" in source
    assert "exec /opt/anaconda3/bin/python" in source
    assert "KITE_API_KEY=" not in source
    assert "KITE_API_SECRET=" not in source

