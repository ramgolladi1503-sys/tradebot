from core.regime import REGIME_EVENT, REGIME_NEUTRAL, REGIME_RANGE, REGIME_TREND, normalize_regime
from core.regime_canonical import normalize_legacy_regime_bucket, resolve_strategy_regime_label


def test_legacy_bucket_normalizer_accepts_movement_labels():
    assert normalize_legacy_regime_bucket("TREND_UP") == REGIME_TREND
    assert normalize_legacy_regime_bucket("TREND_DOWN") == REGIME_TREND
    assert normalize_legacy_regime_bucket("CHOP") == REGIME_RANGE
    assert normalize_legacy_regime_bucket("COMPRESSION") == REGIME_RANGE
    assert normalize_legacy_regime_bucket("VOLATILITY_EXPANSION") == REGIME_EVENT
    assert normalize_legacy_regime_bucket("TRAP_RISK") == REGIME_EVENT
    assert normalize_legacy_regime_bucket("EXPIRY_CONTEXT") == REGIME_EVENT
    assert normalize_legacy_regime_bucket("INCONCLUSIVE") == REGIME_NEUTRAL


def test_legacy_regime_module_uses_shared_bucket_normalizer():
    assert normalize_regime("TRENDING_UP") == REGIME_TREND
    assert normalize_regime("TRENDING_DOWN") == REGIME_TREND
    assert normalize_regime("CHOP") == REGIME_RANGE
    assert normalize_regime("VOLATILITY_EXPANSION") == REGIME_EVENT
    assert normalize_regime("GARBAGE") == REGIME_NEUTRAL


def test_strategy_regime_label_resolver_handles_movement_and_legacy_inputs():
    assert resolve_strategy_regime_label("TREND_UP") == "TRENDING_UP"
    assert resolve_strategy_regime_label("TREND_DOWN") == "TRENDING_DOWN"
    assert resolve_strategy_regime_label("TREND", bias="bullish") == "TRENDING_UP"
    assert resolve_strategy_regime_label("TREND", bias="bearish") == "TRENDING_DOWN"
    assert resolve_strategy_regime_label("COMPRESSION") == "RANGE"
    assert resolve_strategy_regime_label("VOLATILITY_EXPANSION") == "VOLATILE"
    assert resolve_strategy_regime_label("EXPIRY_CONTEXT") == "EXPIRY_CONTEXT"
    assert resolve_strategy_regime_label("INCONCLUSIVE") == "UNKNOWN"
