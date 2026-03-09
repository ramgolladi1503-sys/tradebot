from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import dashboard.streamlit_app_runtime as runtime
from config import config as cfg
from core import tf_utils


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_load_does_not_import_tensorflow(tmp_path):
    env = os.environ.copy()
    env["DATA_ROOT"] = str(tmp_path / "runtime_data")
    cmd = [
        sys.executable,
        "-c",
        "import sys; import dashboard.streamlit_app_runtime; print(int('tensorflow' in sys.modules))",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines
    assert lines[-1] == "0"


def test_check_tf_available_returns_false_on_missing_tf(monkeypatch):
    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="ModuleNotFoundError")

    monkeypatch.setattr(tf_utils.subprocess, "run", _fake_run)
    assert tf_utils.check_tf_available(timeout_sec=0.1) is False


def test_micro_training_runner_writes_pid_log_and_blocks_overlap(tmp_path, monkeypatch):
    paths = {
        "log": tmp_path / "logs" / "train_micro.log",
        "pid": tmp_path / "logs" / "train_micro.pid",
        "lock": tmp_path / "logs" / "train_micro.lock",
        "status": tmp_path / "logs" / "train_micro.status.json",
        "model_artifact": tmp_path / "models" / "microstructure_model.h5",
        "feature_importance": tmp_path / "logs" / "micro_feature_importance.csv",
    }

    popen_calls: list[tuple[list[str], dict]] = []

    class _FakeProc:
        pid = 424242

    def _fake_popen(command, **kwargs):
        popen_calls.append((list(command), dict(kwargs)))
        return _FakeProc()

    started, message = runtime.start_micro_training_subprocess(
        backend_override="sklearn",
        paths=paths,
        popen_fn=_fake_popen,
        root_dir=tmp_path,
    )

    assert started is True
    assert "started" in message.lower()
    assert paths["pid"].exists()
    assert paths["lock"].exists()
    assert paths["status"].exists()
    assert paths["log"].exists()
    assert paths["pid"].read_text(encoding="utf-8").strip() == "424242"

    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["status"] == runtime.MICRO_TRAIN_STATUS_RUNNING

    assert len(popen_calls) == 1
    cmd, kwargs = popen_calls[0]
    assert cmd[:3] == [sys.executable, "-m", "models.train_micro_model"]
    assert cmd[-2:] == ["--backend", "sklearn"]
    assert kwargs["env"]["MPLBACKEND"] == "Agg"
    assert kwargs["env"]["TF_CPP_MIN_LOG_LEVEL"] == "2"

    monkeypatch.setattr(runtime, "_is_pid_alive", lambda pid: True)
    started_again, message_again = runtime.start_micro_training_subprocess(
        backend_override="sklearn",
        paths=paths,
        popen_fn=_fake_popen,
        root_dir=tmp_path,
    )
    assert started_again is False
    assert "already running" in message_again.lower()
    assert len(popen_calls) == 1


