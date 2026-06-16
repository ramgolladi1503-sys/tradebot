from pathlib import Path

from core.strategy_spec import build_strategy_spec_registry


DOC_PATH = Path("/Users/madhuram/tradebot/docs/strategy_module_taxonomy.md")
STRATEGIES_ROOT = Path("/Users/madhuram/tradebot/strategies")


def test_strategy_module_taxonomy_mentions_registry_owned_families():
    registry = build_strategy_spec_registry()
    doc = DOC_PATH.read_text(encoding="utf-8")

    for strategy_id in (
        "vwap_orb",
        "pairs_arbitrage",
        "opening_drive",
        "compression_breakout",
        "failed_breakout_trap",
        "exhaustion_reversal",
        "late_day_momentum",
        "vwap_reclaim_rejection",
        "option_pressure_confirmation",
        "event_volatility_expansion",
        "no_trade_chop",
        "volatility_trend",
        "pro_strategy",
    ):
        spec = registry.get(strategy_id)
        assert spec is not None
        assert spec.module_path.replace(".", "/") in doc
        assert spec.family in doc


def test_strategy_module_taxonomy_marks_support_modules_as_non_strategy_utilities():
    doc = DOC_PATH.read_text(encoding="utf-8")
    assert "strategies/soft_signal.py" in doc
    assert "Support utility" in doc
    assert "strategies/risk_manager.py" in doc


def test_strategy_module_taxonomy_covers_all_strategy_python_modules():
    doc = DOC_PATH.read_text(encoding="utf-8")
    files = sorted(
        path.relative_to(Path("/Users/madhuram/tradebot")).as_posix()
        for path in STRATEGIES_ROOT.rglob("*.py")
        if path.name != "__init__.py"
    )

    missing = [module_path for module_path in files if module_path not in doc]
    assert missing == []
