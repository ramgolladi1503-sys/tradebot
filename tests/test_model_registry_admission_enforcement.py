from __future__ import annotations

import json
from pathlib import Path

from core import model_registry as reg


def test_register_model_rejects_missing_governance(tmp_path):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")

    try:
        reg.register_model("xgb", str(model_path), metrics={"acc": 0.5}, governance={})
    except ValueError as exc:
        assert "MODEL_ENTRY_MISSING_PROVENANCE" in str(exc)
    else:
        raise AssertionError("register_model should reject missing governance")


def test_build_admission_report_uses_shared_schema(tmp_path):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    report = reg.build_admission_report(
        model_type="xgb",
        path=model_path,
        status="shadow",
        governance={
            "features": ["x", "y"],
            "training_window": {"rows": 2, "start": "2026-01-01", "end": "2026-01-02"},
        },
        metrics={"acc": 0.9},
        checks={"walk_forward": {"status": "ok"}},
    )

    assert report["schema_version"] == 1
    assert report["admitted"] is True
    assert report["checks"]["walk_forward"]["status"] == "ok"


def test_write_rejection_artifact_persists_report(tmp_path):
    report = {
        "schema_version": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "model_type": "xgb",
        "path": str(tmp_path / "model.pkl"),
        "hash": "abc123",
        "status": "rejected",
        "admitted": False,
        "reason": "MODEL_ENTRY_MISSING_PROVENANCE",
        "metrics": {},
        "governance": {},
        "checks": {},
    }
    out = reg.write_rejection_artifact(report, output_path=tmp_path / "reject.json")

    assert out.exists()
    saved = json.loads(out.read_text())
    assert saved["admitted"] is False
    assert saved["reason"] == "MODEL_ENTRY_MISSING_PROVENANCE"


def test_verify_admission_report_detects_tampering(tmp_path):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    report = reg.build_admission_report(
        model_type="xgb",
        path=model_path,
        status="active",
        governance={
            "features": ["x"],
            "training_window": {"rows": 1, "start": "2026-01-01", "end": "2026-01-01"},
            "walk_forward": {"status": "SELECTED", "selection": {"status": "SELECTED"}},
        },
        metrics={"acc": 1.0},
        checks={"cli": True},
    )
    ok, reason = reg.verify_admission_report(report)

    assert ok is True
    assert reason == "ok"
    report["reason"] = "tampered"
    ok, reason = reg.verify_admission_report(report)
    assert ok is False
    assert reason == "REPORT_HASH_MISMATCH"


def test_activate_model_rejects_when_walk_forward_not_selected(tmp_path):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    governance = {
        "features": ["x"],
        "training_window": {"rows": 10},
        "walk_forward": {"status": "NO_ADMISSIBLE_MODEL"},
    }

    try:
        reg.activate_model("xgb", str(model_path), governance=governance)
    except ValueError as exc:
        assert "WALK_FORWARD_NO_SELECTION" in str(exc)
    else:
        raise AssertionError("activate_model should reject missing selection")
