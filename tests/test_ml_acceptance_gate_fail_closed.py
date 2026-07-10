from __future__ import annotations

from core.gates import ml_acceptance_gate as gate


def test_ml_acceptance_gate_missing_model_fails_closed(monkeypatch):
    monkeypatch.setattr(gate, "_MODEL_LOAD_FAILED", True, raising=False)
    monkeypatch.setattr(gate, "_XGB_MODEL", None, raising=False)

    result = gate.validate_ml_acceptance({"metrics": {"rsi_14": 50}})

    assert result["pass"] is False
    assert result["reason_code"] == "MISSING_ML_MODEL"
    assert result["ml_probability"] is None
