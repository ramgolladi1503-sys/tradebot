from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "run_live.sh").read_text(encoding="utf-8")


def test_read_only_mode_execs_real_product_and_externalizes_runtime():
    assert '--read-only-observation' in LAUNCHER
    assert 'exec python "$ROOT_DIR/main.py"' in LAUNCHER
    assert '/Volumes/TradeBotData/tradebot-os/live/current-main' in LAUNCHER
    assert 'TRADEBOT_ACCESS_TOKEN_PATH' in LAUNCHER


def test_read_only_mode_disables_all_execution_authority():
    for key in (
        "TRADEBOT_READ_ONLY=true",
        "ALLOW_LIVE_ORDERS=0",
        "AUTO_TRADE=0",
        "AUTO_ORDER=0",
        "LIVE_TRADING_ENABLED=false",
        "PAPER_TRADING_ENABLED=false",
        "BROKER_WRITE_AUTHORITY=false",
        "ORDER_AUTHORITY=false",
        "PAPER_AUTHORIZED=false",
        "LIVE_EXECUTION_AUTHORIZED=false",
    ):
        assert key in LAUNCHER


def test_legacy_observer_is_not_called_by_canonical_launcher():
    assert "run_live_observation.sh" not in LAUNCHER
