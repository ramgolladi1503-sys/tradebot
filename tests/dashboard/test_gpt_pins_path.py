from __future__ import annotations

import json

import dashboard.streamlit_app_runtime as runtime


def test_gpt_pins_saved_and_loaded_from_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "logs_dir", lambda: tmp_path)

    pins = {"trade-a", "trade-b"}
    runtime._save_gpt_pins(pins)

    pins_path = tmp_path / "gpt_pins.json"
    assert pins_path.exists()
    payload = json.loads(pins_path.read_text(encoding="utf-8"))
    assert sorted(payload) == sorted(pins)

    loaded = runtime._load_gpt_pins()
    assert loaded == pins
