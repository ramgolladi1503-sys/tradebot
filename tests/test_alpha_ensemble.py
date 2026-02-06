from core.alpha_ensemble import AlphaEnsemble


def test_alpha_ensemble_basic():
    ae = AlphaEnsemble(model_path="")
    res = ae.combine(
        xgb_conf=0.7,
        deep_conf=0.6,
        micro_conf=0.55,
        regime_probs={"TREND": 0.7, "RANGE": 0.2},
        shock_score=0.2,
        cross={"x_vol_spillover": 0.1},
    )
    assert 0.0 <= res["final_prob"] <= 1.0
    assert 0.0 <= res["uncertainty"] <= 1.0
    assert 0.0 < res["size_mult"] <= 1.0


def test_alpha_ensemble_uncertainty_downsizes():
    ae = AlphaEnsemble(model_path="")
    res = ae.combine(
        xgb_conf=0.9,
        deep_conf=0.1,
        micro_conf=0.9,
        regime_probs={"TREND": 0.34, "RANGE": 0.33, "EVENT": 0.33},
        shock_score=0.8,
        cross={"x_vol_spillover": 2.0},
    )
    assert 0.0 <= res["uncertainty"] <= 1.0
    assert res["size_mult"] <= 1.0
