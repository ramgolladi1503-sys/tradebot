from pathlib import Path


def test_service_adapter_has_no_order_methods():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "run_read_only_live_pipeline_service.py").read_text()
    assert "run_pipeline" in source
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source

