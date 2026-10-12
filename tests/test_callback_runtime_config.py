from core.feed import callback_config


def test_callback_runtime_config_uses_conservative_defaults(monkeypatch):
    for name in (
        "DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING",
        "DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC",
        "FEED_RESTART_LIFECYCLE_WAIT_SEC",
        "FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC",
    ):
        monkeypatch.delenv(name, raising=False)

    assert callback_config.callback_queue_max_pending() == 64
    assert callback_config.callback_transition_timeout_sec() == 10.0
    assert callback_config.restart_lifecycle_wait_sec() == 10.0
    assert callback_config.restart_verify_block_log_cooldown_sec() == 30.0


def test_callback_runtime_config_accepts_bounded_environment_overrides(monkeypatch):
    monkeypatch.setenv("DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING", "128")
    monkeypatch.setenv("DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", "2.5")
    monkeypatch.setenv("FEED_RESTART_LIFECYCLE_WAIT_SEC", "0")
    monkeypatch.setenv("FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC", "900")

    assert callback_config.callback_queue_max_pending(1) == 128
    assert callback_config.callback_transition_timeout_sec(1.0) == 2.5
    assert callback_config.restart_lifecycle_wait_sec(1.0) == 0.0
    assert callback_config.restart_verify_block_log_cooldown_sec(1.0) == 900.0


def test_callback_runtime_config_clamps_out_of_range_environment_values(monkeypatch):
    monkeypatch.setenv("DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING", "999999")
    monkeypatch.setenv("DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", "999")
    monkeypatch.setenv("FEED_RESTART_LIFECYCLE_WAIT_SEC", "-5")
    monkeypatch.setenv("FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC", "99999")

    assert callback_config.callback_queue_max_pending() == 4096
    assert callback_config.callback_transition_timeout_sec() == 120.0
    assert callback_config.restart_lifecycle_wait_sec() == 0.0
    assert callback_config.restart_verify_block_log_cooldown_sec() == 3600.0


def test_callback_runtime_config_rejects_malformed_and_nonfinite_values(monkeypatch):
    monkeypatch.setenv("DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING", "1.5")
    monkeypatch.setenv("DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", "nan")
    monkeypatch.setenv("FEED_RESTART_LIFECYCLE_WAIT_SEC", "inf")
    monkeypatch.setenv("FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC", "not-a-number")

    assert callback_config.callback_queue_max_pending(256) == 64
    assert callback_config.callback_transition_timeout_sec(1.0) == 10.0
    assert callback_config.restart_lifecycle_wait_sec(2.0) == 10.0
    assert callback_config.restart_verify_block_log_cooldown_sec(3.0) == 30.0


def test_callback_runtime_config_uses_legacy_override_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING", raising=False)
    assert callback_config.callback_queue_max_pending(32) == 32
    assert callback_config.callback_queue_max_pending(0) == 1
