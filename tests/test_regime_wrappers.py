import core.market_data as md
from core.market_regime import detect_market_regime
from core.regime_detection import detect_regime
from core.regime_detector import RegimeDetector
from core.regime import detect_regime as detect_regime_legacy


def test_regime_wrappers_match(monkeypatch):
    snap = {
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.8, "RANGE": 0.2},
        "regime_entropy": 0.4,
        "unstable_regime_flag": False,
        "regime_ts": 1700000000.0,
    }
    monkeypatch.setattr(md, "_LAST_REGIME_SNAPSHOT", {"NIFTY": dict(snap)})

    base = md.get_current_regime("NIFTY")
    r1 = detect_market_regime()
    r2 = detect_regime()
    r3 = RegimeDetector().detect({"symbol": "NIFTY"})
    r4 = detect_regime_legacy()

    for r in (r1, r2, r3, r4):
        assert r.get("primary_regime", r.get("regime")) == base.get("primary_regime")
        assert r.get("regime_probs") == base.get("regime_probs")
        assert r.get("regime_entropy") == base.get("regime_entropy")
        assert r.get("unstable_regime_flag") == base.get("unstable_regime_flag")
