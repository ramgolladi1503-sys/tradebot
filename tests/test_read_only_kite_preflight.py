from pathlib import Path


def test_preflight_is_metadata_only_and_directly_invokable():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "read_only_kite_preflight.py").read_text()
    assert "client.profile()" in source
    assert "client.margins()" in source
    assert "client.instruments(exchange)" in source
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source

