from core import market_data
from core import market_regime
from core.regime_detector import RegimeDetector
from core import regime_detection
from core import regime


def test_regime_canonical_wrappers():
    sample = {
        "primary_regime": "RANGE",
        "regime_probs": {"RANGE": 0.7, "TREND": 0.3},
        "regime_entropy": 0.61,
        "unstable_regime_flag": False,
        "regime_ts": "2026-02-06T00:00:00",
    }
    market_data._LAST_REGIME_SNAPSHOT["NIFTY"] = sample

    snap = market_data.get_current_regime("NIFTY")
    assert snap["regime_probs"] == sample["regime_probs"]
    assert snap["regime_entropy"] == sample["regime_entropy"]

    mr = market_regime.detect_market_regime()
    assert mr["regime_probs"] == sample["regime_probs"]
    assert mr["regime_entropy"] == sample["regime_entropy"]

    rd = RegimeDetector().detect({"symbol": "NIFTY"})
    assert rd["regime_probs"] == sample["regime_probs"]
    assert rd["regime_entropy"] == sample["regime_entropy"]

    r1 = regime_detection.detect_regime(None)
    assert r1["regime_probs"] == sample["regime_probs"]
    assert r1["regime_entropy"] == sample["regime_entropy"]

    r2 = regime.detect_regime(None)
    assert r2["regime_probs"] == sample["regime_probs"]
    assert r2["regime_entropy"] == sample["regime_entropy"]