def test_is_pid_alive_reaps_exited_child():
    proc = subprocess.Popen(
        [sys.executable, "-c", "print('done')"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait(timeout=10)

    assert runtime._is_pid_alive(proc.pid) is False
    assert runtime._is_pid_alive(proc.pid) is False


def test_micro_model_badge_state_marks_stale_artifact_as_not_trained(tmp_path):
    paths = {
        "log": tmp_path / "logs" / "train_micro.log",
        "pid": tmp_path / "logs" / "train_micro.pid",
        "lock": tmp_path / "logs" / "train_micro.lock",
        "status": tmp_path / "logs" / "train_micro.status.json",
        "model_artifact": tmp_path / "models" / "microstructure_model.h5",
        "feature_importance": tmp_path / "logs" / "micro_feature_importance.csv",
    }
    paths["feature_importance"].parent.mkdir(parents=True, exist_ok=True)
    paths["feature_importance"].write_text("feature,importance\nx,1.0\n", encoding="utf-8")

    label, stale = runtime._micro_model_badge_state(
        paths=paths,
        state={"status": runtime.MICRO_TRAIN_STATUS_FAILED},
    )

    assert label == "Not trained"
    assert stale is True


def test_micro_model_readiness_requires_training_report_and_class_variance(tmp_path):
    paths = {
        "log": tmp_path / "logs" / "train_micro.log",
        "pid": tmp_path / "logs" / "train_micro.pid",
        "lock": tmp_path / "logs" / "train_micro.lock",
        "status": tmp_path / "logs" / "train_micro.status.json",
        "model_artifact": tmp_path / "models" / "microstructure_model.h5",
        "feature_importance": tmp_path / "logs" / "micro_feature_importance.csv",
    }
    paths["model_artifact"].parent.mkdir(parents=True, exist_ok=True)
    # sklearn fallback writes a .pkl sibling for .h5 configured paths.
    paths["model_artifact"].with_suffix(".pkl").write_text("stub", encoding="utf-8")
    paths["status"].parent.mkdir(parents=True, exist_ok=True)
    paths["status"].write_text(
        json.dumps({"status": runtime.MICRO_TRAIN_STATUS_SUCCESS}),
        encoding="utf-8",
    )

    readiness = runtime._micro_model_readiness(paths=paths)
    label, stale = runtime._micro_model_badge_state(paths=paths)

    assert readiness["ready"] is False
    assert readiness["reason_code"] == "TRAIN_REPORT_MISSING"
    assert label == "Not trained"
    assert stale is True


def test_micro_model_readiness_succeeds_with_valid_report(tmp_path):
    paths = {
        "log": tmp_path / "logs" / "train_micro.log",
        "pid": tmp_path / "logs" / "train_micro.pid",
        "lock": tmp_path / "logs" / "train_micro.lock",
        "status": tmp_path / "logs" / "train_micro.status.json",
        "model_artifact": tmp_path / "models" / "microstructure_model.h5",
        "feature_importance": tmp_path / "logs" / "micro_feature_importance.csv",
    }
    paths["model_artifact"].parent.mkdir(parents=True, exist_ok=True)
    paths["model_artifact"].with_suffix(".pkl").write_text("stub", encoding="utf-8")
    paths["log"].parent.mkdir(parents=True, exist_ok=True)
    paths["log"].write_text(
        "\n".join(
            [
                "[2026-03-02T00:00:00+00:00] START",
                json.dumps({"status": "TRAINED", "class_labels": [0, 1]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["status"].parent.mkdir(parents=True, exist_ok=True)
    paths["status"].write_text(
        json.dumps({"status": runtime.MICRO_TRAIN_STATUS_SUCCESS}),
        encoding="utf-8",
    )

    readiness = runtime._micro_model_readiness(paths=paths)
    label, stale = runtime._micro_model_badge_state(paths=paths)

    assert readiness["ready"] is True
    assert readiness["reason_code"] is None
    assert readiness["class_labels"] == [0, 1]
    assert label == "Trained"
    assert stale is False


def test_suggestion_reliability_snapshot_defaults_when_missing(monkeypatch, tmp_path):
    missing = tmp_path / "logs" / "suggestion_reliability_latest.json"
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_LATEST_PATH", str(missing), raising=False)

    payload = runtime._suggestion_reliability_snapshot()

    assert payload["exists"] is False
    assert payload["status"] == "UNKNOWN"
    assert payload["allowed_count"] == 0
    assert payload["candidate_count"] == 0
    assert payload["min_allowed"] == 20
    assert payload["reason_codes"] == []


def test_suggestion_reliability_snapshot_reads_latest_payload(monkeypatch, tmp_path):
    latest = tmp_path / "logs" / "suggestion_reliability_latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(
        json.dumps(
            {
                "status": "INSUFFICIENT_SAMPLE",
                "allowed_count": 7,
                "candidate_count": 3,
                "min_allowed": 20,
                "mode": "SIM",
                "window_sec": 900,
                "reason_codes": ["SUGGESTION_SAMPLE_TOO_SMALL"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "SUGGESTION_RELIABILITY_LATEST_PATH", str(latest), raising=False)

    payload = runtime._suggestion_reliability_snapshot()

    assert payload["exists"] is True
    assert payload["status"] == "INSUFFICIENT_SAMPLE"
    assert payload["allowed_count"] == 7
    assert payload["candidate_count"] == 3
    assert payload["min_allowed"] == 20
    assert payload["mode"] == "SIM"
    assert payload["window_sec"] == 900
    assert payload["reason_codes"] == ["SUGGESTION_SAMPLE_TOO_SMALL"]
