import core.runtime_safety_boot_guard as boot_guard
import core.runtime_startup_lifecycle as lifecycle
from core.runtime_boot_identity import ENV_BOOT_EPOCH, ENV_RUN_ID


def test_boot_safety_records_validated_runtime_startup_event(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-boot-safety-proof")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "6000.0")
    monkeypatch.setattr(boot_guard, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    decision = boot_guard.enforce_runtime_boot_safety(
        mode="PAPER",
        config={"EXECUTION_MODE": "PAPER"},
        env={},
    )

    assert decision.allowed is True
    payload = lifecycle.read_runtime_startup_lifecycle(tmp_path / "runtime_startup_lifecycle_latest.json")
    assert payload["last_event"] == "MAIN_SAFETY_VALIDATED"
    assert payload["proof_flags"]["main_safety_validated"] is True
    assert payload["is_order_action"] is False
    assert payload["events"][-1]["details"]["mode"] == "PAPER"
    assert payload["events"][-1]["details"]["allowed"] is True


def test_boot_safety_records_failed_runtime_startup_event(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_RUN_ID, "run-boot-safety-fail-proof")
    monkeypatch.setenv(ENV_BOOT_EPOCH, "7000.0")
    monkeypatch.setattr(boot_guard, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(lifecycle, "logs_dir", lambda: tmp_path)

    try:
        boot_guard.enforce_runtime_boot_safety(
            mode="LIVE",
            config={"EXECUTION_MODE": "LIVE", "ALLOW_STALE_QUOTES": True},
            env={},
        )
    except RuntimeError as exc:
        assert "runtime_boot_safety_failed" in str(exc)
    else:
        raise AssertionError("expected unsafe LIVE boot to fail")

    payload = lifecycle.read_runtime_startup_lifecycle(tmp_path / "runtime_startup_lifecycle_latest.json")
    assert payload["last_event"] == "MAIN_SAFETY_VALIDATION_FAILED"
    assert payload["proof_flags"]["failure_seen"] is True
    assert payload["last_error"].startswith("runtime_boot_safety_failed:")
    assert "LIVE_UNSAFE_FLAG:ALLOW_STALE_QUOTES" in payload["events"][-1]["details"]["fatal_reasons"]
